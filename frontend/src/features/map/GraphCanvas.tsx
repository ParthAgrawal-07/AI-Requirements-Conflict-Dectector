// The map canvas (Abhijeet — US-14; Cytoscape.js, chosen in the Sprint 0 spike for 500 nodes and
// 2,000 edges, NFR-33). The canvas is updated in place: elements are added, changed and removed by
// id, so a delta never re-lays-out the map and nothing jumps (interface design §9 "Stable layout").

import { useEffect, useRef } from "react";
import cytoscape, { type Core, type ElementDefinition, type StylesheetStyle } from "cytoscape";
import type { EdgeKind, GraphEdge, GraphNode } from "./api";

export interface GraphCanvasProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  pulsing: ReadonlySet<string>;
  focusId: string | null;
  focusDepth: 1 | 2;
  onSelect: (requirementId: string | null) => void;
  /** Called with positions the canvas chose or the member dragged; null = read-only layout. */
  onMoved: ((positions: { requirement_id: string; x: number; y: number }[]) => void) | null;
}

const SHAPE: Record<string, string> = {
  functional: "round-rectangle",
  non_functional: "ellipse",
  constraint: "diamond",
};
const BADGE: Partial<Record<EdgeKind, string>> = { ambiguous: "?", incomplete: "…" };

/** Nodes and the edges between two requirements. A single-requirement finding is a badge on its
 *  node's label ("REQ-040 ?"), not a loop. Classes carry everything the stylesheet needs. */
export function toElements(nodes: GraphNode[], edges: GraphEdge[]): ElementDefinition[] {
  const badges = new Map<string, Set<string>>();
  for (const edge of edges) {
    const badge = BADGE[edge.kind];
    if (edge.source === edge.target && badge) {
      badges.set(edge.source, (badges.get(edge.source) ?? new Set()).add(badge));
    }
  }
  const ids = new Set(nodes.map((n) => n.id));
  return [
    ...nodes.map(
      (node): ElementDefinition => ({
        group: "nodes",
        data: {
          id: node.id,
          label: [node.label ?? "—", ...(badges.get(node.id) ?? [])].join(" "),
          req_type: node.req_type ?? "",
        },
        classes: [
          `state-${node.state.toLowerCase()}`,
          node.is_protected ? "protected" : "",
          node.origin === "post" ? "posted" : "",
        ]
          .filter(Boolean)
          .join(" "),
        position: node.x !== null && node.y !== null ? { x: node.x, y: node.y } : undefined,
      }),
    ),
    ...edges
      .filter((e) => e.source !== e.target && ids.has(e.source) && ids.has(e.target))
      .map(
        (edge): ElementDefinition => ({
          group: "edges",
          data: { id: edge.id, source: edge.source, target: edge.target },
          classes: `kind-${edge.kind} status-${edge.status}${edge.severity === "high" ? " high" : ""}`,
        }),
      ),
  ];
}

const STYLE: StylesheetStyle[] = [
  {
    selector: "node",
    style: {
      label: "data(label)",
      "font-family": "IBM Plex Mono, monospace",
      "font-size": 11,
      "text-valign": "center",
      width: 72,
      height: 32,
      "background-color": "#faf8f3",
      "border-width": 2,
      "border-color": "#1b1b1d",
      shape: "round-rectangle",
    },
  },
  ...Object.entries(SHAPE).map(([type, shape]) => ({
    selector: `node[req_type = "${type}"]`,
    style: { shape: shape as cytoscape.Css.NodeShape },
  })),
  { selector: "node.state-approved, node.state-implemented", style: { "border-style": "solid" } },
  { selector: "node.state-proposed, node.state-under_review", style: { "border-style": "dashed", "border-color": "#9a6a00" } },
  { selector: "node.state-rejected, node.state-deprecated", style: { "border-style": "dotted", opacity: 0.5 } },
  { selector: "node.protected", style: { "border-width": 4 } },
  { selector: "node:selected", style: { "border-color": "#1f5bd8", "border-width": 4 } },
  { selector: "edge", style: { width: 2, "curve-style": "bezier", "line-color": "#7a7a80", opacity: 0.8 } },
  // Kind by colour AND line style (never colour alone, NFR-29); the legend says it in words.
  { selector: "edge.kind-conflict", style: { "line-color": "#c2410c", "line-style": "solid", width: 3 } },
  { selector: "edge.kind-duplicate", style: { "line-color": "#6d28d9", "line-style": "dashed" } },
  {
    selector: "edge.kind-depends_on",
    style: { "line-color": "#4a4a4f", "target-arrow-shape": "triangle", "target-arrow-color": "#4a4a4f" },
  },
  { selector: "edge.kind-link", style: { "line-color": "#b9b3a6", "line-style": "dotted" } },
  { selector: "edge.high", style: { width: 5 } },
  { selector: "edge.status-confirmed", style: { opacity: 1 } },
  { selector: ".faded", style: { opacity: 0.12 } },
  { selector: ".pulse", style: { "overlay-color": "#1f5bd8", "overlay-opacity": 0.25, "overlay-padding": 8 } },
];

