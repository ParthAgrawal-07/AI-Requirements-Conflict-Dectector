import { afterEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent } from "@testing-library/react";
import { ComposerPage, AUTOSAVE_MS } from "../src/features/composer/ComposerPage";
import type { EarsTemplate } from "../src/features/composer/api";
import { cleanFields, EMPTY_FIELDS, incompleteCriteria } from "../src/features/composer/api";
import { missingSlots, renderStatement } from "../src/features/composer/ears";
import { mockApi, renderWithProviders, screen, waitFor, within } from "./test-utils";

vi.mock("../src/app/auth", async (original) => ({
  ...(await original<typeof import("../src/app/auth")>()),
  useAuth: () => ({
    user: { id: "u-me", full_name: "Me" },
    token: "t",
    loading: false,
  }),
}));

const TEMPLATES: EarsTemplate[] = [
  {
    template: "ubiquitous",
    chip: "Always",
    pattern: "The {system} shall {response}.",
    slots: [
      { key: "system", label: "System", placeholder: "mobile app" },
      { key: "response", label: "Response", placeholder: "log the user out" },
    ],
    example: "The mobile app shall encrypt stored card numbers.",
  },
  {
    template: "event_driven",
    chip: "When…",
    pattern: "When {trigger}, the {system} shall {response}.",
    slots: [
      {
        key: "trigger",
        label: "Trigger",
        placeholder: "the user is inactive for 5 minutes",
      },
      { key: "system", label: "System", placeholder: "mobile app" },
      { key: "response", label: "Response", placeholder: "log the user out" },
    ],
    example: "When the user is inactive for 5 minutes, the mobile app shall log the user out.",
  },
];
const EVENT = TEMPLATES[1];
const permissions = (granted: string[]) => ({
  workspace_id: "w1",
  project_id: "p1",
  role: { id: "r", name: "Developer", is_default: true },
  permissions: granted,
  protected_only: [],
});
const ROUTE = "/w/w1/p/p1/requirements/new";
const PATH = "/w/:workspaceId/p/:projectId/requirements/new";

function api(granted = ["view", "req.propose"], extra: Record<string, unknown> = {}) {
  return mockApi({
    "GET /api/v1/me/permissions?project=p1": permissions(granted),
    "GET /api/v1/composer/templates": TEMPLATES,
    "GET /api/v1/workspaces/w1/members": [],
    "GET /api/v1/projects/p1/channels": [],
    "GET /api/v1/me/drafts": [],
    ...extra,
  });
}

