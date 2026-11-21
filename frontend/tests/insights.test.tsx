import { afterEach, describe, expect, it, vi } from "vitest";
import { BaselineList } from "../src/features/baselines/BaselineList";
import { DashboardPage } from "../src/features/dashboard/DashboardPage";
import { DecisionOwner } from "../src/features/members/DecisionOwner";
import { DecisionRulesTab } from "../src/features/members/DecisionRulesTab";
import { mockApi, renderWithProviders, screen, waitFor, within } from "./test-utils";

afterEach(() => vi.unstubAllGlobals());

const permissions = (granted: string[]) => ({
  workspace_id: "w1",
  project_id: "p1",
  role: { id: "r", name: "Analyst", is_default: true },
  permissions: granted,
  protected_only: [],
});

const BOARD = {
  project_id: "p1",
  filters: {},
  suggested_filters: {},
  findings: {
    total: 3,
    by_category: { Conflicting: 2, Ambiguous: 1 },
    by_severity: { high: 1, unset: 2 },
    by_status: { flagged: 2, dismissed: 1 },
    by_source: { ai: 2, rule: 1, person: 0 },
  },
  requirements: { total: 4, by_state: { Approved: 2, Proposed: 2 } },
  change_requests: { open: 1, by_risk: { low: 0, medium: 0, high: 1, unknown: 0 } },
  issues: { open: 1, closed: 2, closed_by_reason: { manual: 2 }, auto_open: 1 },
};

const route = { route: "/w/w1/p/p1/insights", path: "/w/:workspaceId/p/:projectId/insights" };

describe("DashboardPage (US-13)", () => {
  it("shows the counts and every number opens its filtered list", async () => {
    mockApi({ "GET /api/v1/projects/p1/analytics": BOARD });
    renderWithProviders(<DashboardPage />, route);
    const findings = await screen.findByRole("region", { name: "Findings (3)" });
    expect(within(findings).getByRole("link", { name: "2" })).toHaveAttribute(
      "href",
      "/w/w1/p/p1/findings?category=Conflicting",
    );
    const severity = screen.getByRole("region", { name: "Findings by severity" });
    expect(within(severity).getByText("Not assessed")).toBeInTheDocument();
    expect(within(severity).getByRole("link", { name: "1" })).toHaveAttribute("href", "/w/w1/p/p1/findings?severity=high");
    const source = screen.getByRole("region", { name: "Found by" });
    expect(within(source).getByRole("link", { name: "1" })).toHaveAttribute("href", "/w/w1/p/p1/findings?source=rule");
    const issues = screen.getByRole("region", { name: "Issues" });
    expect(within(issues).getByRole("link", { name: "2" })).toHaveAttribute("href", "/w/w1/p/p1/issues?status=closed");
    expect(screen.getByRole("region", { name: "Open change requests (1)" })).toHaveTextContent("High risk1");
  });

  it("starts on the role's suggested view and filters on request", async () => {
    const { calls } = mockApi({
      "GET /api/v1/projects/p1/analytics": { ...BOARD, suggested_filters: { owner: "u-me" } },
    });
    const { user } = renderWithProviders(<DashboardPage />, route);
    await waitFor(() => expect(calls.some((c) => c.path.includes("owner=u-me"))).toBe(true));
    await user.selectOptions(screen.getByLabelText("Type"), "constraint");
    await waitFor(() => expect(calls.some((c) => c.path.includes("req_type=constraint"))).toBe(true));
    await user.click(screen.getByRole("button", { name: "Clear filters" }));
    await waitFor(() => expect(calls[calls.length - 1].path).toBe("/api/v1/projects/p1/analytics"));
  });
});