export function GraphCanvas({ nodes, edges, pulsing, focusId, focusDepth, onSelect, onMoved }: GraphCanvasProps) {
  const container = useRef<HTMLDivElement>(null);
  const cy = useRef<Core | null>(null);
  const callbacks = useRef({ onSelect, onMoved });
  callbacks.current = { onSelect, onMoved };

  useEffect(() => {
    if (!container.current) return;
    const instance = cytoscape({
      container: container.current,
      style: STYLE,
      wheelSensitivity: 0.3,
      textureOnViewport: true, // pans and zooms of a 500-node map stay smooth (NFR-33)
      hideEdgesOnViewport: true,
      minZoom: 0.1,
      maxZoom: 3,
    });
    instance.on("tap", "node", (event) => callbacks.current.onSelect(event.target.id()));
    instance.on("tap", (event) => {
      if (event.target === instance) callbacks.current.onSelect(null);
    });
    instance.on("dragfree", "node", (event) => {
      const { x, y } = event.target.position();
      callbacks.current.onMoved?.([{ requirement_id: event.target.id(), x, y }]);
    });
    cy.current = instance;
    return () => {
      instance.destroy();
      cy.current = null;
    };
  }, []);

  // Data: add, change and remove by id — never rebuild.
  useEffect(() => {
    const instance = cy.current;
    if (!instance) return;
    const wanted = toElements(nodes, edges);
    const wantedIds = new Set(wanted.map((element) => String(element.data.id)));
    const unplaced: string[] = [];
    instance.batch(() => {
      instance.elements().forEach((element) => {
        if (!wantedIds.has(element.id())) element.remove();
      });
      for (const element of wanted) {
        const id = String(element.data.id);
        const existing = instance.getElementById(id);
        if (existing.nonempty()) {
          existing.data(element.data);
          existing.classes(element.classes ?? "");
          if (element.position && !existing.grabbed()) existing.position(element.position);
        } else {
          instance.add(element);
          if (element.group === "nodes" && !element.position) unplaced.push(id);
        }
      }
    });
    if (unplaced.length === 0) return;
    // Lay out only what nobody has placed: everything when the map is new, else just the newcomers
    // in a grid beside the existing layout. The result is saved so every viewer sees the same map.
    const fresh = unplaced.length === nodes.length;
    const placing = new Set(unplaced);
    const targets = instance.nodes().filter((node) => placing.has(node.id()));
    const box = instance.nodes().difference(targets).boundingBox();
    const layout = fresh
      ? instance.layout({ name: "cose", animate: false, randomize: true, nodeRepulsion: () => 8000 })
      : targets.layout({
          name: "grid",
          animate: false,
          boundingBox: { x1: box.x2 + 80, y1: box.y1, w: 300, h: Math.max(200, box.h) },
        });
    layout.run();
    if (fresh) instance.fit(undefined, 40);
    callbacks.current.onMoved?.(
      targets.nodes().map((node) => ({ requirement_id: node.id(), ...node.position() })),
    );
  }, [nodes, edges]);

  // Pulses and focus are classes on what is already drawn.
  useEffect(() => {
    const instance = cy.current;
    if (!instance) return;
    instance.batch(() => {
      instance.elements().removeClass("pulse faded");
      instance.elements().filter((element) => pulsing.has(element.id())).addClass("pulse");
      if (focusId) {
        const focus = instance.getElementById(focusId);
        if (focus.nonempty()) {
          let near = focus.closedNeighborhood();
          if (focusDepth === 2) near = near.closedNeighborhood();
          instance.elements().difference(near).addClass("faded");
          focus.select();
        }
      }
    });
  }, [pulsing, focusId, focusDepth, nodes, edges]);

  return (
    <div
      ref={container}
      className="graph-canvas"
      role="img"
      aria-label={`Requirements map: ${nodes.length} requirements, ${edges.length} relationships. The table view lists the same data.`}
    />
  );
}
