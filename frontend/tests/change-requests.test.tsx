import { QueryClient } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { applyEvent } from "../src/app/socket";
import { ChangeEditor } from "../src/features/changes/ChangeEditor";
import { ChangeRequestPage } from "../src/features/changes/ChangeRequestPage";
import { ChecksTab } from "../src/features/changes/ChecksTab";
import { DiffView } from "../src/features/changes/DiffView";
import type { ChangeRequest, Checks, Review, Reviews } from "../src/features/changes/api";
import { mockApi, renderWithProviders, screen, waitFor, within } from "./test-utils";

vi.mock("../src/app/auth", async (original) => ({
  ...(await original<typeof import("../src/app/auth")>()),
  useAuth: () => ({ user: { id: "u-me", full_name: "Me" }, token: "t", loading: false }),
}));

afterEach(() => vi.unstubAllGlobals());

// The sample request of the Detailed Sprint Guide (fixtures/rcr_sample.json): REQ-014's
// inactivity timeout 30 → 10 minutes, resolving the auto conflict issue ISS-12.
const change = (overrides: Partial<ChangeRequest> = {}): ChangeRequest => ({
  id: "cr1",
  project_id: "p1",
  number: 34,
  key: "RCR-34",
  requirement: { id: "r14", label: "REQ-014", state: "Approved", current_version: 2, is_protected: false, owner_id: "u-riya" },
  kind: "modify",
  status: "open",
  base_version: 2,
  proposal_revision: 1,
  proposed_body: "When the user is inactive for 10 minutes, the system shall end the session.",
  base_body: "When the user is inactive for 30 minutes, the system shall end the session.",
  current_body: "When the user is inactive for 30 minutes, the system shall end the session.",
  reason: "Audit finding A-17: idle sessions must end within 10 minutes",
  proposer: { id: "u-arjun", full_name: "Arjun" },
  resolves: [{ id: "i12", key: "ISS-12", title: "Conflict between REQ-014 and REQ-031", status: "open" }],
  merged_version: null,
  merged_at: null,
  closed_at: null,
  close_reason: null,
  created_at: "2026-12-10T09:00:00Z",
  updated_at: "2026-12-10T09:00:00Z",
  ...overrides,
});
const review = (overrides: Partial<Review> = {}): Review => ({
  id: "rv1",
  reviewer: { id: "u-riya", full_name: "Riya" },
  decision: "approve",
  rationale: null,
  proposal_revision: 1,
  reviewed_base_version: 2,
  dismissed: false,
  comments: [],
  created_at: "2026-12-10T10:00:00Z",
  ...overrides,
});
const REVIEWS: Reviews = {
  requests: [
    { reviewer: { id: "u-riya", full_name: "Riya" }, required: true, reason: "owner", approved: true },
    { reviewer: { id: "u-meera", full_name: "Meera" }, required: true, reason: "direct_conflict", approved: false },
  ],
  reviews: [review({ id: "rv0", proposal_revision: 0, dismissed: true, created_at: "2026-12-10T09:30:00Z" }), review()],
};
const CHECKS: Checks = {
  state: "done",
  stale_reasons: [],
  report: {
    id: "rep1",
    proposal_revision: 1,
    base_version: 2,
    baseline_revision: 4,
    risk_level: "medium",
    risk_reasons: ["3–10 requirements affected"],
    affected: [
      { requirement_id: "r31", label: "REQ-031", depth: 1, relation: "conflict_partner", reason: "Conflicting finding", status: "confirmed", owner_id: "u-meera", stakeholder_group: null, is_protected: false, finding_id: "f1", path: ["REQ-014", "REQ-031"] },
      { requirement_id: "r40", label: "REQ-040", depth: 2, relation: "semantic_similarity", reason: "Shares a constraint", status: "potential", owner_id: null, stakeholder_group: null, is_protected: true, finding_id: null, path: ["REQ-014", "REQ-031", "REQ-040"] },
    ],
    checks: [
      { key: "conflicts", title: "Conflicts", status: "pass", message: "Resolves the conflict with REQ-031", details: {} },
      { key: "duplicates", title: "Duplicates", status: "warning", message: "1 possible duplicate", details: { labels: ["REQ-077"] } },
      { key: "protected", title: "Protected", status: "info", message: "Nothing protected is touched directly", details: {} },
    ],
    findings_delta: {
      resolved: [{ finding_id: "f1", category: "Conflicting", requirement_ids: ["r14", "r31"], labels: ["REQ-014", "REQ-031"], source: "ai", reason: "No longer holds with the new text" }],
      new: [],
      still_open: [],
      must_rerun: [{ finding_id: null, category: "semantic_similarity", requirement_ids: ["r14", "r40"], labels: ["REQ-014", "REQ-040"], source: "ai", reason: "Two steps away through REQ-031: re-run before approving" }],
    },
    narrative: { label: "AI", summary: "Shortening the timeout resolves the conflict with REQ-031.", points: [], cited_ids: ["REQ-031"], prompt_version: "v1", model: "gemini-2.5-flash" },
    is_stale: false,
    llm_calls: 1,
    created_at: "2026-12-10T09:01:00Z",
  },
};
const permissions = (granted: string[]) => ({
  workspace_id: "w1",
  project_id: "p1",
  role: { id: "r", name: "Analyst", is_default: true },
  permissions: granted,
  protected_only: [],
});
const MEMBERS = [
  { user: { id: "u-riya", full_name: "Riya", email: "r@x" }, role: { id: "r", name: "PM" }, stakeholder_group: null, joined_at: "2026-11-01T00:00:00Z" },
  { user: { id: "u-meera", full_name: "Meera", email: "m@x" }, role: { id: "r", name: "Analyst" }, stakeholder_group: null, joined_at: "2026-11-01T00:00:00Z" },
];
const PAGE = "/w/w1/p/p1/changes/cr1";
const PAGE_PATH = "/w/:workspaceId/p/:projectId/changes/:changeRequestId";
const pageApi = (granted: string[], overrides: Record<string, unknown> = {}) =>
  mockApi({
    "GET /api/v1/change-requests/cr1": change(),
    "GET /api/v1/change-requests/cr1/reviews": REVIEWS,
    "GET /api/v1/change-requests/cr1/checks": CHECKS,
    "GET /api/v1/change-requests/cr1/agreement": { mergeable: true, unmet: [] },
    "GET /api/v1/me/permissions?project=p1": permissions(granted),
    "GET /api/v1/workspaces/w1/members": MEMBERS,
    ...overrides,
  });

