import { afterEach, describe, expect, it, vi } from "vitest";
import { ComplianceQueue } from "../src/features/compliance/ComplianceQueue";
import { ProtectionControl } from "../src/features/compliance/ProtectionControl";
import { AiFeedbackPage } from "../src/features/feedback/AiFeedbackPage";
import { acceptanceRate } from "../src/features/feedback/api";
import type { Finding } from "../src/features/findings/api";
import { FindingCard } from "../src/features/findings/FindingCard";
import { SeverityControl } from "../src/features/findings/SeverityControl";
import { mockApi, renderWithProviders, screen, waitFor, within } from "./test-utils";

afterEach(() => vi.unstubAllGlobals());

const permissions = (granted: string[], protectedOnly: string[] = []) => ({
  workspace_id: "w1",
  project_id: "p1",
  role: { id: "r", name: "Member", is_default: false },
  permissions: granted,
  protected_only: protectedOnly,
});
const PERMS = "GET /api/v1/me/permissions?project=p1";

const FINDING: Finding = {
  id: "f1",
  project_id: "p1",
  source: "AI",
  category: "Conflicting",
  status: "flagged",
  severity: "high",
  severity_source: "reviewer",
  severity_proposed: "medium",
  severity_reason: "Touches patient data",
  confidence: 0.86,
  confidence_percent: 86,
  low_confidence: false,
  explanation: "Different inactivity limits.",
  evidence_spans: [],
  requirements: [
    { id: "r14", label: "REQ-014", body: "A", state: "Approved", is_protected: true, origin: "document",
      section_heading: null, location: null, document_id: null, origin_message_id: null },
    { id: "r31", label: "REQ-031", body: "B", state: "Proposed", is_protected: false, origin: "post",
      section_heading: null, location: null, document_id: null, origin_message_id: null },
  ],
  dependency_direction: null,
  vague_terms: [],
  missing_information: [],
  context_version: null,
  prompt_version: null,
  analysis_run_id: null,
  created_at: "2027-01-05T10:00:00Z",
};

const at = (page: string) => ({ route: `/w/w1/p/p1/${page}`, path: `/w/:workspaceId/p/:projectId/${page}` });

describe("FindingCard severity and protection", () => {
  it("shows severity as a shape and a word beside confidence, and the protected flag", () => {
    renderWithProviders(<FindingCard finding={FINDING} />);
    const card = screen.getByRole("article", { name: /Conflicting finding/ });
    expect(within(card).getByText(/High severity/)).toHaveTextContent("▲▲▲ High severity, set by a reviewer");
    expect(within(card).getByText("86% confidence")).toBeInTheDocument();
    expect(within(card).getByText("Protected")).toBeInTheDocument();
  });

  it("says when no severity is set", () => {
    renderWithProviders(<FindingCard finding={{ ...FINDING, severity: null, severity_source: null }} />);
    expect(screen.getByText("Severity not set")).toBeInTheDocument();
  });
});

describe("SeverityControl", () => {
  it("shows the system's proposal after an override and saves a new level with a reason", async () => {
    const { calls } = mockApi({
      [PERMS]: permissions(["view", "finding.review", "protected.signoff"]),
      "PATCH /api/v1/findings/f1/severity": { ...FINDING, severity: "low" },
    });
    const { user } = renderWithProviders(<SeverityControl projectId="p1" finding={FINDING} />);

    expect(screen.getByText(/the system proposed Medium/)).toBeInTheDocument();
    expect(screen.getByText("Why: Touches patient data")).toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "Change severity…" }));
    await user.click(screen.getByRole("radio", { name: "Low" }));
    const save = screen.getByRole("button", { name: "Save severity" });
    expect(save).toBeDisabled();
    await user.type(screen.getByRole("textbox", { name: /Reason/ }), "Only affects the demo tenant");
    await user.click(save);

    await waitFor(() => expect(calls.some((c) => c.method === "PATCH")).toBe(true));
    const patch = calls.find((c) => c.method === "PATCH");
    expect(JSON.parse(String(patch?.body))).toEqual({ severity: "low", reason: "Only affects the demo tenant" });
  });

  it("keeps a protected finding's severity for compliance reviewers", async () => {
    mockApi({ [PERMS]: permissions(["view", "finding.review"]) });
    renderWithProviders(<SeverityControl projectId="p1" finding={FINDING} />);
    await screen.findByText(/High severity/);
    await waitFor(() => expect(screen.queryByRole("button", { name: "Change severity…" })).not.toBeInTheDocument());
  });
});

