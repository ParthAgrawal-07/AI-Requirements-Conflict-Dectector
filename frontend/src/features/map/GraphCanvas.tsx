// The map canvas (Abhijeet — US-14; Cytoscape.js, chosen in the Sprint 0 spike for 500 nodes and
// 2,000 edges, NFR-33). The canvas is updated in place: elements are added, changed and removed by
// id, so a delta never re-lays-out the map and nothing jumps (interface design §9 "Stable layout").

import { useEffect, useRef } from "react";
import cytoscape, { type Core, type ElementDefinition, type StylesheetStyle } from "cytoscape";
import type { EdgeKind, GraphEdge, GraphNode } from "./api";
import type { PreviewOverlay } from "./history";

export interface GraphCanvasProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  pulsing: ReadonlySet<string>;
  focusId: string | null;
  focusDepth: 1 | 2;
  onSelect: (requirementId: string | null) => void;
  /** Called with positions the canvas chose or the member dragged; null = read-only layout. */
  onMoved: ((positions: { requirement_id: string; x: number; y: number }[]) => void) | null;
  /** US-50: what a change request or a draft would do, drawn over the map (never saved). */
  preview?: PreviewOverlay | null;
  /** US-55: the node under the pointer (null when it leaves), so the panel can list its changes. */
  onHover?: (requirementId: string | null) => void;
  /** US-50: cluster nodes into boxes by this label (stakeholder group, type, owner); null = none. */
  groupOf?: ((node: GraphNode) => string | null) | null;
}

const GHOST = "ghost-";
const CLUSTER = "cluster:";
const SHAPE: Record<string, string> = {
  functional: "round-rectangle",
  non_functional: "ellipse",
  constraint: "diamond",
};
const BADGE: Partial<Record<EdgeKind, string>> = { ambiguous: "?", incomplete: "…" };

/** Nodes and the edges between two requirements. A single-requirement finding is a badge on its
 *  node's label ("REQ-040 ?"), not a loop. Classes carry everything the stylesheet needs. */