async function fillEvent(user: ReturnType<typeof renderWithProviders>["user"]) {
  await user.type(await screen.findByLabelText("Trigger"), "the user is inactive for 5 minutes");
  await user.type(screen.getByLabelText("System"), "The mobile app");
  await user.type(screen.getByLabelText("Response"), "shall log the user out.");
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("the EARS preview mirrors the backend", () => {
  it("drops the words the pattern supplies and its own punctuation", () => {
    expect(
      renderStatement(EVENT, {
        trigger: "  the user  is inactive for 5 minutes, ",
        system: "The mobile app",
        response: "shall log the user out.",
      }),
    ).toBe("When the user is inactive for 5 minutes, the mobile app shall log the user out.");
  });

  it("is null and names the missing slots while one is empty", () => {
    expect(renderStatement(EVENT, { trigger: "x", system: " " })).toBeNull();
    expect(missingSlots(EVENT, { trigger: "x", system: " " })).toEqual(["System", "Response"]);
  });

  const written = {
    ...EMPTY_FIELDS,
    slots: {
      trigger: "x",
      system: "",
      state: "left over from another template",
    },
    tags: [" a ", ""],
    acceptance_criteria: [
      { given: "g", when: "w", then: "t" },
      { given: "g", when: "", then: "" },
      { given: "", when: "", then: "" },
    ],
  };

  it("sends only the chosen template's non-empty slots", () => {
    const cleaned = cleanFields(written, EVENT, { draft: true });
    expect(cleaned.slots).toEqual({ trigger: "x" });
    expect(cleaned.tags).toEqual(["a"]);
  });

  it("keeps half-written criteria in a draft but only whole ones in a proposal", () => {
    expect(cleanFields(written, EVENT, { draft: true }).acceptance_criteria).toHaveLength(2);
    expect(cleanFields(written, EVENT, { draft: false }).acceptance_criteria).toHaveLength(1);
    expect(incompleteCriteria(written)).toEqual([2]);
  });
});

describe("ComposerPage", () => {
  it("shows the sentence as it is written and proposes it", async () => {
    const { calls } = api(undefined, {
      "POST /api/v1/projects/p1/requirements": [
        201,
        {
          message: { channel_id: "c-general" },
          requirement: { source_req_id: "REQ-061" },
          analysis_run_id: "run-1",
        },
      ],
    });
    const { user } = renderWithProviders(<ComposerPage />, {
      route: ROUTE,
      path: PATH,
    });

    await fillEvent(user);

    expect(
      screen.getByText(
        "When the user is inactive for 5 minutes, the mobile app shall log the user out.",
      ),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /propose requirement/i }));
    await waitFor(() => expect(screen.getByText("navigated away")).toBeInTheDocument());
    const posted = calls.find(
      (c) => c.method === "POST" && c.path === "/api/v1/projects/p1/requirements",
    );
    const body = JSON.parse(String(posted?.body));
    expect(body.fields).toMatchObject({
      template: "event_driven",
      type: "functional",
      priority: "must",
      owner_id: null,
      slots: {
        trigger: "the user is inactive for 5 minutes",
        system: "The mobile app",
        response: "shall log the user out.",
      },
    });
    expect(body.draft_id).toBeNull();
  });

  it("cannot propose until every slot is filled", async () => {
    api();
    const { user } = renderWithProviders(<ComposerPage />, {
      route: ROUTE,
      path: PATH,
    });

    await user.type(await screen.findByLabelText("Trigger"), "the user is inactive");

    expect(screen.getByRole("button", { name: /propose requirement/i })).toBeDisabled();
    expect(screen.getByText(/Fill in: System, Response/)).toBeInTheDocument();
  });

  it("saves a private draft every 5 seconds while there are changes", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { calls } = api(undefined, {
      "POST /api/v1/me/drafts": [
        201,
        {
          id: "d1",
          project_id: "p1",
          fields: EMPTY_FIELDS,
          preview: null,
          updated_at: "x",
        },
      ],
      "PATCH /api/v1/me/drafts/d1": {
        id: "d1",
        project_id: "p1",
        fields: EMPTY_FIELDS,
        preview: null,
        updated_at: "y",
      },
    });
    renderWithProviders(<ComposerPage />, { route: ROUTE, path: PATH });
    const trigger = await screen.findByLabelText("Trigger");

    fireEvent.change(trigger, { target: { value: "the user is inactive" } });
    await act(async () => {
      vi.advanceTimersByTime(AUTOSAVE_MS);
    });
    await waitFor(() => expect(screen.getByText("Draft saved ✓")).toBeInTheDocument());
    fireEvent.change(trigger, {
      target: { value: "the user is inactive for 5 minutes" },
    });
    await act(async () => {
      vi.advanceTimersByTime(AUTOSAVE_MS);
    });

    await waitFor(() =>
      expect(
        calls
          .filter((c) => c.path.startsWith("/api/v1/me/drafts") && c.method !== "GET")
          .map((c) => c.method),
      ).toEqual(["POST", "PATCH"]),
    );
    const created = JSON.parse(String(calls.find((c) => c.method === "POST")?.body));
    expect(created).toMatchObject({
      project_id: "p1",
      fields: { slots: { trigger: "the user is inactive" } },
    });
  });

  it("saves one draft at a time and keeps edits made during a save unsaved", async () => {
    const draft = {
      id: "d1",
      project_id: "p1",
      fields: EMPTY_FIELDS,
      preview: null,
      updated_at: "x",
    };
    const { calls } = api(undefined, {
      "POST /api/v1/me/drafts": [201, draft],
    });
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => (release = resolve));
    const fetchMock = vi.mocked(fetch);
    const original = fetchMock.getMockImplementation()!;
    fetchMock.mockImplementation(async (input, init) => {
      if (init?.method === "POST" && String(input).endsWith("/me/drafts")) await gate;
      return original(input, init);
    });
    const { user } = renderWithProviders(<ComposerPage />, {
      route: ROUTE,
      path: PATH,
    });
    const trigger = await screen.findByLabelText("Trigger");
    fireEvent.change(trigger, { target: { value: "the user is inactive" } });

    await user.click(screen.getByRole("button", { name: "Save draft" }));
    fireEvent.change(trigger, {
      target: { value: "the user is inactive for 5 minutes" },
    });
    await user.click(screen.getByRole("button", { name: "Save draft" })); // ignored: one in flight
    release();

    await waitFor(() => expect(screen.getByText("Unsaved changes")).toBeInTheDocument());
    expect(calls.filter((c) => c.method === "POST" && c.path === "/api/v1/me/drafts")).toHaveLength(
      1,
    );
  });

  it("will not propose with a half-written criterion and says which", async () => {
    api();
    const { user } = renderWithProviders(<ComposerPage />, {
      route: ROUTE,
      path: PATH,
    });
    await fillEvent(user);

    await user.click(screen.getByRole("button", { name: "+ Criterion" }));
    await user.type(
      within(screen.getByRole("group", { name: "Criterion 1" })).getByLabelText("Given"),
      "a session",
    );

    expect(screen.getByRole("button", { name: /propose requirement/i })).toBeDisabled();
    expect(screen.getByText("Finish or remove criterion 1 to propose.")).toBeInTheDocument();
  });

  it("shows similar requirements as hints, not verdicts", async () => {
    api(undefined, {
      "POST /api/v1/projects/p1/similar": {
        hints: [
          {
            requirement_id: "r14",
            label: "REQ-014",
            state: "Approved",
            preview: "Session timeout after 30 minutes of inactivity",
            similarity: 0.88,
          },
        ],
      },
    });
    const { user } = renderWithProviders(<ComposerPage />, {
      route: ROUTE,
      path: PATH,
    });

    await fillEvent(user);

    expect(await screen.findByText("REQ-014", {}, { timeout: 3000 })).toBeInTheDocument();
    expect(screen.getByText("88% alike")).toBeInTheDocument();
  });

  it("gives a viewer no composer at all", async () => {
    api(["view"]);
    renderWithProviders(<ComposerPage />, { route: ROUTE, path: PATH });

    expect(await screen.findByText(/cannot propose requirements/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /propose requirement/i })).toBeNull();
    expect(screen.queryByLabelText("Trigger")).toBeNull();
  });
});
