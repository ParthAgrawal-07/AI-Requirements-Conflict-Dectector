import { afterEach, describe, expect, it, vi } from "vitest";
import { CLEAN_RESULT, ResultCard } from "../src/features/channels/ResultCard";
import type { Message } from "../src/features/channels/api";
import type { AnalysisRun } from "../src/features/channels/runs";
import { OwnershipRequestDialog } from "../src/features/requirements/OwnershipRequestDialog";
import { mockApi, renderWithProviders, screen, waitFor } from "./test-utils";

vi.mock("../src/app/auth", async (original) => ({
  ...(await original<typeof import("../src/app/auth")>()),
  useAuth: () => ({
    user: { id: "u-me", full_name: "Me" },
    token: "t",
    loading: false,
  }),
}));

afterEach(() => vi.unstubAllGlobals());

const card = (overrides: Partial<Message> = {}): Message => ({
  id: "m-card",
  channel_id: "c1",
  parent_id: "m-post",
  kind: "analysis_card",
  body: "Analysis of REQ-031: plain-text fallback",
  author: null,
  payload: {
    run_id: "run-1",
    requirement_id: "r31",
    label: "REQ-031",
    status: "done",
  },
  mentions: [],
  created_at: "2026-11-21T10:42:00Z",
  edited_at: null,
  deleted: false,
  reply_count: 0,
  last_reply_at: null,
  cursor: "c",
  ...overrides,
});

const run = (overrides: Partial<AnalysisRun> = {}): AnalysisRun => ({
  id: "run-1",
  project_id: "p1",
  scope: "requirement",
  subject_id: "r31",
  status: "done",
  pairs_total: 1,
  pairs_failed: 0,
  checks_total: 1,
  checks_failed: 0,
  error_message: null,
  created_at: "2026-11-21T10:42:00Z",
  finished_at: "2026-11-21T10:42:14Z",
  findings: [],
  ...overrides,
});

const CONFLICT = {
  id: "f1",
  project_id: "p1",
  source: "AI" as const,
  category: "Conflicting" as const,
  status: "flagged" as const,
  severity: "high" as const,
  confidence: 0.86,
  confidence_percent: 86,
  low_confidence: false,
  explanation: "REQ-031 sets 5 minutes, REQ-014 sets 30 minutes.",
  evidence_spans: [],
  requirements: [
    {
      id: "r14",
      label: "REQ-014",
      body: "x",
      state: "Approved" as const,
      is_protected: false,
      origin: "document" as const,
      section_heading: null,
      location: null,
      document_id: "d",
      origin_message_id: null,
    },
    {
      id: "r31",
      label: "REQ-031",
      body: "y",
      state: "Proposed" as const,
      is_protected: false,
      origin: "post" as const,
      section_heading: null,
      location: null,
      document_id: null,
      origin_message_id: "m-post",
    },
  ],
  dependency_direction: null,
  vague_terms: [],
  missing_information: [],
  context_version: 1,
  prompt_version: "v2",
  analysis_run_id: "run-1",
  created_at: "2026-11-21T10:42:10Z",
  clarification: {
    id: "c1",
    finding_id: "f1",
    question: "Which inactivity limit applies, 5 or 30 minutes?",
    addressed_to: "owner",
    answered: false,
    resolution: null,
    resolved_by: null,
    resolved_at: null,
  },
};

const ROUTE = "/w/w1/p/p1/channels/c1";
const PATH = "/w/:workspaceId/p/:projectId/channels/:channelId";

