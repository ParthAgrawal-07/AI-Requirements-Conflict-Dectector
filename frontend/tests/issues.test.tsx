import { afterEach, describe, expect, it, vi } from "vitest";
import { IssueList } from "../src/features/issues/IssueList";
import { IssuePage } from "../src/features/issues/IssuePage";
import { RaiseConcernDialog } from "../src/features/issues/RaiseConcernDialog";
import { sourceOf, type Issue } from "../src/features/issues/api";
import { mockApi, renderWithProviders, screen, waitFor, within } from "./test-utils";

vi.mock("../src/app/auth", async (original) => ({
  ...(await original<typeof import("../src/app/auth")>()),
  useAuth: () => ({ user: { id: "u-me", full_name: "Me" }, token: "t", loading: false }),
}));

afterEach(() => vi.unstubAllGlobals());

const issue = (overrides: Partial<Issue> = {}): Issue => ({
  id: "i1",
  project_id: "p1",
  number: 1,
  key: "ISS-1",
  title: "Conflict between REQ-014 and REQ-031",
  body: "REQ-014 and REQ-031 set different inactivity limits.",
  status: "open",
  close_reason: null,
  auto: true,
  finding_id: "f1",
  author: null,
  labels: ["conflicting", "severity:high", "auto"],
  assignees: [
    { id: "u-asha", full_name: "Asha" },
    { id: "u-ravi", full_name: "Ravi" },
  ],
  requirements: [
    { id: "r14", label: "REQ-014", state: "Approved", owner_id: "u-asha" },
    { id: "r31", label: "REQ-031", state: "Proposed", owner_id: "u-ravi" },
  ],
  comment_count: 1,
  created_at: "2026-12-05T10:00:00Z",
  updated_at: "2026-12-05T10:00:00Z",
  closed_at: null,
  closed_by: null,
  ...overrides,
});
const CONCERN = issue({
  id: "i2",
  number: 2,
  key: "ISS-2",
  title: "Concern: Conflicting — REQ-020 and REQ-044",
  auto: false,
  author: { id: "u-me", full_name: "Me" },
  labels: ["concern", "conflicting", "severity:medium"],
  comment_count: 0,
});
const page = (items: Issue[]) => ({ items, total: items.length, limit: 25, offset: 0 });
const permissions = (granted: string[]) => ({
  workspace_id: "w1",
  project_id: "p1",
  role: { id: "r", name: "Analyst", is_default: true },
  permissions: granted,
  protected_only: [],
});
const LIST = "/w/w1/p/p1/issues";
const LIST_PATH = "/w/:workspaceId/p/:projectId/issues";
const requirements = {
  items: [
    { requirement_id: "r14", source_req_id: "REQ-014", body: "Sessions end after 30 minutes." },
    { requirement_id: "r31", source_req_id: "REQ-031", body: "Sessions end after 5 minutes." },
  ],
  total: 2,
  limit: 200,
  offset: 0,
};

describe("sourceOf", () => {
  it("reads who found it from the issue", () => {
    expect(sourceOf(issue())).toBe("AI");
    expect(sourceOf(CONCERN)).toBe("Person");
    expect(sourceOf(issue({ auto: false, labels: ["ux"] }))).toBeNull();
  });
});

