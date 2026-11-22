import { afterEach, describe, expect, it, vi } from "vitest";
import { ChangesPanel } from "../src/features/analytics/ChangesPanel";
import { draftOverlay, overlayOf, type GraphPreview, type RevisionPoint } from "../src/features/map/history";
import { TimeSlider } from "../src/features/map/TimeSlider";
import { Timeline } from "../src/features/requirements/Timeline";
import { fireEvent, mockApi, render, renderWithProviders, screen, waitFor, within } from "./test-utils";

afterEach(() => vi.unstubAllGlobals());

const event = (id: string, sentence: string, extra: Record<string, unknown> = {}) => ({
  id,
  at: "2027-01-12T09:30:00Z",
  revision: 7,
  kind: "added",
  sentence,
  actor_id: "u1",
  actor_name: "Riya",
  node_ids: ["r31"],
  edge_ids: [],
  backfilled: false,
  ...extra,
});

const summary = (narrative: boolean) => ({
  since: "2027-01-10T00:00:00Z",
  until: "2027-01-12T10:00:00Z",
  since_label: "your last visit",
  counts: { added: 1, conflict_found: 1 },
  count_lines: ["1 requirement added", "1 conflict found"],
  highlights: [event("e2", "A conflict was found between REQ-031 and REQ-014.", { kind: "conflict_found" })],
  total_events: 2,
  markdown: "## Changes",
  narrative: narrative
    ? { text: "Riya added a login rule that conflicts with REQ-014.", ai: true, provider: "gemini", model: "gemini-2.5-flash" }
    : null,
  narrative_status: narrative ? "ok" : "not_requested",
});

function changesApi(extra: Record<string, unknown> = {}) {
  return mockApi({
    "GET /api/v1/projects/p1/changes": {
      items: [
        event("e1", "Riya posted REQ-031."),
        event("e2", "A conflict was found between REQ-031 and REQ-014.", {
          kind: "conflict_found",
          node_ids: ["r31", "r14"],
          edge_ids: ["edge-1"],
          backfilled: true,
        }),
      ],
      next_before: null,
    },
    "PUT /api/v1/projects/p1/changes/seen": { seen_at: "2027-01-12T10:00:00Z", previous: null },
    "GET /api/v1/projects/p1/baselines": [],
    ...extra,
  });
}

const names = new Map([["u1", "Riya"]]);

describe("ChangesPanel", () => {
  it("lists every change as a sentence and highlights its elements when chosen", async () => {
    const { calls } = changesApi();
    const onSelect = vi.fn();
    const { user } = renderWithProviders(
      <ChangesPanel projectId="p1" names={names} untilRevision={null} hoveredNode={null} onSelect={onSelect} />,
    );

    const panel = screen.getByRole("region", { name: "Changes panel" });
    await user.click(await within(panel).findByRole("button", { name: /conflict was found/ }));
    expect(onSelect).toHaveBeenCalledWith(["r31", "r14", "edge-1"]);
    expect(within(panel).getByText("(from the audit log)")).toBeInTheDocument();
    // Opening the panel counts as a visit.
    await waitFor(() => expect(calls.some((c) => c.method === "PUT" && c.path.endsWith("/changes/seen"))).toBe(true));
  });

  it("filters by person, kind and the time slider's revision", async () => {
    const { calls } = changesApi();
    const { user } = renderWithProviders(
      <ChangesPanel projectId="p1" names={names} untilRevision={5} hoveredNode="r31" onSelect={vi.fn()} />,
    );
    await screen.findByRole("button", { name: /Riya posted/ });
    await user.selectOptions(screen.getByLabelText("Person"), "u1");
    await user.selectOptions(screen.getByLabelText("Kind"), "Merged");

    await waitFor(() => {
      const reads = calls.filter((c) => c.path.startsWith("/api/v1/projects/p1/changes?"));
      const last = reads[reads.length - 1];
      expect(last?.path).toContain("actor=u1");
      expect(last?.path).toContain("kind=merged");
      expect(last?.path).toContain("until_revision=5");
      expect(last?.path).toContain("requirement=r31");
    });
    expect(screen.getByText(/requirement under the pointer/)).toBeInTheDocument();
  });

  it("summarises with exact counts and keeps the AI paragraph labelled", async () => {
    const { calls } = changesApi({ "POST /api/v1/projects/p1/changes/summary": summary(true) });
    const { user } = renderWithProviders(
      <ChangesPanel projectId="p1" names={names} untilRevision={null} hoveredNode={null} onSelect={vi.fn()} />,
    );
    await user.click(screen.getByRole("checkbox", { name: /add an AI/ }));
    await user.click(screen.getByRole("button", { name: "Summarise" }));

    expect(await screen.findByText(/1 requirement added · 1 conflict found/)).toBeInTheDocument();
    const paragraph = screen.getByText(/conflicts with REQ-014/);
    expect(paragraph.querySelector(".badge-ai")).toHaveTextContent("AI");
    const post = calls.find((c) => c.method === "POST");
    expect(JSON.parse(String(post?.body))).toEqual({ since_last_visit: true, narrative: true });
  });
});

