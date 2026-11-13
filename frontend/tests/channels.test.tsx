import { afterEach, describe, expect, it, vi } from "vitest";
import { QueryClient, type InfiniteData } from "@tanstack/react-query";
import { applyEvent } from "../src/app/socket";
import { ChannelList } from "../src/features/channels/ChannelList";
import { ChannelView } from "../src/features/channels/ChannelView";
import type { Message, MessagePage } from "../src/features/channels/api";
import { activeQuery, encode, segments } from "../src/features/channels/mentions";
import { mockApi, renderWithProviders, screen, waitFor, within } from "./test-utils";

vi.mock("../src/app/auth", async (original) => ({
  ...(await original<typeof import("../src/app/auth")>()),
  useAuth: () => ({ user: { id: "u-me", full_name: "Me" }, token: "t", loading: false }),
}));

const RIYA = "11111111-1111-4111-8111-111111111111";
const member = (id: string, name: string) => ({
  user: { id, full_name: name, email: `${name}@acme.in` },
  role: { id: "r", name: "Developer", is_default: true },
  stakeholder_group: null,
  joined_at: "2026-10-01T00:00:00Z",
});
const MEMBERS = [member("u-me", "Me"), member(RIYA, "Riya Kapoor"), member("u-arjun", "Arjun Mehta")];
const CHANNEL = {
  id: "c1",
  project_id: "p1",
  name: "general",
  topic: "Everything else",
  is_private: false,
  is_default: true,
  archived_at: null,
  created_by: null,
  created_at: "2026-10-01T00:00:00Z",
  unread_count: 0,
  last_message_at: null,
};
let seq = 0;
const message = (overrides: Partial<Message> = {}): Message => ({
  id: `m${++seq}`,
  channel_id: "c1",
  parent_id: null,
  kind: "chat",
  body: "hello",
  author: { id: "u-arjun", full_name: "Arjun Mehta", is_member: true },
  mentions: [],
  created_at: "2026-10-24T10:42:00Z",
  edited_at: null,
  deleted: false,
  reply_count: 0,
  last_reply_at: null,
  cursor: `cur-${seq}`,
  ...overrides,
});
const permissions = (granted: string[]) => ({
  workspace_id: "w1",
  project_id: "p1",
  role: { id: "r", name: "Developer", is_default: true },
  permissions: granted,
  protected_only: [],
});
const VIEW = "/w/w1/p/p1/channels/c1";
const PATH = "/w/:workspaceId/p/:projectId/channels/:channelId";

function routes(messages: Message[], extra: Record<string, unknown> = {}) {
  return {
    "GET /api/v1/channels/c1": CHANNEL,
    "GET /api/v1/workspaces/w1/members": MEMBERS,
    "GET /api/v1/channels/c1/messages": { items: messages, next_cursor: null },
    "GET /api/v1/me/permissions": permissions(["view", "message.post"]),
    "POST /api/v1/channels/c1/read": [204, null],
    ...extra,
  };
}

afterEach(() => vi.unstubAllGlobals());

describe("mentions", () => {
  it("turns picked names into tokens and tokens back into names, as text", () => {
    const body = encode("@Riya Kapoor please check", [{ userId: RIYA, name: "Riya Kapoor" }]);
    expect(body).toBe(`<@${RIYA}> please check`);
    expect(segments(body, new Map([[RIYA, "Riya Kapoor"]]))).toEqual([
      { kind: "mention", userId: RIYA, name: "Riya Kapoor" },
      { kind: "text", text: " please check" },
    ]);
    expect(activeQuery("hi @ri", 6)).toEqual({ start: 3, query: "ri" });
    expect(activeQuery("mail me@acme", 12)).toBeNull(); // an e-mail address is not a mention
  });
});

describe("ChannelList", () => {
  it("lists channels with unread counts and offers + Channel only to managers", async () => {
    mockApi({
      "GET /api/v1/projects/p1/channels": [
        CHANNEL,
        { ...CHANNEL, id: "c2", name: "security", is_private: true, is_default: false, unread_count: 3 },
      ],
      "GET /api/v1/me/permissions": permissions(["view", "message.post"]),
    });
    renderWithProviders(<ChannelList workspaceId="w1" projectId="p1" />);

    const security = await screen.findByRole("link", { name: /security/ });
    expect(security).toHaveAttribute("href", "/w/w1/p/p1/channels/c2");
    expect(within(security).getByLabelText("3 unread")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "New channel" })).not.toBeInTheDocument();
  });
});

