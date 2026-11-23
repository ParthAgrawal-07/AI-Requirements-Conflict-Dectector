import { afterEach, describe, expect, it, vi } from "vitest";
import { DiscussionPanel } from "../src/features/discussion/DiscussionPanel";
import { WatchButton } from "../src/features/discussion/WatchButton";
import { mockApi, renderWithProviders, screen, within } from "./test-utils";

afterEach(() => vi.unstubAllGlobals());

const permissions = (granted: string[]) => ({
  workspace_id: "w1",
  project_id: "p1",
  role: { id: "r", name: "Stakeholder", is_default: true },
  permissions: granted,
  protected_only: [],
});

const social = {
  requirement_id: "r31",
  comments: 1,
  votes: {
    support: 1,
    oppose: 1,
    mine: null,
    decides: false,
    votes: [
      { user_id: "u1", user_name: "Riya", stance: "oppose", reason: "Too short for night shifts" },
      { user_id: "u2", user_name: "Arjun", stance: "support", reason: null },
    ],
  },
  watching: false,
  links: [
    {
      id: "l1",
      source_id: "r31",
      source_label: "REQ-031",
      target_id: "r14",
      target_label: "REQ-014",
      kind: "depends_on",
      direction: "outgoing",
      note: null,
      created_by: "u1",
      created_by_name: "Riya",
      created_at: "2027-01-03T10:00:00Z",
      found_by: "person",
    },
  ],
};

const graph = {
  project_id: "p1",
  revision: 3,
  nodes: [
    { id: "r31", label: "REQ-031", state: "Proposed", group: null, owner_id: null, req_type: null,
      origin: "post", is_protected: false, open_issues: 0, x: null, y: null },
    { id: "r20", label: "REQ-020", state: "Approved", group: null, owner_id: null, req_type: null,
      origin: "document", is_protected: false, open_issues: 0, x: null, y: null },
  ],
  edges: [],
};

function api(granted: string[], extra: Record<string, unknown> = {}) {
  return mockApi({
    "GET /api/v1/me/permissions?project=p1": permissions(granted),
    "GET /api/v1/requirements/r31/social": social,
    "GET /api/v1/requirements/r31/watch": { watching: false, watchers: 2 },
    "GET /api/v1/projects/p1/graph": graph,
    "GET /api/v1/requirements/r31/comments": [
      { id: "c1", author_id: "u1", author_name: "Riya", body: "Clinicians need longer.",
        created_at: "2027-01-03T10:00:00Z", edited_at: null },
    ],
    ...extra,
  });
}

describe("DiscussionPanel", () => {
  it("shows the tally with reasons as information, the links and the thread", async () => {
    api(["view"]);
    const { user } = renderWithProviders(<DiscussionPanel projectId="p1" requirementId="r31" label="REQ-031" />);

    expect(await screen.findByText(/1 support · ▼ 1 oppose/)).toBeInTheDocument();
    expect(screen.getByText(/votes never change a state/)).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: "Reasons" })).getByText(/Too short for night shifts/)).toBeInTheDocument();
    const links = screen.getByRole("list", { name: "Links" });
    expect(within(links).getByText(/REQ-031 depends on REQ-014/)).toBeInTheDocument();
    expect(within(links).getByText("Person")).toBeInTheDocument();
    // A viewer: no voting, linking or commenting controls.
    expect(screen.queryByRole("button", { name: /Support/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "Add a link" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Comments (1)" }));
    expect(await screen.findByText("Clinicians need longer.")).toBeInTheDocument();
    expect(screen.queryByLabelText("Add a comment")).not.toBeInTheDocument();
  });

  it("lets a stakeholder vote with a reason and comment", async () => {
    const { calls } = api(["view", "req.vote", "req.comment"], {
      "PUT /api/v1/requirements/r31/vote": { ...social.votes, support: 2, mine: "support" },
      "POST /api/v1/requirements/r31/comments": [201, { id: "c2", author_id: "u3", author_name: "Me",
        body: "Agreed", created_at: "2027-01-03T11:00:00Z", edited_at: null }],
    });
    const { user } = renderWithProviders(<DiscussionPanel projectId="p1" requirementId="r31" label="REQ-031" />);

    await user.type(await screen.findByLabelText("Reason for your vote (optional)"), "Matches the audit");
    await user.click(screen.getByRole("button", { name: "▲ Support" }));
    const put = calls.find((c) => c.method === "PUT");
    expect(JSON.parse(String(put?.body))).toEqual({ stance: "support", reason: "Matches the audit" });

    await user.click(screen.getByRole("button", { name: "Comments (1)" }));
    await user.type(await screen.findByLabelText("Add a comment"), "Agreed");
    await user.click(screen.getByRole("button", { name: "Comment" }));
    const post = calls.find((c) => c.method === "POST");
    expect(JSON.parse(String(post?.body))).toEqual({ body: "Agreed" });
  });

  it("lets an analyst add a link to another requirement of the project", async () => {
    const { calls } = api(["view", "req.link"], {
      "POST /api/v1/requirements/r31/links": [201, { ...social.links[0], id: "l2", target_id: "r20" }],
    });
    const { user } = renderWithProviders(<DiscussionPanel projectId="p1" requirementId="r31" label="REQ-031" />);

    const form = await screen.findByRole("form", { name: "Add a link" });
    await user.selectOptions(within(form).getByLabelText("Relation"), "refines");
    await user.selectOptions(within(form).getByLabelText("Other requirement"), "REQ-020");
    await user.click(within(form).getByRole("button", { name: "Link" }));
    const post = calls.find((c) => c.method === "POST");
    expect(JSON.parse(String(post?.body))).toEqual({ target_id: "r20", kind: "refines" });
  });
});

describe("WatchButton", () => {
  it("toggles watching and announces the pressed state", async () => {
    const { calls } = mockApi({
      "GET /api/v1/issues/i1/watch": { watching: false, watchers: 0 },
      "PUT /api/v1/issues/i1/watch": { watching: true, watchers: 1 },
    });
    const { user } = renderWithProviders(<WatchButton subject="issues" id="i1" />);

    const button = await screen.findByRole("button", { name: /Watch/ });
    expect(button).toHaveAttribute("aria-pressed", "false");
    await user.click(button);
    expect(await screen.findByRole("button", { name: /Watching/ })).toHaveAttribute("aria-pressed", "true");
    expect(calls.some((c) => c.method === "PUT" && c.path === "/api/v1/issues/i1/watch")).toBe(true);
  });
});