describe("Timeline", () => {
  it("lists a requirement's activity newest first, each linking to its detail", async () => {
    mockApi({
      "GET /api/v1/requirements/r31/timeline": {
        requirement_id: "r31",
        label: "REQ-031",
        kinds: ["finding", "post"],
        entries: [
          {
            at: "2027-01-12T09:00:00Z",
            kind: "finding",
            title: "Conflicting with REQ-014",
            actor_id: null,
            actor_name: null,
            link_type: "finding",
            link_id: "f1",
            detail: "Different session lengths",
          },
          {
            at: "2027-01-11T09:00:00Z",
            kind: "post",
            title: "Posted in #requirements",
            actor_id: "u1",
            actor_name: "Riya",
            link_type: null,
            link_id: null,
            detail: null,
          },
        ],
      },
    });
    renderWithProviders(<Timeline requirementId="r31" />, {
      route: "/w/w1/p/p1/map",
      path: "/w/:workspaceId/p/:projectId/map",
    });

    const timeline = screen.getByRole("region", { name: "Timeline" });
    const link = await within(timeline).findByRole("link", { name: "Conflicting with REQ-014" });
    expect(link).toHaveAttribute("href", "/w/w1/p/p1/findings?finding=f1");
    const [first, second] = within(timeline).getAllByRole("listitem");
    expect(first).toHaveTextContent("Findings");
    expect(second).toHaveTextContent("Posted in #requirements");
    expect(second).toHaveTextContent("Riya");
    expect(within(timeline).getAllByRole("option").map((o) => o.textContent)).toEqual([
      "Everything",
      "Findings",
      "Posted",
    ]);
  });
});

const point = (id: string | null, kind: RevisionPoint["kind"], label: string, revision: number): RevisionPoint => ({
  id,
  label,
  kind,
  baseline_revision: revision,
  graph_revision: revision * 10,
  at: id ? "2027-01-05T10:00:00Z" : null,
  baseline_id: kind === "baseline" ? "b1" : null,
  nodes: 10,
  edges: 4,
});

describe("TimeSlider", () => {
  it("is a native range input that moves through the revisions and marks the past read-only", () => {
    const points = [point("g1", "baseline_revision", "Revision 1", 1), point("g2", "baseline", "v1.0", 2), point(null, "now", "Now", 3)];
    const onChange = vi.fn();
    const { rerender } = render(<TimeSlider points={points} value={null} onChange={onChange} />);

    const slider = screen.getByRole("slider", { name: "Map at" });
    expect(slider).toHaveValue("2");
    expect(screen.queryByText(/read-only/)).not.toBeInTheDocument();
    fireEvent.change(slider, { target: { value: "1" } });
    expect(onChange).toHaveBeenCalledWith("g2", points[1]);

    rerender(<TimeSlider points={points} value="g2" onChange={onChange} />);
    expect(screen.getByRole("slider")).toHaveAttribute("aria-valuetext", expect.stringContaining("v1.0"));
    expect(screen.getByText(/read-only/)).toBeInTheDocument();
  });

  it("explains itself until there is a past to show", () => {
    render(<TimeSlider points={[point(null, "now", "Now", 1)]} value={null} onChange={vi.fn()} />);
    expect(screen.queryByRole("slider")).not.toBeInTheDocument();
    expect(screen.getByText(/fills in as changes are merged/)).toBeInTheDocument();
  });
});

describe("preview overlays", () => {
  it("fades what a change request resolves and makes its new findings glow", () => {
    const preview: GraphPreview = {
      change_request_id: "cr1",
      number: 1,
      kind: "edit",
      requirement_id: "r31",
      report_id: "rep1",
      checks_pending: false,
      stale: [],
      fading_edge_ids: ["edge-1"],
      glowing_edges: [{ source: "r31", target: "r20", kind: "conflict", labels: ["REQ-031", "REQ-020"], reason: "New" }],
      affected_node_ids: ["r31", "r20"],
      removed_node_ids: [],
      sentences: [],
    };
    const overlay = overlayOf(preview);
    expect([...overlay.fadingEdgeIds]).toEqual(["edge-1"]);
    expect(overlay.ghostEdges).toHaveLength(1);
    expect(overlay.affectedNodeIds.has("r20")).toBe(true);
  });

  it("draws a pre-flight draft as a ghost node with edges only for relations it can name", () => {
    const overlay = draftOverlay({
      projectId: "p1",
      findings: [
        { category: "Conflicting", requirement_id: "r14", label: "REQ-014" },
        { category: "Ambiguous", requirement_id: null, label: null },
      ],
    });
    expect(overlay.ghostNode?.label).toBe("Draft");
    expect(overlay.ghostEdges).toEqual([
      expect.objectContaining({ target: "r14", kind: "conflict", reason: "Likely conflicting (pre-flight)" }),
    ]);
  });
});