export function toElements(
  nodes: GraphNode[],
  edges: GraphEdge[],
  preview: PreviewOverlay | null = null,
  groupOf: ((node: GraphNode) => string | null) | null = null,
): ElementDefinition[] {
  // US-50: optional compound parent nodes for stakeholder/type/owner clusters.
  const parents = new Map<string, string>();
  if (groupOf) {
    for (const node of nodes) {
      const label = groupOf(node);
      if (label) parents.set(node.id, `${CLUSTER}${label}`);
    }
  }

  const parentElements: ElementDefinition[] = [
    ...new Set(parents.values()),
  ].map((id) => ({
    group: "nodes",
    data: { id, label: id.slice(CLUSTER.length) },
    classes: "cluster",
  }));
  const badges = new Map<string, Set<string>>();
  for (const edge of edges) {
    const badge = BADGE[edge.kind];
    if (edge.source === edge.target && badge) {
      badges.set(edge.source, (badges.get(edge.source) ?? new Set()).add(badge));
    }
  }
  const ids = new Set(nodes.map((n) => n.id));
  return [
    ...parentElements,
    ...nodes.map(
      (node): ElementDefinition => ({
        group: "nodes",
        data: {
          id: node.id,
          label: [node.label ?? "—", ...(badges.get(node.id) ?? [])].join(" "),
          req_type: node.req_type ?? "",
          ...(parents.has(node.id) ? { parent: parents.get(node.id) } : {}),
        },
        classes: [
          `state-${node.state.toLowerCase()}`,
          node.is_protected ? "protected" : "",
          node.origin === "post" ? "posted" : "",
          preview?.affectedNodeIds.has(node.id) ? "preview-affected" : "",
          preview?.removedNodeIds.has(node.id) ? "preview-removed" : "",
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
          classes: [
            `kind-${edge.kind}`,
            `status-${edge.status}`,
            edge.severity === "high" ? "high" : "",
            preview?.fadingEdgeIds.has(edge.id) ? "preview-fade" : "",
            edge.link_kind ? "human-link" : "",
          ]
            .filter(Boolean)
            .join(" "),
        }),
      ),
    ...ghosts(preview, nodes, ids),
  ];
}

/** US-50: proposed additions are ghost elements, never persisted to the graph. */
function ghosts(
  preview: PreviewOverlay | null,
  nodes: GraphNode[],
  ids: Set<string>,
): ElementDefinition[] {
  if (!preview) return [];

  const result: ElementDefinition[] = [];

  if (preview.ghostNode) {
    // Place the draft beside affected requirements; fall back to the existing map centre.
    const anchors = nodes.filter(
      (node) =>
        preview.affectedNodeIds.has(node.id) &&
        node.x !== null &&
        node.y !== null,
    );
    const positioned = anchors.length
      ? anchors
      : nodes.filter((node) => node.x !== null && node.y !== null);
    const position =
      positioned.length > 0
        ? {
            x: positioned.reduce((sum, node) => sum + node.x!, 0) / positioned.length,
            y: positioned.reduce((sum, node) => sum + node.y!, 0) / positioned.length,
          }
        : { x: 80, y: 80 };

    result.push({
      group: "nodes",
      data: {
        id: `${GHOST}${preview.ghostNode.id}`,
        label: preview.ghostNode.label,
      },
      position,
      classes: "preview-ghost",
    });
  }

  preview.ghostEdges.forEach((edge, index) => {
    if (
      edge.source === edge.target ||
      !ids.has(edge.source) ||
      !ids.has(edge.target)
    ) {
      return;
    }

    result.push({
      group: "edges",
      data: {
        // Include the index so parallel proposed edges never share an element ID.
        id: `${GHOST}edge-${index}-${edge.source}-${edge.target}`,
        source: edge.source,
        target: edge.target,
        label: edge.labels.join(", "),
      },
      classes: "preview-ghost ghost-edge",
    });
  });

  return result;
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
  { selector: "node.cluster", style: { label: "data(label)", shape: "round-rectangle", "background-color": "#e8e4dc", "background-opacity": 0.35, "border-color": "#aaa397", "border-width": 1, "border-style": "dashed", "font-size": 12, "text-valign": "top", "text-halign": "center", padding: "16px" } },
  { selector: "node.preview-affected", style: { "border-color": "#1f5bd8", "border-width": 4 } },
  { selector: "node.preview-removed", style: { "background-color": "#f5d6d6", "border-color": "#b42318", opacity: 0.45 } },
  { selector: "node.preview-ghost", style: { "background-color": "#dbeafe", "border-color": "#1f5bd8", "border-style": "dashed", "border-width": 2, opacity: 0.8 } },
  { selector: "edge.preview-fade", style: { opacity: 0.12 } },
  { selector: "edge.human-link", style: { "line-style": "dashed", "line-color": "#0f766e" } },
  { selector: "edge.preview-ghost", style: { "line-style": "dashed", "line-color": "#1f5bd8", opacity: 0.7, width: 2 } },
];


export function GraphCanvas({ nodes, edges, pulsing, focusId, focusDepth, onSelect, onMoved, preview = null, onHover, groupOf = null }: GraphCanvasProps) {
  const container = useRef<HTMLDivElement>(null);
  const cy = useRef<Core | null>(null);
  const callbacks = useRef({ onSelect, onMoved, onHover });
  callbacks.current = { onSelect, onMoved, onHover };

  useEffect(() => {
    if (!container.current) return;
    const instance = cytoscape({
      container: container.current,
      style: STYLE,
      wheelSensitivity: 0.3,
      textureOnViewport: true,
      hideEdgesOnViewport: true,
      minZoom: 0.1,
      maxZoom: 3,
    });

    instance.on("tap", "node", (event) => {
      const node = event.target;
      if (node.id().startsWith(GHOST) || node.id().startsWith(CLUSTER)) return;
      callbacks.current.onSelect(node.id());
    });

    instance.on("tap", (event) => {
      if (event.target === instance) callbacks.current.onSelect(null);
    });

    instance.on("mouseover", "node", (event) => {
      const id = event.target.id();
      callbacks.current.onHover?.(
        id.startsWith(GHOST) || id.startsWith(CLUSTER) ? null : id,
      );
    });

    instance.on("mouseout", "node", () => {
      callbacks.current.onHover?.(null);
    });

    instance.on("dragfree", "node", (event) => {
      const node = event.target;
      if (node.id().startsWith(GHOST) || node.id().startsWith(CLUSTER)) return;
      const { x, y } = node.position();
      callbacks.current.onMoved?.([{ requirement_id: node.id(), x, y }]);
    });

    cy.current = instance;
    return () => {
      instance.destroy();
      cy.current = null;
    };
  }, []);

  // Data: add, change and remove by id — never rebuild.
  // Lay out only what nobody has placed: everything when the map is new, else just the new
  // comers in a grid beside the existing layout. The result is saved so every viewer sees the same map.
  useEffect(() => {
    const instance = cy.current;
    if (!instance) return;

    const wanted = toElements(nodes, edges, preview, groupOf);
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
          if (element.group === "nodes") {
            const parent = element.data.parent;
            if (parent !== existing.data("parent")) {
              existing.move({ parent });
            }
          }
          existing.data(element.data);
          existing.classes(element.classes ?? "");
          if (element.position && !existing.grabbed()) {
            existing.position(element.position);
          }
        } else {
          instance.add(element);
          if (
            element.group === "nodes" &&
            !element.position &&
            !id.startsWith(GHOST) &&
            !id.startsWith(CLUSTER)
          ) {
            unplaced.push(id);
          }
        }
      }
    });

    if (unplaced.length === 0) return;

    const fresh = unplaced.length === nodes.length;
    const placing = new Set(unplaced);
    const targets = instance.nodes().filter((node) => placing.has(node.id()));
    const box = instance.nodes().difference(targets).boundingBox();

    const layout = fresh
      ? instance.layout({
          name: "cose",
          animate: false,
          randomize: true,
          nodeRepulsion: () => 8000,
        })
      : targets.layout({
          name: "grid",
          animate: false,
          boundingBox: {
            x1: box.x2 + 80,
            y1: box.y1,
            w: 300,
            h: Math.max(200, box.h),
          },
        });

    layout.run();

    if (fresh) instance.fit(undefined, 40);

    callbacks.current.onMoved?.(
      targets.nodes().map((node) => ({
        requirement_id: node.id(),
        ...node.position(),
      })),
    );
  }, [nodes, edges, preview, groupOf]);

  // Update pulses and focus without rebuilding the graph.
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