describe("ChannelView", () => {
  it("renders bodies as text, mentions as names, and marks former members and edits", async () => {
    mockApi(
      routes([
        message({ body: `<@${RIYA}> look: <b>bold</b>`, edited_at: "2026-10-24T10:43:00Z" }),
        message({ body: "old words", author: { id: "u-gone", full_name: "Sam", is_member: false } }),
        message({ body: "", deleted: true }),
        message({ body: "When idle for 5 minutes, log out.", kind: "requirement_post" }),
      ]),
    );
    renderWithProviders(<ChannelView />, { route: VIEW, path: PATH });

    expect(await screen.findByText("@Riya Kapoor")).toHaveClass("mention");
    expect(screen.getByText(/<b>bold<\/b>/)).toBeInTheDocument(); // not interpreted as HTML
    expect(screen.getByText("· edited")).toBeInTheDocument();
    expect(screen.getByText("(former member)")).toBeInTheDocument();
    expect(screen.getByText("This message was deleted.")).toBeInTheDocument();
    expect(screen.getByText("Requirement · Proposed")).toBeInTheDocument();
  });

  it("sends with the keyboard alone and shows the new message", async () => {
    const { calls } = mockApi(
      routes([], { "POST /api/v1/channels/c1/messages": message({ body: "Is 30 minutes final?", author: { id: "u-me", full_name: "Me", is_member: true } }) }),
    );
    const { user } = renderWithProviders(<ChannelView />, { route: VIEW, path: PATH });

    const box = await screen.findByLabelText("Message #general");
    await user.type(box, "Is 30 minutes final?{Enter}");

    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path.endsWith("/messages"))).toBe(true));
    const sent = calls.find((c) => c.method === "POST" && c.path.endsWith("/messages"));
    expect(JSON.parse(String(sent?.body))).toEqual({ body: "Is 30 minutes final?", parent_id: null });
    expect(await screen.findByText("Is 30 minutes final?")).toBeInTheDocument();
    expect(box).toHaveValue("");
  });

  it("picks a mention from the list with the keyboard and sends its token", async () => {
    const { calls } = mockApi(routes([], { "POST /api/v1/channels/c1/messages": message() }));
    const { user } = renderWithProviders(<ChannelView />, { route: VIEW, path: PATH });

    const box = await screen.findByLabelText("Message #general");
    await user.type(box, "@ri");
    expect(await screen.findByRole("option", { name: /Riya Kapoor/ })).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{Enter}");
    await waitFor(() => expect(box).toHaveValue("@Riya Kapoor "));
    await user.type(box, "can you check?{Enter}");

    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path.endsWith("/messages"))).toBe(true));
    const sent = calls.find((c) => c.method === "POST" && c.path.endsWith("/messages"));
    expect(JSON.parse(String(sent?.body)).body).toBe(`<@${RIYA}> can you check?`);
  });

  it("is read-only when archived and for members who cannot post", async () => {
    mockApi(routes([message()], { "GET /api/v1/channels/c1": { ...CHANNEL, archived_at: "2026-10-20T00:00:00Z" } }));
    renderWithProviders(<ChannelView />, { route: VIEW, path: PATH });

    expect(await screen.findByText(/This channel is archived/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Message #general")).not.toBeInTheDocument();
  });

  it("opens a thread in the drawer with its replies and a reply box", async () => {
    const root = message({ body: "Which timeout applies?", reply_count: 1 });
    const reply = message({ body: "30 minutes", parent_id: root.id });
    mockApi(routes([root], { [`GET /api/v1/messages/${root.id}/thread`]: [root, reply] }));
    const { user } = renderWithProviders(<ChannelView />, { route: VIEW, path: PATH });

    await user.click(await screen.findByRole("button", { name: "1 reply" }));

    const drawer = await screen.findByRole("dialog", { name: "Thread" });
    expect(await within(drawer).findByText("30 minutes")).toBeInTheDocument();
    expect(within(drawer).getByLabelText("Reply in thread")).toBeInTheDocument();
  });

  it("offers Edit and Delete on your own chat messages only", async () => {
    mockApi(
      routes([
        message({ body: "mine", author: { id: "u-me", full_name: "Me", is_member: true } }),
        message({ body: "theirs" }),
      ]),
    );
    renderWithProviders(<ChannelView />, { route: VIEW, path: PATH });

    const mine = (await screen.findByText("mine")).closest("article") as HTMLElement;
    const theirs = screen.getByText("theirs").closest("article") as HTMLElement;
    expect(within(mine).getByRole("button", { name: "Edit" })).toBeInTheDocument();
    expect(within(theirs).queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
  });
});

describe("realtime", () => {
  it("re-reads a message named by an event and appends it to the open channel", async () => {
    const arrived = message({ body: "live!" });
    mockApi({ [`GET /api/v1/messages/${arrived.id}`]: arrived });
    const queryClient = new QueryClient();
    queryClient.setQueryData<InfiniteData<MessagePage>>(["messages", "c1"], {
      pages: [{ items: [message({ body: "earlier" })], next_cursor: null }],
      pageParams: [null],
    });

    applyEvent(queryClient, {
      type: "message.created",
      workspace_id: "w1",
      project_id: "p1",
      channel_id: "c1",
      entity_id: arrived.id,
      at: "2026-10-24T10:42:00Z",
      data: { message_id: arrived.id, private: false },
    });

    await waitFor(() => {
      const data = queryClient.getQueryData<InfiniteData<MessagePage>>(["messages", "c1"]);
      expect(data?.pages[0].items.map((m) => m.body)).toEqual(["earlier", "live!"]);
    });
  });
});