describe("IssueList", () => {
  it("shows open issues with who found them, their requirements and assignees", async () => {
    const { calls } = mockApi({
      "GET /api/v1/projects/p1/issues": page([issue(), CONCERN]),
      "GET /api/v1/me/permissions?project=p1": permissions(["view", "issue.open"]),
    });
    renderWithProviders(<IssueList />, { route: LIST, path: LIST_PATH });

    const first = (await screen.findByText("ISS-1")).closest("li") as HTMLElement;
    expect(within(first).getByTitle(/Found by AI analysis/)).toHaveTextContent("AI");
    expect(within(first).getByText(/REQ-014, REQ-031 · assigned to Asha, Ravi · 1 comment/)).toBeInTheDocument();
    const second = screen.getByText("ISS-2").closest("li") as HTMLElement;
    expect(within(second).getByTitle("Raised by a person")).toHaveTextContent("Person");
    expect(calls.find((c) => c.path.includes("/issues"))?.path).toContain("status=open");
  });

  it("filters on the server by status and by 'assigned to me'", async () => {
    const { calls } = mockApi({
      "GET /api/v1/projects/p1/issues": page([]),
      "GET /api/v1/me/permissions?project=p1": permissions(["view"]),
    });
    const { user } = renderWithProviders(<IssueList />, { route: LIST, path: LIST_PATH });
    await screen.findByText(/No issues here/);

    await user.click(screen.getByRole("button", { name: "Closed" }));
    await user.click(screen.getByRole("button", { name: "Assigned to me" }));

    await waitFor(() =>
      expect(calls.some((c) => c.path.includes("status=closed") && c.path.includes("assignee=u-me"))).toBe(true),
    );
    expect(screen.queryByRole("button", { name: "New issue" })).not.toBeInTheDocument(); // a viewer
  });

  it("opens a new issue about chosen requirements", async () => {
    const { calls } = mockApi({
      "GET /api/v1/projects/p1/issues": page([]),
      "GET /api/v1/me/permissions?project=p1": permissions(["view", "issue.open"]),
      "GET /api/v1/projects/p1/requirements": requirements,
      "POST /api/v1/projects/p1/issues": [201, issue({ auto: false, number: 3, key: "ISS-3", id: "i3" })],
    });
    const { user } = renderWithProviders(<IssueList />, { route: LIST, path: LIST_PATH });

    await user.click(await screen.findByRole("button", { name: "New issue" }));
    await user.type(screen.getByLabelText("Title"), "Which timeout?");
    await user.selectOptions(await screen.findByLabelText("Requirements it is about"), ["r14", "r31"]);
    await user.type(screen.getByLabelText(/Labels/), "sessions, ux");
    await user.click(screen.getByRole("button", { name: "Open issue" }));

    await waitFor(() => expect(screen.getByText("navigated away")).toBeInTheDocument());
    const posted = calls.find((c) => c.method === "POST");
    expect(JSON.parse(String(posted?.body))).toEqual({
      title: "Which timeout?",
      body: "",
      requirement_ids: ["r14", "r31"],
      labels: ["sessions", "ux"],
    });
  });
});