describe("Baselines (US-40)", () => {
  const BASELINES = [
    { id: "b2", project_id: "p1", label: "v1.1", note: null, baseline_revision: 4, requirement_count: 3, created_by: "u", created_by_name: "Asha", created_at: "2026-12-20T10:00:00Z" },
    { id: "b1", project_id: "p1", label: "v1.0", note: "Client sign-off", baseline_revision: 2, requirement_count: 3, created_by: "u", created_by_name: "Asha", created_at: "2026-12-10T10:00:00Z" },
  ];

  it("compares v1.1 with v1.0: added, changed with a diff, removed", async () => {
    mockApi({
      "GET /api/v1/me/permissions?project=p1": permissions(["view"]),
      "GET /api/v1/projects/p1/baselines": BASELINES,
      "GET /api/v1/baselines/b1/compare/b2": {
        base: BASELINES[1],
        target: BASELINES[0],
        added: [{ requirement_id: "r5", label: "REQ-005", version: 1, state: "Approved", body: "Export as PDF." }],
        changed: [{ requirement_id: "r2", label: "REQ-002", from_version: 1, to_version: 2, before: "Kept for 7 years.", after: "Kept for 10 years." }],
        removed: [{ requirement_id: "r3", label: "REQ-003", version: 1, state: "Deprecated", body: "Export as CSV." }],
        unchanged: 1,
      },
    });
    const { user } = renderWithProviders(<BaselineList />, { route: "/w/w1/p/p1/baselines", path: "/w/:workspaceId/p/:projectId/baselines" });
    expect(await screen.findByText("Client sign-off")).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "Freeze a baseline" })).not.toBeInTheDocument();
    const [v11, v10] = screen.getAllByRole("row").slice(1);
    await user.click(within(v10).getByLabelText("from"));
    await user.click(within(v11).getByLabelText("to"));
    const comparison = await screen.findByRole("region", { name: "v1.0 compared with v1.1" });
    expect(comparison.querySelector("p")).toHaveTextContent("1 added · 1 changed · 1 removed · 1 unchanged");
    const diff = screen.getByLabelText("Changes to REQ-002");
    expect(diff.querySelector("del")).toHaveTextContent("7");
    expect(diff.querySelector("ins")).toHaveTextContent("10");
    expect(screen.getByText(/now Deprecated/)).toBeInTheDocument();
  });

  it("freezes a labelled snapshot for those who manage the baseline", async () => {
    const { calls } = mockApi({
      "GET /api/v1/me/permissions?project=p1": permissions(["view", "baseline.manage"]),
      "GET /api/v1/projects/p1/baselines": [],
      "POST /api/v1/projects/p1/baselines": [201, { ...BASELINES[0], label: "v1.0" }],
    });
    const { user } = renderWithProviders(<BaselineList />, { route: "/w/w1/p/p1/baselines", path: "/w/:workspaceId/p/:projectId/baselines" });
    await user.type(await screen.findByLabelText("Label"), "v1.0");
    await user.click(screen.getByRole("button", { name: "Freeze baseline" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    expect(calls.find((c) => c.method === "POST")?.body).toBe(JSON.stringify({ label: "v1.0" }));
  });
});

describe("Decision rules (US-57)", () => {
  const RULES = [
    { id: "d2", name: "Protected requirements", priority: 100, is_default: false, specificity: 1, match_category: null, match_label: null, match_group: null, match_req_type: null, match_protected: true, owner: { kind: "role", id: "rc", name: "Compliance Reviewer" }, required_reviewers: [], optional_reviewers: [] },
    { id: "d1", name: "Default: the requirement owner decides", priority: 100, is_default: true, specificity: 0, match_category: null, match_label: null, match_group: null, match_req_type: null, match_protected: null, owner: { kind: "requirement_owner", id: null, name: "the requirement owner" }, required_reviewers: [], optional_reviewers: [] },
  ];

  it("lists the rules with the default pinned and lets managers delete the others", async () => {
    mockApi({
      "GET /api/v1/me/permissions?project=p1": permissions(["view", "project.manage"]),
      "GET /api/v1/projects/p1/decision-rules": RULES,
      "GET /api/v1/workspaces/w1/roles": [],
      "GET /api/v1/workspaces/w1/members": [],
    });
    renderWithProviders(<DecisionRulesTab workspaceId="w1" projectId="p1" />);
    const rows = (await screen.findAllByRole("row")).slice(1);
    expect(within(rows[0]).getByText("Protected")).toBeInTheDocument();
    expect(within(rows[0]).getByText("Compliance Reviewer")).toBeInTheDocument();
    expect(within(rows[1]).getByText("Default")).toBeInTheDocument();
    expect(within(rows[1]).getByText("Everything else")).toBeInTheDocument();
    expect(within(rows[0]).getByRole("button", { name: /Delete rule Protected/ })).toBeInTheDocument();
    expect(within(rows[1]).queryByRole("button")).not.toBeInTheDocument();
  });

  it("shows who decides an item, with a link to the rules", async () => {
    mockApi({
      "GET /api/v1/issues/i1/decision": {
        rule_id: "d2", rule_name: "Protected requirements", is_default: false, owner_kind: "role",
        owners: [{ id: "u-meera", full_name: "Meera" }], required_reviewers: [],
        sentence: "Decides: Compliance Reviewer (Meera) — rule Protected requirements",
      },
    });
    renderWithProviders(<DecisionOwner kind="issues" id="i1" />, { route: "/w/w1/p/p1/issues/i1", path: "/w/:workspaceId/p/:projectId/issues/:issueId" });
    expect(await screen.findByText(/Decides: Compliance Reviewer \(Meera\)/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "rules" })).toHaveAttribute("href", "/w/w1/p/p1/settings/decision-rules");
  });
});