describe("ProtectionControl", () => {
  it("asks for a reason before removing protection", async () => {
    const { calls } = mockApi({
      [PERMS]: permissions(["view", "req.protect"]),
      "PUT /api/v1/requirements/r14/protection": {
        requirement_id: "r14", label: "REQ-014", is_protected: false, protected_by: null, protected_at: null,
        protection_reason: null,
      },
    });
    const { user } = renderWithProviders(
      <ProtectionControl projectId="p1" requirementId="r14" label="REQ-014" isProtected />,
    );
    await user.click(await screen.findByRole("button", { name: "Remove protection…" }));
    const form = screen.getByRole("form", { name: "Remove protection" });
    expect(within(form).getByRole("button", { name: "Remove protection" })).toBeDisabled();
    await user.type(within(form).getByRole("textbox"), "No longer regulated");
    await user.click(within(form).getByRole("button", { name: "Remove protection" }));

    await waitFor(() => expect(calls.some((c) => c.method === "PUT")).toBe(true));
    const put = calls.find((c) => c.method === "PUT");
    expect(JSON.parse(String(put?.body))).toEqual({ protected: false, reason: "No longer regulated" });
  });

  it("is not offered without req.protect", async () => {
    mockApi({ [PERMS]: permissions(["view"]) });
    renderWithProviders(<ProtectionControl projectId="p1" requirementId="r14" label="REQ-014" isProtected={false} />);
    await waitFor(() => expect(screen.queryByRole("button", { name: /protect/i })).not.toBeInTheDocument());
  });
});

const QUEUE = {
  pending: [
    { kind: "finding", id: "f1", requirement_ids: ["r14"], labels: ["REQ-014", "REQ-031"], title: "Conflicting finding",
      status: "awaiting_decision", since: "2027-01-05T10:00:00Z", done_by: null, done_by_name: null },
    { kind: "change_request", id: "cr1", requirement_ids: ["r14"], labels: ["REQ-014"], title: "RCR-3: shorten sessions",
      status: "awaiting_approval", since: "2027-01-06T10:00:00Z", done_by: null, done_by_name: null },
  ],
  protected: [
    { requirement_id: "r14", label: "REQ-014", state: "Approved", current_version: 3, signed_off_version: 2,
      signed_off_by: "u2", signed_off_by_name: "Meera", signed_off_at: "2027-01-02T10:00:00Z", protected_by: "u1",
      protected_by_name: "Parth", protected_at: "2027-01-01T10:00:00Z", protection_reason: "HIPAA §164.312" },
  ],
};

describe("ComplianceQueue", () => {
  it("lists what waits for compliance, each protected requirement's sign-off, and exports the trail", async () => {
    mockApi({
      [PERMS]: permissions(["view", "protected.signoff", "audit.export"]),
      "GET /api/v1/projects/p1/compliance/queue": QUEUE,
    });
    renderWithProviders(<ComplianceQueue />, at("compliance"));

    const pending = await screen.findByRole("region", { name: "Waiting for compliance (2)" });
    expect(within(pending).getByRole("link", { name: "Conflicting finding" })).toHaveAttribute(
      "href",
      "/w/w1/p/p1/findings?finding=f1",
    );
    expect(within(pending).getByRole("link", { name: "RCR-3: shorten sessions" })).toHaveAttribute(
      "href",
      "/w/w1/p/p1/changes/cr1",
    );
    expect(within(pending).getByText("Awaiting compliance approval")).toBeInTheDocument();

    const protectedList = screen.getByRole("region", { name: "Protected requirements (1)" });
    expect(within(protectedList).getByText(/Signed off v2 — v3 needs sign-off/)).toBeInTheDocument();
    expect(within(protectedList).getByText("HIPAA §164.312")).toBeInTheDocument();

    const exports = screen.getByRole("group", { name: "Export the audit trail" });
    expect(within(exports).getByRole("button", { name: "Audit trail CSV" })).toBeInTheDocument();
  });

  it("explains itself to members who have no compliance permission, without loading the queue", async () => {
    const { calls } = mockApi({ [PERMS]: permissions(["view"]) });
    renderWithProviders(<ComplianceQueue />, at("compliance"));
    expect(await screen.findByText(/Only compliance reviewers and project managers/)).toBeInTheDocument();
    expect(calls.some((c) => c.path.includes("/compliance/queue"))).toBe(false);
  });

  it("is reachable by keyboard: every row link is focusable in order", async () => {
    mockApi({
      [PERMS]: permissions(["view", "protected.signoff"]),
      "GET /api/v1/projects/p1/compliance/queue": QUEUE,
    });
    const { user } = renderWithProviders(<ComplianceQueue />, at("compliance"));
    await screen.findByRole("link", { name: "Conflicting finding" });
    await user.tab();
    expect(screen.getByRole("link", { name: "Conflicting finding" })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("link", { name: "RCR-3: shorten sessions" })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("link", { name: "REQ-014" })).toHaveFocus();
  });
});

