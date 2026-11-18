import { afterEach, describe, expect, it, vi } from "vitest";
import { FindingDrawer } from "../src/features/findings/FindingDrawer";
import { FindingsPage } from "../src/features/findings/FindingsPage";
import type { Finding } from "../src/features/findings/api";
import { mockApi, renderWithProviders, screen, waitFor, within } from "./test-utils";

afterEach(() => vi.unstubAllGlobals());

const requirement = (id: string, label: string, isProtected = false) => ({
  id,
  label,
  body: `${label} body.`,
  state: "Approved" as const,
  is_protected: isProtected,
  origin: "document" as const,
  section_heading: null,
  location: null,
  document_id: "d1",
  origin_message_id: null,
});
const FINDING: Finding = {
  id: "f1",
  project_id: "p1",
  source: "AI",
  category: "Conflicting",
  status: "flagged",
  severity: "high",
  confidence: 0.86,
  confidence_percent: 86,
  low_confidence: false,
  explanation: "REQ-014 and REQ-031 set different inactivity limits.",
  evidence_spans: [],
  requirements: [requirement("r14", "REQ-014"), requirement("r31", "REQ-031")],
  dependency_direction: null,
  vague_terms: [],
  missing_information: [],
  context_version: 2,
  prompt_version: "v2",
  analysis_run_id: null,
  created_at: "2026-11-01T10:00:00Z",
  ai_category: "Conflicting",
  clarification: null,
  resolved: false,
};
const permissions = (granted: string[]) => ({
  workspace_id: "w1",
  project_id: "p1",
  role: { id: "r", name: "Analyst", is_default: true },
  permissions: granted,
  protected_only: [],
});
const page = (items: Finding[]) => ({ items, total: items.length, limit: 50, offset: 0 });

function api(finding: Finding, granted = ["view", "req.comment", "finding.review"], extra: Record<string, unknown> = {}) {
  return mockApi({
    "GET /api/v1/findings/f1": finding,
    "GET /api/v1/projects/p1/findings": page([finding]),
    "GET /api/v1/me/permissions?project=p1": permissions(granted),
    "POST /api/v1/findings/f1/review": { ...finding, status: "confirmed" },
    ...extra,
  });
}

const drawer = () => renderWithProviders(<FindingDrawer projectId="p1" findingId="f1" onClose={() => undefined} />);
const posted = (calls: { method: string; path: string; body: unknown }[], path: string) =>
  calls.filter((c) => c.method === "POST" && c.path === path).map((c) => JSON.parse(String(c.body)));

describe("ReviewActions", () => {
  it("confirms a finding", async () => {
    const { calls } = api(FINDING);
    const { user } = drawer();

    await user.click(await screen.findByRole("button", { name: "Confirm" }));

    await waitFor(() => expect(posted(calls, "/api/v1/findings/f1/review")).toEqual([{ action: "confirm" }]));
    expect(await screen.findByText("Finding accepted")).toBeInTheDocument();
  });

  it("asks why before dismissing", async () => {
    const { calls } = api(FINDING);
    const { user } = drawer();

    await user.click(await screen.findByRole("button", { name: "Dismiss…" }));
    const reason = screen.getByLabelText("Why is it not a real issue?");
    expect(reason).toBeRequired();
    await user.type(reason, "Different products");
    await user.click(screen.getByRole("button", { name: "Dismiss" }));

    await waitFor(() =>
      expect(posted(calls, "/api/v1/findings/f1/review")).toEqual([{ action: "dismiss", reason: "Different products" }]),
    );
  });

  it("offers only the categories a pair can have when reclassifying", async () => {
    api(FINDING);
    const { user } = drawer();

    await user.click(await screen.findByRole("button", { name: "Reclassify…" }));

    const options = within(screen.getByLabelText("New category")).getAllByRole("option").map((o) => o.textContent);
    expect(options).toEqual(["Choose…", "Duplicate", "Dependent"]);
  });

  it("keeps the AI's category visible after a reclassification", async () => {
    api({ ...FINDING, category: "Duplicate", status: "reclassified" });
    drawer();
    expect(await screen.findByText(/AI said Conflicting/)).toBeInTheDocument();
  });

  it("says a protected finding is for compliance reviewers instead of offering buttons", async () => {
    const guarded = { ...FINDING, requirements: [requirement("r14", "REQ-014", true), requirement("r31", "REQ-031")] };
    api(guarded);
    drawer();

    expect(await screen.findByText(/only a compliance reviewer can act on this finding/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Confirm" })).not.toBeInTheDocument();
  });

  it("lets a compliance reviewer act on a protected finding", async () => {
    const guarded = { ...FINDING, requirements: [requirement("r14", "REQ-014", true), requirement("r31", "REQ-031")] };
    api(guarded, ["view", "protected.signoff"]);
    drawer();
    expect(await screen.findByRole("button", { name: "Confirm" })).toBeInTheDocument();
  });

  it("offers reopen, not confirm, on a dismissed finding", async () => {
    api({ ...FINDING, status: "dismissed" });
    drawer();
    expect(await screen.findByRole("button", { name: "Reopen" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Confirm" })).not.toBeInTheDocument();
  });
});

describe("Clarification in the finding drawer", () => {
  const clarification = {
    id: "c1",
    finding_id: "f1",
    question: "Which inactivity limit applies, 5 or 30 minutes?",
    addressed_to: "owner",
    answered: false,
    resolution: null,
    resolved_by: null,
    resolved_at: null,
  };

  it("records the answer to the question", async () => {
    const { calls } = api({ ...FINDING, clarification }, undefined, {
      "POST /api/v1/clarifications/c1/answer": { ...clarification, answered: true, resolution: "5 minutes" },
    });
    const { user } = drawer();

    expect(await screen.findByText(/Which inactivity limit applies/)).toBeInTheDocument();
    await user.type(await screen.findByLabelText("Answer"), "5 minutes");
    await user.click(screen.getByRole("button", { name: "Record answer" }));

    await waitFor(() =>
      expect(posted(calls, "/api/v1/clarifications/c1/answer")).toEqual([{ resolution: "5 minutes" }]),
    );
  });

  it("shows the answer once given", async () => {
    api({ ...FINDING, clarification: { ...clarification, answered: true, resolution: "5 minutes" } });
    drawer();
    expect(await screen.findByText("5 minutes")).toBeInTheDocument();
    expect(screen.queryByLabelText("Answer")).not.toBeInTheDocument();
  });
});

describe("FindingsPage review filter", () => {
  it("filters by review state on the server", async () => {
    const { calls } = api(FINDING);
    const { user } = renderWithProviders(<FindingsPage />, {
      route: "/w/w1/p/p1/findings",
      path: "/w/:workspaceId/p/:projectId/findings",
    });
    await screen.findByRole("article", { name: /Conflicting finding/ });

    await user.selectOptions(screen.getByLabelText("Review"), "Dismissed");

    await waitFor(() => expect(calls.some((c) => c.path.includes("status=dismissed"))).toBe(true));
  });
});
