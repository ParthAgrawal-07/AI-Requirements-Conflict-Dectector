import { afterEach, describe, expect, it, vi } from "vitest";
import { FindingsPage } from "../src/features/findings/FindingsPage";
import { highlight, type Finding } from "../src/features/findings/api";
import { mockApi, renderWithProviders, screen, within } from "./test-utils";

const A = "Sessions shall expire after 30 minutes of inactivity.";
const B = "When the user is inactive for 5 minutes, the app shall log the user out.";
const CONFLICT: Finding = {
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
  evidence_spans: [
    { requirement_id: "r14", label: "REQ-014", quote: "30 minutes", start: 28, end: 38 },
    { requirement_id: "r31", label: "REQ-031", quote: "5 minutes", start: 30, end: 39 },
  ],
  requirements: [
    { id: "r14", label: "REQ-014", body: A, state: "Approved", is_protected: true, origin: "document", section_heading: "3.1 Sessions", location: "page 4", document_id: "d1", origin_message_id: null },
    { id: "r31", label: "REQ-031", body: B, state: "Proposed", is_protected: false, origin: "post", section_heading: null, location: null, document_id: null, origin_message_id: "m1" },
  ],
  dependency_direction: null,
  vague_terms: [],
  missing_information: [],
  context_version: 2,
  prompt_version: "v2",
  analysis_run_id: null,
  created_at: "2026-11-01T10:00:00Z",
};
const VAGUE: Finding = {
  ...CONFLICT,
  id: "f2",
  category: "Incomplete",
  confidence: 0.42,
  confidence_percent: 42,
  low_confidence: true,
  explanation: "The uptime figure has no period. Missing: the measurement period.",
  evidence_spans: [],
  requirements: [{ ...CONFLICT.requirements[0], id: "r40", label: "REQ-040", body: "The system shall maintain 99.9% uptime." }],
  missing_information: ["the measurement period"],
};
const page = (items: Finding[]) => ({ items, total: items.length, limit: 20, offset: 0 });
const PATH = "/w/:workspaceId/p/:projectId/findings";

afterEach(() => vi.unstubAllGlobals());

describe("highlight", () => {
  it("marks only the located spans and keeps the rest verbatim", () => {
    expect(highlight(A, CONFLICT.evidence_spans.slice(0, 1))).toEqual([
      { text: "Sessions shall expire after ", marked: false },
      { text: "30 minutes", marked: true },
      { text: " of inactivity.", marked: false },
    ]);
    expect(highlight("short", [{ requirement_id: "x", label: "x", quote: "q", start: 2, end: 99 }])).toEqual([
      { text: "short", marked: false },
    ]);
  });
});

describe("FindingsPage", () => {
  it("shows category, confidence, the low-confidence marker and the requirements involved", async () => {
    mockApi({ "GET /api/v1/projects/p1/findings": page([CONFLICT, VAGUE]) });
    renderWithProviders(<FindingsPage />, { route: "/w/w1/p/p1/findings", path: PATH });

    const conflict = await screen.findByRole("article", { name: /Conflicting finding/ });
    expect(within(conflict).getByText("86% confidence")).toBeInTheDocument();
    expect(within(conflict).getByText("REQ-014 ↔ REQ-031")).toBeInTheDocument();
    expect(within(conflict).getByText("AI analysis")).toBeInTheDocument();
    expect(within(conflict).queryByText(/Low confidence/)).not.toBeInTheDocument();

    const vague = screen.getByRole("article", { name: /Incomplete finding/ });
    expect(within(vague).getByText(/Low confidence — recommend manual review/)).toBeInTheDocument();
  });

  it("filters by low confidence on the server", async () => {
    const { calls } = mockApi({ "GET /api/v1/projects/p1/findings": page([VAGUE]) });
    const { user } = renderWithProviders(<FindingsPage />, { route: "/w/w1/p/p1/findings", path: PATH });

    await user.click(await screen.findByLabelText(/Only low confidence/));

    expect(calls.some((c) => c.path.includes("low_confidence=true"))).toBe(true);
  });

  it("opens a finding side by side with the problem clause highlighted and its sources", async () => {
    mockApi({
      "GET /api/v1/projects/p1/findings": page([CONFLICT]),
      "GET /api/v1/findings/f1": CONFLICT,
    });
    const { user } = renderWithProviders(<FindingsPage />, { route: "/w/w1/p/p1/findings", path: PATH });

    await user.click(await screen.findByRole("button", { name: "View side by side" }));

    const drawer = await screen.findByRole("dialog", { name: "Conflicting finding" });
    const left = await within(drawer).findByRole("region", { name: "REQ-014" });
    expect(within(left).getByText("30 minutes").tagName).toBe("MARK");
    expect(within(left).getByText(/3.1 Sessions · page 4/)).toBeInTheDocument();
    expect(within(left).getByText("Protected")).toBeInTheDocument();
    const right = within(drawer).getByRole("region", { name: "REQ-031" });
    expect(within(right).getByText("From a post in a channel")).toBeInTheDocument();
    expect(within(drawer).getByText(/project context v2/)).toBeInTheDocument();
  });

  it("says when there is nothing yet", async () => {
    mockApi({ "GET /api/v1/projects/p1/findings": page([]) });
    renderWithProviders(<FindingsPage />, { route: "/w/w1/p/p1/findings", path: PATH });
    expect(await screen.findByText(/No findings yet/)).toBeInTheDocument();
  });
});