describe("IssuePage", () => {
  const PAGE_ROUTE = "/w/w1/p/p1/issues/i1";
  const PAGE_PATH = "/w/:workspaceId/p/:projectId/issues/:issueId";

  it("shows the discussion, with the app's question, and posts a comment", async () => {
    const { calls } = mockApi({
      "GET /api/v1/issues/i1": issue(),
      "GET /api/v1/issues/i1/comments": [
        { id: "c1", author: null, body: "Clarification question: 5 or 30 minutes?", created_at: "2026-12-05T10:01:00Z" },
      ],
      "GET /api/v1/me/permissions?project=p1": permissions(["view", "issue.open"]),
      "GET /api/v1/workspaces/w1/members": [],
      "POST /api/v1/issues/i1/comments": [201, { id: "c2", author: { id: "u-me", full_name: "Me" }, body: "5", created_at: "x" }],
    });
    const { user } = renderWithProviders(<IssuePage />, { route: PAGE_ROUTE, path: PAGE_PATH });

    expect(await screen.findByText("Clarification question: 5 or 30 minutes?")).toBeInTheDocument();
    expect(screen.getByText("RCD")).toBeInTheDocument();
    expect(screen.getByText(/Opened automatically/)).toBeInTheDocument();
    await user.type(screen.getByLabelText("Comment"), "Five minutes, as the bank asks.");
    await user.click(screen.getByRole("button", { name: "Comment" }));

    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST")?.body).toBe(JSON.stringify({ body: "Five minutes, as the bank asks." })),
    );
  });

  it("offers Propose change on each requirement, resolving the issue (US-33)", async () => {
    mockApi({
      "GET /api/v1/issues/i1": issue(),
      "GET /api/v1/issues/i1/comments": [],
      "GET /api/v1/me/permissions?project=p1": permissions(["view", "issue.open", "rcr.open"]),
      "GET /api/v1/workspaces/w1/members": [],
    });
    renderWithProviders(<IssuePage />, { route: PAGE_ROUTE, path: PAGE_PATH });

    const links = await screen.findAllByRole("link", { name: "Propose change" });
    expect(links.map((link) => link.getAttribute("href"))).toEqual([
      "/w/w1/p/p1/changes/new?requirement=r14&resolves=1",
      "/w/w1/p/p1/changes/new?requirement=r31&resolves=1",
    ]);
  });

  it("closes the issue", async () => {
    const { calls } = mockApi({
      "GET /api/v1/issues/i1": issue(),
      "GET /api/v1/issues/i1/comments": [],
      "GET /api/v1/me/permissions?project=p1": permissions(["view", "issue.open"]),
      "GET /api/v1/workspaces/w1/members": [],
      "PATCH /api/v1/issues/i1": issue({ status: "closed", close_reason: "manual" }),
    });
    const { user } = renderWithProviders(<IssuePage />, { route: PAGE_ROUTE, path: PAGE_PATH });

    await user.click(await screen.findByRole("button", { name: "Close issue" }));

    await waitFor(() => expect(calls.find((c) => c.method === "PATCH")?.body).toBe(JSON.stringify({ status: "closed" })));
    expect(await screen.findByText("ISS-1 closed")).toBeInTheDocument();
  });

  it("lets only an issue manager edit labels and assignees", async () => {
    const { calls } = mockApi({
      "GET /api/v1/issues/i1": issue(),
      "GET /api/v1/issues/i1/comments": [],
      "GET /api/v1/me/permissions?project=p1": permissions(["view", "issue.open", "issue.manage"]),
      "GET /api/v1/workspaces/w1/members": [
        { user: { id: "u-asha", full_name: "Asha", email: "a@x" }, role: { id: "r", name: "BA", is_default: true }, stakeholder_group: null, joined_at: "x" },
      ],
      "PATCH /api/v1/issues/i1": issue(),
    });
    const { user } = renderWithProviders(<IssuePage />, { route: PAGE_ROUTE, path: PAGE_PATH });

    await user.click(await screen.findByRole("button", { name: "Edit labels and assignees" }));
    const labels = screen.getByLabelText("Labels");
    await user.clear(labels);
    await user.type(labels, "sessions");
    await user.selectOptions(screen.getByLabelText("Assignees"), ["u-asha"]);
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(JSON.parse(String(calls.find((c) => c.method === "PATCH")?.body))).toEqual({
        labels: ["sessions"],
        assignee_ids: ["u-asha"],
      }),
    );
  });
});

describe("RaiseConcernDialog", () => {
  it("asks for two requirements for a conflict and posts the concern", async () => {
    const { calls } = mockApi({
      "GET /api/v1/projects/p1/requirements": requirements,
      "POST /api/v1/projects/p1/concerns": [201, { finding: {}, issue_id: "i9", issue_key: "ISS-9", ai_miss: true }],
    });
    const onRaised = vi.fn();
    const { user } = renderWithProviders(
      <RaiseConcernDialog open onClose={() => undefined} projectId="p1" requirementId="r14" onRaised={onRaised} />,
    );

    const submit = await screen.findByRole("button", { name: "Raise concern" });
    await user.type(screen.getByLabelText("Explain it"), "Thirty and five minutes cannot both hold.");
    expect(submit).toBeDisabled(); // the second requirement is missing
    await user.selectOptions(await screen.findByLabelText("Second requirement"), "r31");
    await user.type(screen.getByLabelText(/What it is based on/), "Contract §7.2");
    await user.selectOptions(screen.getByLabelText("Severity"), "high");
    await user.click(submit);

    await waitFor(() => expect(onRaised).toHaveBeenCalled());
    expect(JSON.parse(String(calls.find((c) => c.method === "POST")?.body))).toEqual({
      category: "Conflicting",
      requirement_ids: ["r14", "r31"],
      explanation: "Thirty and five minutes cannot both hold.",
      external_ref: "Contract §7.2",
      severity: "high",
    });
    expect(await screen.findByText("ISS-9 opened — the analysis had not reported this")).toBeInTheDocument();
  });

  it("needs one requirement for wording", async () => {
    mockApi({ "GET /api/v1/projects/p1/requirements": requirements });
    const { user } = renderWithProviders(<RaiseConcernDialog open onClose={() => undefined} projectId="p1" requirementId="r14" />);

    await user.selectOptions(await screen.findByLabelText("What is wrong?"), "Ambiguous");

    expect(screen.queryByLabelText("Second requirement")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Requirement")).toHaveValue("r14");
  });
});
