import { afterEach, describe, expect, it, vi } from "vitest";
import type { RealtimeEvent } from "../src/api/types";
import type { EventHandler } from "../src/app/socket";
import { applyDelta, type GraphDelta, type GraphEdge, type GraphNode, type GraphSnapshot } from "../src/features/map/api";
import type { GraphCanvasProps } from "../src/features/map/GraphCanvas";
import { toElements } from "../src/features/map/GraphCanvas";
import { MapPage } from "../src/features/map/MapPage";
import { applyAll } from "../src/features/map/useGraphDeltas";
import { act, mockApi, renderWithProviders, screen, waitFor, within } from "./test-utils";

vi.mock("../src/app/auth", async (original) => ({
  ...(await original<typeof import("../src/app/auth")>()),
  useAuth: () => ({ user: { id: "u-me", full_name: "Me" }, token: "t", loading: false }),
}));

// The socket is replaced by a handle the test pushes events through.
const realtime = vi.hoisted(() => ({ handler: null as EventHandler | null }));
vi.mock("../src/app/socket", async (original) => ({
  ...(await original<typeof import("../src/app/socket")>()),
  useProjectRealtime: () => undefined,
  useRealtimeEvents: (handler: EventHandler) => {
    realtime.handler = handler;
  },
}));

// jsdom has no canvas: the map is a list of what Cytoscape would draw.
vi.mock("../src/features/map/GraphCanvas", async (original) => ({
  ...(await original<typeof import("../src/features/map/GraphCanvas")>()),
  GraphCanvas: ({ nodes, edges, onSelect }: GraphCanvasProps) => (
    <ul aria-label="canvas">
      {nodes.map((node) => (
        <li key={node.id}>
          <button type="button" onClick={() => onSelect(node.id)}>
            {node.label}
          </button>
        </li>
      ))}
      {edges.map((edge) => (
        <li key={edge.id}>{`${edge.source} ${edge.kind} ${edge.target}`}</li>
      ))}
    </ul>
  ),
}));

afterEach(() => {
  vi.unstubAllGlobals();
  realtime.handler = null;
});

const node = (id: string, label: string, overrides: Partial<GraphNode> = {}): GraphNode => ({
  id,
  label,
  state: "Approved",
  group: null,
  owner_id: null,
  req_type: "functional",
  origin: "document",
  is_protected: false,
  open_issues: 0,
  x: 10,
  y: 20,
  ...overrides,
});
const edge = (id: string, source: string, target: string, kind: GraphEdge["kind"] = "conflict"): GraphEdge => ({
  id,
  source,
  target,
  kind,
  status: "flagged",
  severity: "high",
  confidence: 0.86,
});
const snapshot = (revision: number, nodes: GraphNode[], edges: GraphEdge[] = []): GraphSnapshot => ({
  project_id: "p1",
  revision,
  nodes,
  edges,
});
const delta = (from: number, overrides: Partial<GraphDelta> = {}): GraphDelta => ({
  project_id: "p1",
  from_revision: from,
  to_revision: from + 1,
  actor_id: "u-arjun",
  actor_name: "Arjun",
  added: { nodes: [], edges: [] },
  changed: { nodes: [], edges: [] },
  removed: { node_ids: [], edge_ids: [] },
  sentences: [],
  ...overrides,
});
const event = (data: GraphDelta): RealtimeEvent => ({
  type: "graph.delta",
  workspace_id: "w1",
  project_id: "p1",
  channel_id: null,
  entity_id: null,
  at: "2026-11-21T10:42:00Z",
  data: data as unknown as Record<string, unknown>,
});

const R14 = node("r14", "REQ-014");
const R31 = node("r31", "REQ-031", { state: "Proposed", origin: "post", x: null, y: null });
const ADDED = delta(3, {
  added: { nodes: [R31], edges: [edge("f1", "r31", "r14")] },
  sentences: ["Arjun added REQ-031; it conflicts with REQ-014."],
});

describe("applyDelta and applyAll", () => {
  it("applies a delta that follows the snapshot and keeps known positions", () => {
    const moved = applyDelta(snapshot(3, [R14]), delta(3, { changed: { nodes: [{ ...R14, state: "Deprecated", x: null, y: null }], edges: [] } }));
    expect(moved?.revision).toBe(4);
    expect(moved?.nodes[0]).toMatchObject({ state: "Deprecated", x: 10, y: 20 });
  });

  it("returns null for a gap so the map re-fetches", () => {
    expect(applyDelta(snapshot(3, [R14]), delta(5))).toBeNull();
    expect(applyAll(snapshot(3, [R14]), [delta(3), delta(5)])).toBeNull();
  });

  it("applies a batch in revision order and skips deltas already included", () => {
    const removed = delta(4, { removed: { node_ids: ["r31"], edge_ids: ["f1"] } });
    const next = applyAll(snapshot(3, [R14]), [removed, ADDED, delta(1)]);
    expect(next?.revision).toBe(5);
    expect(next?.nodes.map((n) => n.id)).toEqual(["r14"]);
    expect(next?.edges).toEqual([]);
  });
});