describe("ChangeEditor", () => {
  const EDITOR = "/w/w1/p/p1/changes/new?requirement=r14&resolves=12";
  const EDITOR_PATH = "/w/:workspaceId/p/:projectId/changes/new";
  const requirement = {
    requirement_id: "r14",
    project_id: "p1",
    source_req_id: "REQ-014",
    body: "When the user is inactive for 30 minutes, the system shall end the session.",
    current_version: 2,
    is_protected: true,
    owner_id: "u-riya",
    state: "Approved",
  };
  const editorApi = (granted = ["view", "rcr.open"]) =>
    mockApi({
      "GET /api/v1/requirements/r14": requirement,
      "GET /api/v1/me/permissions?project=p1": permissions(granted),
      "GET /api/v1/projects/p1/issues": { items: [{ id: "i12", number: 12, key: "ISS-12", title: "Conflict between REQ-014 and REQ-031" }], total: 1, limit: 50, offset: 0 },
      "GET /api/v1/requirements/r14/impact": { requirement_id: "r14", label: "REQ-014", affected: CHECKS.report?.affected, owners: ["u-meera"], stakeholder_groups: [], work_items: [] },
      "GET /api/v1/workspaces/w1/members": MEMBERS,
      "POST /api/v1/requirements/r14/change-requests": [201, change()],
    });

  it("pre-fills the current text, diffs the edit and shows the pre-flight", async () => {
    editorApi();
    const { user } = renderWithProviders(<ChangeEditor />, { route: EDITOR, path: EDITOR_PATH });

    const text = await screen.findByLabelText("Proposed text");
    expect(text).toHaveValue(requirement.body);
    await user.clear(text);
    await user.type(text, "When the user is inactive for 10 minutes, the system shall end the session.");
    const diff = screen.getByLabelText("Your changes");
    expect(within(diff).getByText(/30/, { selector: "del" })).toBeInTheDocument();
    expect(within(diff).getByText(/10/, { selector: "ins" })).toBeInTheDocument();

    expect(await screen.findByLabelText(/ISS-12/)).toBeChecked(); // from ?resolves=12
    const preflight = screen.getByRole("region", { name: "Pre-flight" });
    expect(await within(preflight).findByText(/2 affected requirements \(1 direct, 1 two steps away\)/)).toBeInTheDocument();
    expect(within(preflight).getByText(/Protected: a compliance reviewer must approve/)).toBeInTheDocument();
    expect(await within(preflight).findByText(/Riya · Meera/)).toBeInTheDocument();
  });

  it("opens the request against the version it read, with the issues it resolves", async () => {
    const { calls } = editorApi();
    const { user } = renderWithProviders(<ChangeEditor />, { route: EDITOR, path: EDITOR_PATH });

    const open = await screen.findByRole("button", { name: "Open change request" });
    expect(open).toBeDisabled(); // nothing changed yet
    const text = screen.getByLabelText("Proposed text");
    await user.clear(text);
    await user.type(text, "When the user is inactive for 10 minutes, the system shall end the session.");
    await user.type(screen.getByLabelText("Reason (required)"), "Audit finding A-17");
    await screen.findByLabelText(/ISS-12/);
    await user.click(open);

    await screen.findByText("navigated away");
    const post = calls.find((c) => c.method === "POST");
    expect(JSON.parse(String(post?.body))).toEqual({
      kind: "modify",
      proposed_body: "When the user is inactive for 10 minutes, the system shall end the session.",
      reason: "Audit finding A-17",
      base_version: 2,
      resolves: [12],
      draft: false,
    });
  });

  it("tells a member without rcr.open that they cannot propose", async () => {
    editorApi(["view"]);
    renderWithProviders(<ChangeEditor />, { route: EDITOR, path: EDITOR_PATH });
    expect(await screen.findByRole("alert")).toHaveTextContent("cannot propose changes");
  });
});