const REPORT = {
  project_id: "p1",
  threshold: 3,
  self_training: false,
  categories: [
    {
      category: "Ambiguous",
      open: 2,
      confirmed: 1,
      dismissed: 4,
      suggestions: { accepted: 2, rejected_meaning: 1 },
      patterns: [
        { pattern: "LINT-WEAK-WORD", source: "rule", confirmed: 0, dismissed: 3, false_positive_rate: 1,
          reasons: [{ reason: "Domain term, not vague", count: 3 }], surfaced: true },
        { pattern: "AI", source: "ai", confirmed: 1, dismissed: 1, false_positive_rate: 0.5,
          reasons: [{ reason: "(no reason given)", count: 1 }], surfaced: false },
      ],
    },
  ],
  surfaced: [],
  suggestion_totals: { accepted: 2, accepted_edited: 1, rejected_meaning: 1, rejected_infeasible: 0,
    rejected_missing_context: 0, deferred: 4 },
};
REPORT.surfaced = [{ category: "Ambiguous", pattern: REPORT.categories[0].patterns[0] }] as never;

describe("AiFeedbackPage", () => {
  it("shows dismissal reasons per category and pattern, surfaced patterns and suggestion outcomes", async () => {
    mockApi({ [PERMS]: permissions(["view"]), "GET /api/v1/projects/p1/ai-feedback": REPORT });
    renderWithProviders(<AiFeedbackPage />, at("insights/ai-feedback"));

    const surfaced = await screen.findByRole("region", { name: "Patterns to look at (1)" });
    expect(within(surfaced).getByText(/LINT-WEAK-WORD/)).toBeInTheDocument();
    expect(within(surfaced).getByText(/Domain term, not vague/)).toBeInTheDocument();

    const table = screen.getByRole("table", { name: "Ambiguous findings by pattern" });
    expect(within(table).getByText("100%")).toBeInTheDocument();
    expect(table.querySelector(".badge-ai")).toHaveTextContent("AI");

    expect(screen.getByText("75%")).toBeInTheDocument(); // 3 accepted of 4 decided
    expect(screen.getByText(/does not learn from it by itself/)).toBeInTheDocument();
  });

  it("lets a project manager change the threshold", async () => {
    const { calls } = mockApi({
      [PERMS]: permissions(["view", "project.manage"]),
      "GET /api/v1/projects/p1/ai-feedback": REPORT,
      "PUT /api/v1/projects/p1/ai-feedback/threshold": { ...REPORT, threshold: 5 },
    });
    const { user } = renderWithProviders(<AiFeedbackPage />, at("insights/ai-feedback"));
    const input = await screen.findByRole("spinbutton", { name: /List a pattern after/ });
    await user.clear(input);
    await user.type(input, "5");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(calls.some((c) => c.method === "PUT")).toBe(true));
    expect(JSON.parse(String(calls.find((c) => c.method === "PUT")?.body))).toEqual({ threshold: 5 });
  });

  it("computes the acceptance rate from decided suggestions only", () => {
    expect(acceptanceRate({ accepted: 1, accepted_edited: 1, rejected_meaning: 2, deferred: 10 })).toBe(50);
    expect(acceptanceRate({ deferred: 3 })).toBeNull();
  });
});