describe("toElements", () => {
  it("draws a single-requirement finding as a badge on its node, not a loop", () => {
    const elements = toElements([R14, node("r40", "REQ-040")], [edge("f2", "r40", "r40", "ambiguous"), edge("f1", "r40", "r14")]);
    expect(elements.find((e) => e.data.id === "r40")?.data.label).toBe("REQ-040 ?");
    expect(elements.filter((e) => e.group === "edges").map((e) => e.data.id)).toEqual(["f1"]);
    expect(elements.find((e) => e.data.id === "f1")?.classes).toBe("kind-conflict status-flagged high");
  });

  it("leaves unplaced nodes without a position for the layout", () => {
    expect(toElements([R31], [])[0].position).toBeUndefined();
    expect(toElements([R14], [])[0].position).toEqual({ x: 10, y: 20 });
  });
});

const ROUTE = "/w/w1/p/p1/map";
const PATH = "/w/:workspaceId/p/:projectId/map";

function api(graph: GraphSnapshot) {
  return mockApi({
    "GET /api/v1/projects/p1/graph": graph,
    "GET /api/v1/me/permissions?project=p1": {
      workspace_id: "w1",
      project_id: "p1",
      role: { id: "r", name: "Developer", is_default: true },
      permissions: ["view", "req.comment"],
      protected_only: [],
    },
    "GET /api/v1/workspaces/w1/members": [],
  });
}

describe("MapPage", () => {
  it("adds the new node and edge from a delta and says so in the feed", async () => {
    api(snapshot(3, [R14]));
    renderWithProviders(<MapPage />, { route: ROUTE, path: PATH });
    const canvas = await screen.findByRole("list", { name: "canvas" });
    expect(within(canvas).getByText("REQ-014")).toBeInTheDocument();

    act(() => realtime.handler?.(event(ADDED)));

    expect(await within(canvas).findByText("REQ-031")).toBeInTheDocument();
    expect(within(canvas).getByText("r31 conflict r14")).toBeInTheDocument();
    const feed = screen.getByRole("region", { name: "Changes" });
    expect(within(feed).getByRole("button", { name: /Arjun added REQ-031; it conflicts with REQ-014\./ })).toBeInTheDocument();
    expect(screen.getByText("2 requirements · revision 4")).toBeInTheDocument();
  });

  it("re-fetches the snapshot when a delta does not follow the revision held", async () => {
    const { calls } = api(snapshot(3, [R14]));
    renderWithProviders(<MapPage />, { route: ROUTE, path: PATH });
    await screen.findByRole("list", { name: "canvas" });

    act(() => realtime.handler?.(event(delta(7, { sentences: ["Arjun added REQ-050."] }))));

    await waitFor(() => expect(calls.filter((c) => c.path === "/api/v1/projects/p1/graph")).toHaveLength(2));
  });

  it("ignores deltas of another project", async () => {
    const { calls } = api(snapshot(3, [R14]));
    renderWithProviders(<MapPage />, { route: ROUTE, path: PATH });
    await screen.findByRole("list", { name: "canvas" });

    act(() => realtime.handler?.({ ...event(delta(7)), project_id: "p2" }));

    await new Promise((resolve) => setTimeout(resolve, 300));
    expect(calls.filter((c) => c.path === "/api/v1/projects/p1/graph")).toHaveLength(1);
  });

  it("shows the same data as tables", async () => {
    api(snapshot(4, [R14, { ...R31, x: 0, y: 0 }], [edge("f1", "r31", "r14"), edge("f2", "r31", "r31", "incomplete")]));
    const { user } = renderWithProviders(<MapPage />, { route: ROUTE, path: PATH });
    await screen.findByRole("list", { name: "canvas" });

    await user.click(screen.getByRole("button", { name: "Table view" }));

    expect(screen.getByRole("table", { name: "Requirements (2)" })).toBeInTheDocument();
    const relationships = screen.getByRole("table", { name: "Relationships (2)" });
    expect(within(relationships).getByText("REQ-031 conflicts with REQ-014")).toBeInTheDocument();
    expect(within(relationships).getByText("REQ-031 is missing information")).toBeInTheDocument();
  });

  it("hides rejected and deprecated requirements until asked", async () => {
    api(snapshot(3, [R14, node("r9", "REQ-009", { state: "Deprecated" })]));
    const { user } = renderWithProviders(<MapPage />, { route: ROUTE, path: PATH });
    const canvas = await screen.findByRole("list", { name: "canvas" });
    expect(within(canvas).queryByText("REQ-009")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Rejected / deprecated" }));

    expect(within(canvas).getByText("REQ-009")).toBeInTheDocument();
  });
});