describe("ChangeRequestPage", () => {
  it("shows the header, the reviewers and dismissed approvals struck through", async () => {
    pageApi(["view", "rcr.review"]);
    renderWithProviders(<ChangeRequestPage />, { route: PAGE, path: PAGE_PATH });

    expect(await screen.findByRole("heading", { name: /RCR-34 Change REQ-014/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "ISS-12" })).toHaveAttribute("href", "/w/w1/p/p1/issues/i12");
    expect(await screen.findByText("Risk Medium")).toBeInTheDocument();

    const reviewers = screen.getByRole("region", { name: "Reviewers" });
    expect(await within(reviewers).findByText(/approved · owner, required/)).toBeInTheDocument();
    expect(within(reviewers).getByText(/requested · owner of a conflicting requirement, required/)).toBeInTheDocument();

    const conversation = screen.getByRole("region", { name: "Reviews" });
    const dismissed = within(conversation).getByText(/dismissed: the proposal or its base changed since/).closest("li") as HTMLElement;
    expect(within(dismissed).getByText("approved", { selector: "s" })).toBeInTheDocument();
    // A reviewer who is not the proposer gets the form.
    expect(screen.getByRole("form", { name: "Your review" })).toBeInTheDocument();
  });

  it("sends a review with an inline comment picked in Files changed", async () => {
    const { calls } = pageApi(["view", "rcr.review"], { "POST /api/v1/change-requests/cr1/reviews": [201, change()] });
    const { user } = renderWithProviders(<ChangeRequestPage />, { route: PAGE, path: PAGE_PATH });

    await user.click(await screen.findByRole("tab", { name: "Files changed" }));
    const proposal = document.querySelector(".proposal-text") as HTMLElement;
    const textNode = proposal.firstChild as Text;
    const start = textNode.data.indexOf("10 minutes");
    const range = document.createRange();
    range.setStart(textNode, start);
    range.setEnd(textNode, start + "10 minutes".length);
    window.getSelection()?.removeAllRanges();
    window.getSelection()?.addRange(range);
    await user.click(screen.getByRole("button", { name: "Comment on the selected words" }));

    await user.click(screen.getByRole("tab", { name: "Conversation (1 pending)" }));
    await user.type(screen.getByRole("textbox", { name: /On 10 minutes/ }), "Why 10 and not 15?");
    await user.click(screen.getByRole("radio", { name: "Request changes" }));
    await user.type(screen.getByLabelText("What should change?"), "Cite the audit clause");
    await user.click(screen.getByRole("button", { name: "Send review" }));

    await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    const post = calls.find((c) => c.method === "POST");
    expect(JSON.parse(String(post?.body))).toEqual({
      decision: "request_changes",
      rationale: "Cite the audit clause",
      comments: [{ field: "statement", start_offset: start, end_offset: start + 10, body: "Why 10 and not 15?" }],
    });
  });

  it("shows 'needs update' with a three-way view, and the proposer can update the request", async () => {
    const moved = change({
      status: "needs_update",
      proposer: { id: "u-me", full_name: "Me" },
      requirement: { ...change().requirement, current_version: 3 },
      current_body: "When the user is inactive for 15 minutes, the system shall end the session.",
    });
    const { calls } = pageApi(["view", "rcr.open", "rcr.review"], {
      "GET /api/v1/change-requests/cr1": moved,
      "PATCH /api/v1/change-requests/cr1": { ...moved, base_version: 3, proposal_revision: 2, status: "open" },
    });
    const { user } = renderWithProviders(<ChangeRequestPage />, { route: PAGE, path: PAGE_PATH });

    expect(await screen.findByText(/REQ-014 changed to v3 after this request was written against v2/)).toBeInTheDocument();
    // Permissions are loaded once Re-run (needs rcr.review) shows; even then, never your own review.
    await user.click(screen.getByRole("tab", { name: /^Checks/ }));
    expect(await screen.findByRole("button", { name: "Re-run checks" })).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: /^Conversation/ }));
    expect(screen.queryByRole("form", { name: "Your review" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Files changed" }));
    expect(screen.getByText("Changed underneath: v2 → v3")).toBeInTheDocument();
    expect(screen.getByText("Current v3 → proposed")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Update request" }));
    await user.click(within(screen.getByRole("form", { name: "Edit the proposal" })).getByRole("button", { name: "Update request" }));
    await waitFor(() => expect(calls.some((c) => c.method === "PATCH")).toBe(true));
    expect(JSON.parse(String(calls.find((c) => c.method === "PATCH")?.body))).toMatchObject({ rebase: true });
  });
});

describe("MergeBox", () => {
  it("lists every condition with ✓ or ✗ and keeps merge disabled until all pass", async () => {
    pageApi(["view", "rcr.review", "rcr.merge"], {
      "GET /api/v1/change-requests/cr1/agreement": {
        mergeable: false,
        unmet: [{ code: "reviewer_missing", message: "1 required reviewer (owner or conflicting owner) still to approve" }],
      },
    });
    renderWithProviders(<ChangeRequestPage />, { route: PAGE, path: PAGE_PATH });

    const conditions = await screen.findByRole("list", { name: "Agreement conditions" });
    expect(await within(conditions).findByText(/1 required reviewer .* still to approve/)).toBeInTheDocument();
    expect(within(conditions).getByText("Written against the current version")).toBeInTheDocument();
    expect(within(conditions).getAllByText("Not met:")).toHaveLength(1);
    expect(within(conditions).queryByText(/compliance/)).not.toBeInTheDocument(); // not protected
    expect(screen.getByRole("button", { name: "Merge into baseline" })).toBeDisabled();
  });

  it("accepts an open High finding as a risk with a reason", async () => {
    const { calls } = pageApi(["view", "rcr.merge"], {
      "GET /api/v1/change-requests/cr1/agreement": {
        mergeable: false,
        unmet: [{ code: "high_finding_open", message: "1 High-severity finding open on REQ-014" }],
      },
      "POST /api/v1/change-requests/cr1/merge": { ...change(), status: "merged", merged_version: 3 },
    });
    const { user } = renderWithProviders(<ChangeRequestPage />, { route: PAGE, path: PAGE_PATH });

    const merge = await screen.findByRole("button", { name: "Merge into baseline" });
    await user.type(await screen.findByLabelText(/Accept the open High-severity risk/), "Signed off by the CISO");
    expect(merge).toBeEnabled();
    await user.click(merge);
    await waitFor(() => expect(calls.some((c) => c.path.endsWith("/merge"))).toBe(true));
    expect(JSON.parse(String(calls.find((c) => c.path.endsWith("/merge"))?.body))).toEqual({
      accepted_risk_reason: "Signed off by the CISO",
    });
  });

  it("lists the unmet conditions from a 409 merge_blocked", async () => {
    pageApi(["view", "rcr.merge"], {
      "POST /api/v1/change-requests/cr1/merge": [
        409,
        {
          error: {
            code: "merge_blocked",
            message: "This change request cannot be merged yet",
            request_id: null,
            details: [{ code: "needs_update", message: "REQ-014 is at v3; the proposal was written against v2" }],
          },
        },
      ],
    });
    const { user } = renderWithProviders(<ChangeRequestPage />, { route: PAGE, path: PAGE_PATH });

    const merge = await screen.findByRole("button", { name: "Merge into baseline" });
    await waitFor(() => expect(merge).toBeEnabled());
    await user.click(merge);
    const refused = await screen.findByRole("alert");
    expect(refused).toHaveTextContent("The merge was refused");
    expect(refused).toHaveTextContent("REQ-014 is at v3; the proposal was written against v2");
  });

  it("greys merge out with the reason for a member without rcr.merge", async () => {
    pageApi(["view", "rcr.review"]);
    renderWithProviders(<ChangeRequestPage />, { route: PAGE, path: PAGE_PATH });
    const merge = await screen.findByRole("button", { name: "Merge into baseline" });
    expect(merge).toBeDisabled();
    expect(merge).toHaveAttribute("title", "You cannot merge change requests in this project");
    expect(screen.queryByRole("button", { name: "Close without merging…" })).not.toBeInTheDocument();
  });

  it("says what a merged request became", async () => {
    pageApi(["view", "rcr.merge"], {
      "GET /api/v1/change-requests/cr1": change({ status: "merged", merged_version: 3, merged_at: "2026-12-11T09:00:00Z" }),
    });
    renderWithProviders(<ChangeRequestPage />, { route: PAGE, path: PAGE_PATH });
    expect(await screen.findByText("Merged: REQ-014 is now v3.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Merge into baseline" })).not.toBeInTheDocument();
  });
});