describe("ResultCard", () => {
  it("lists each finding with the other requirement, severity, confidence and question", async () => {
    mockApi({
      "GET /api/v1/analysis-runs/run-1": run({ findings: [CONFLICT] }),
    });
    renderWithProviders(<ResultCard message={card()} />, {
      route: ROUTE,
      path: PATH,
    });

    expect(await screen.findByText("Conflicting with REQ-014")).toBeInTheDocument();
    expect(screen.getByText("high")).toBeInTheDocument();
    expect(screen.getByText("86% confidence")).toBeInTheDocument();
    expect(screen.getByText(/Which inactivity limit applies/)).toBeInTheDocument();
    expect(screen.getByText("14 s")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View on map" })).toHaveAttribute(
      "href",
      "/w/w1/p/p1/map?focus=r31",
    );
  });

  it("says a clean result can miss conflicts, never that it is verified", async () => {
    mockApi({ "GET /api/v1/analysis-runs/run-1": run() });
    const { container } = renderWithProviders(<ResultCard message={card()} />, {
      route: ROUTE,
      path: PATH,
    });

    expect(await screen.findByText(new RegExp(CLEAN_RESULT))).toBeInTheDocument();
    expect(container.textContent?.toLowerCase()).not.toMatch(/verified|conflict-free/);
  });

  it("says it is waiting for budget", async () => {
    mockApi({
      "GET /api/v1/analysis-runs/run-1": run({
        status: "waiting_budget",
        finished_at: null,
      }),
    });
    renderWithProviders(<ResultCard message={card()} />, {
      route: ROUTE,
      path: PATH,
    });

    expect(await screen.findByText("Waiting for budget")).toBeInTheDocument();
    expect(screen.getByText(/resumes automatically/)).toBeInTheDocument();
  });

  it("gives a readable reason when the analysis could not finish", async () => {
    mockApi({
      "GET /api/v1/analysis-runs/run-1": run({
        error_message: "No LLM is configured: candidate pairs were found but not classified.",
      }),
    });
    renderWithProviders(<ResultCard message={card()} />, {
      route: ROUTE,
      path: PATH,
    });

    expect(
      await screen.findByText(/Analysis could not finish: No LLM is configured/),
    ).toBeInTheDocument();
    expect(screen.queryByText(new RegExp(CLEAN_RESULT))).toBeNull();
  });

  it("falls back to the card's text when the run cannot be read", async () => {
    mockApi({});
    renderWithProviders(<ResultCard message={card()} />, {
      route: ROUTE,
      path: PATH,
    });

    expect(await screen.findByText("Analysis of REQ-031: plain-text fallback")).toBeInTheDocument();
  });
});

describe("OwnershipRequestDialog", () => {
  const requirement = {
    requirement_id: "r31",
    source_req_id: "REQ-031",
    owner_id: "u-riya",
    owner_name: "Riya",
    stakeholder_group: "Security",
  };

  it("lets a contributor ask to own a requirement", async () => {
    const { calls } = mockApi({
      "GET /api/v1/requirements/r31/ownership-requests": [],
      "POST /api/v1/requirements/r31/ownership-requests": [201, { id: "o1" }],
    });
    const { user } = renderWithProviders(
      <OwnershipRequestDialog
        open
        onClose={() => undefined}
        projectId="p1"
        requirement={requirement}
        canRequest
        canManage={false}
        names={new Map()}
      />,
    );

    await user.type(screen.getByLabelText(/Why should you own it/), "I run the session tests");
    await user.click(screen.getByRole("button", { name: "Request ownership" }));

    await waitFor(() =>
      expect(
        calls.some(
          (c) =>
            c.method === "POST" && JSON.parse(String(c.body)).note === "I run the session tests",
        ),
      ).toBe(true),
    );
  });

  it("lets the owner accept a pending request", async () => {
    const { calls } = mockApi({
      "GET /api/v1/requirements/r31/ownership-requests": [
        {
          id: "o1",
          requirement_id: "r31",
          requester_id: "u-arjun",
          status: "pending",
          note: null,
          decided_by: null,
          decided_at: null,
          created_at: "x",
        },
      ],
      "POST /api/v1/ownership-requests/o1/decision": {
        id: "o1",
        status: "accepted",
      },
    });
    const { user } = renderWithProviders(
      <OwnershipRequestDialog
        open
        onClose={() => undefined}
        projectId="p1"
        requirement={{ ...requirement, owner_id: "u-me" }}
        canRequest
        canManage={false}
        names={new Map([["u-arjun", "Arjun"]])}
      />,
    );

    await user.click(await screen.findByRole("button", { name: "Accept" }));

    await waitFor(() =>
      expect(calls.some((c) => c.path === "/api/v1/ownership-requests/o1/decision")).toBe(true),
    );
    expect(screen.queryByRole("button", { name: "Request ownership" })).toBeNull(); // the owner
  });
});