describe("ChecksTab", () => {
  it("puts the findings delta first, then each check with an icon and a word, risk and the AI summary", async () => {
    mockApi({ "GET /api/v1/change-requests/cr1/checks": CHECKS });
    renderWithProviders(<ChecksTab changeRequestId="cr1" canRerun={false} />);

    const delta = await screen.findByRole("region", { name: "Findings delta" });
    const counts = within(delta).getAllByRole("list")[0];
    expect(within(counts).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "1 Resolved",
      "0 New",
      "0 Still open",
      "1 Must re-run before approval",
    ]);
    expect(within(delta).getByText(/Two steps away through REQ-031/)).toBeInTheDocument();

    const duplicates = screen.getByText("Duplicates").closest("li") as HTMLElement;
    expect(duplicates).toHaveTextContent("⚠");
    expect(duplicates).toHaveTextContent("Warning");
    expect(duplicates).toHaveTextContent("REQ-077");
    expect(screen.getByText("Medium")).toBeInTheDocument();
    const summary = screen.getByRole("region", { name: "AI summary" });
    expect(summary.querySelector(".badge-ai")).toHaveTextContent("AI");
    expect(within(summary).getByText(/resolves the conflict with REQ-031/)).toBeInTheDocument();
    expect(screen.queryByText(/analysis can miss conflicts/)).not.toBeInTheDocument(); // a warning is shown
  });

  it("says when the results are stale and re-runs them", async () => {
    const { calls } = mockApi({
      "GET /api/v1/change-requests/cr1/checks": { ...CHECKS, state: "stale", stale_reasons: ["REQ-014 moved to v3"] },
      "POST /api/v1/change-requests/cr1/checks/rerun": [202, null],
    });
    const { user } = renderWithProviders(<ChecksTab changeRequestId="cr1" canRerun />);

    expect(await screen.findByText(/These results are out of date/)).toBeInTheDocument();
    expect(screen.getByText(/REQ-014 moved to v3/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Re-run checks" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    expect(await screen.findByText(/Checks queued/)).toBeInTheDocument();
  });

  it("waits honestly while no report exists", async () => {
    mockApi({ "GET /api/v1/change-requests/cr1/checks": { state: "pending", stale_reasons: [], report: null } });
    renderWithProviders(<ChecksTab changeRequestId="cr1" canRerun={false} />);
    expect(await screen.findByRole("status")).toHaveTextContent("The checks are running on this revision");
  });
});

describe("DiffView", () => {
  it("shows a deprecation as the whole text removed", () => {
    renderWithProviders(<DiffView change={change({ kind: "deprecate", proposed_body: null })} />);
    expect(screen.getByText(/Deprecate REQ-014/)).toBeInTheDocument();
    expect(screen.getByLabelText("Text removed").querySelector("del")).toHaveTextContent(/inactive for 30 minutes/);
  });

  it("quotes inline comments on the current revision only", () => {
    const comment = { field: "statement", start_offset: 30, end_offset: 40, body: "Why 10?" };
    renderWithProviders(
      <DiffView
        change={change()}
        reviews={[review({ comments: [comment] }), review({ id: "old", dismissed: true, comments: [{ ...comment, body: "Old one" }] })]}
      />,
    );
    const current = screen.getByText("Why 10?").closest("li") as HTMLElement;
    expect(within(current).getByText("10 minutes")).toBeInTheDocument();
    const old = screen.getByText("Old one").closest("li") as HTMLElement;
    expect(old.querySelector("q")).toBeNull();
  });
});

describe("change_request events", () => {
  it("refresh the request and, on a merge, the requirement, its versions and the issues", () => {
    const queryClient = new QueryClient();
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    applyEvent(queryClient, {
      type: "change_request.merged",
      workspace_id: "w1",
      project_id: "p1",
      channel_id: null,
      entity_id: "cr1",
      at: "2026-12-11T09:00:00Z",
      data: { change_request_id: "cr1", requirement_id: "r14", number: 34, status: "merged" },
    });
    const keys = invalidate.mock.calls.map(([filters]) => filters?.queryKey);
    expect(keys).toEqual(
      expect.arrayContaining([
        ["change-requests", "p1"],
        ["change-request", "cr1"],
        ["requirement", "r14"],
        ["versions", "r14"],
        ["issues", "p1"],
      ]),
    );
  });
});
