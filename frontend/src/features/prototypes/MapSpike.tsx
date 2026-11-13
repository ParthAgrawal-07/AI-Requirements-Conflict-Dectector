// Map-library spike (Abhijeet with Dhavni — Sprint 0): React Flow vs Cytoscape.js at 500 nodes
// and 2,000 edges. Both libraries draw the same seeded graph; "Measure" pans for 5 s and reports
// frames per second, "Apply delta" adds 10 nodes / 40 edges like a graph.delta would.
// Method and the results table: docs/spikes/map.md. Throwaway — the chosen library's real map
// is built in Sprint 3 (US-14).

import { useEffect, useMemo, useRef, useState } from "react";
import ReactFlow, { type Edge, type Node, type ReactFlowInstance } from "reactflow";
import "reactflow/dist/style.css";
import cytoscape from "cytoscape";
import { Button } from "../../components/Button";

export interface SpikeGraph {
  nodes: { id: string; x: number; y: number }[];
  edges: { id: string; source: string; target: string; conflict: boolean }[];
}

/** Deterministic graph so both libraries (and every laptop) draw the same thing. */
export function makeGraph(nodeCount: number, edgeCount: number, seed = 42): SpikeGraph {
  let state = seed;
  const random = () => {
    state = (state * 1664525 + 1013904223) % 2 ** 32;
    return state / 2 ** 32;
  };
  const columns = Math.ceil(Math.sqrt(nodeCount));
  const nodes = Array.from({ length: nodeCount }, (_, i) => ({
    id: `REQ-${String(i + 1).padStart(3, "0")}`,
    x: (i % columns) * 140 + random() * 40,
    y: Math.floor(i / columns) * 80 + random() * 30,
  }));
  const edges = Array.from({ length: edgeCount }, (_, i) => {
    const a = Math.floor(random() * nodeCount);
    let b = Math.floor(random() * nodeCount);
    if (b === a) b = (a + 1) % nodeCount;
    return { id: `e${i}`, source: nodes[a].id, target: nodes[b].id, conflict: random() < 0.1 };
  });
  return { nodes, edges };
}

function measureFps(pan: (dx: number) => void, seconds = 5): Promise<number> {
  return new Promise((resolve) => {
    let frames = 0;
    const start = performance.now();
    const step = (now: number) => {
      frames += 1;
      pan(Math.sin((now - start) / 300) * 4);
      if (now - start < seconds * 1000) requestAnimationFrame(step);
      else resolve(Math.round((frames / (now - start)) * 1000));
    };
    requestAnimationFrame(step);
  });
}

type Library = "reactflow" | "cytoscape";

export function MapSpike() {
  const [library, setLibrary] = useState<Library>("reactflow");
  const [size, setSize] = useState({ nodes: 500, edges: 2000 });
  const [graph, setGraph] = useState(() => makeGraph(500, 2000));
  const [build, setBuild] = useState(0); // a rebuild remounts the view; a delta does not
  const [results, setResults] = useState<string[]>([]);
  const mountedAt = useRef(performance.now());
  const panRef = useRef<(dx: number) => void>(() => undefined);
  const deltaRef = useRef<(g: SpikeGraph) => void>(() => undefined);

  const log = (line: string) => setResults((current) => [`${library}: ${line}`, ...current]);

  useEffect(() => {
    mountedAt.current = performance.now();
  }, [library, graph]);

  const applyDelta = () => {
    const start = performance.now();
    const extra = makeGraph(size.nodes + 10, 40, Date.now() % 1000);
    const added = extra.nodes.slice(size.nodes);
    const next: SpikeGraph = {
      nodes: [...graph.nodes, ...added],
      edges: [
        ...graph.edges,
        ...extra.edges.map((edge, i) => ({
          ...edge,
          id: `d${Date.now()}-${i}`,
          source: added[i % added.length].id,
        })),
      ],
    };
    deltaRef.current(next);
    setGraph(next);
    requestAnimationFrame(() => log(`delta applied in ${Math.round(performance.now() - start)} ms`));
  };

  return (
    <div className="page">
      <h1>Map library spike</h1>
      <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <label>
          Library{" "}
          <select
            className="select"
            value={library}
            onChange={(event) => setLibrary(event.target.value as Library)}
          >
            <option value="reactflow">React Flow 11</option>
            <option value="cytoscape">Cytoscape.js 3</option>
          </select>
        </label>
        <label>
          Nodes{" "}
          <input
            className="input"
            type="number"
            value={size.nodes}
            style={{ width: 90 }}
            onChange={(event) => setSize({ ...size, nodes: Number(event.target.value) })}
          />
        </label>
        <label>
          Edges{" "}
          <input
            className="input"
            type="number"
            value={size.edges}
            style={{ width: 90 }}
            onChange={(event) => setSize({ ...size, edges: Number(event.target.value) })}
          />
        </label>
        <Button
          onClick={() => {
            setGraph(makeGraph(size.nodes, size.edges));
            setBuild(build + 1);
          }}
        >
          Rebuild
        </Button>
        <Button
          variant="primary"
          onClick={async () => log(`pan ${await measureFps(panRef.current)} fps`)}
        >
          Measure
        </Button>
        <Button onClick={applyDelta}>Apply delta</Button>
      </div>
      <div className="card" style={{ height: 560, marginTop: 16 }}>
        {library === "reactflow" ? (
          <FlowView
            graph={graph}
            onReady={(pan) => {
              panRef.current = pan;
              log(`first paint ${Math.round(performance.now() - mountedAt.current)} ms`);
            }}
          />
        ) : (
          <CytoscapeView
            key={build}
            graph={graph}
            onReady={(pan, delta) => {
              panRef.current = pan;
              deltaRef.current = delta;
              log(`first paint ${Math.round(performance.now() - mountedAt.current)} ms`);
            }}
          />
        )}
      </div>
      <h2>Results (copy into docs/spikes/map.md)</h2>
      <pre className="card" style={{ padding: 12 }}>
        {results.join("\n") || "Nothing measured yet."}
      </pre>
    </div>
  );
}

function FlowView({ graph, onReady }: { graph: SpikeGraph; onReady: (pan: (dx: number) => void) => void }) {
  const nodes = useMemo<Node[]>(
    () => graph.nodes.map((n) => ({ id: n.id, position: { x: n.x, y: n.y }, data: { label: n.id } })),
    [graph],
  );
  const edges = useMemo<Edge[]>(
    () =>
      graph.edges.map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        style: e.conflict ? { stroke: "#c2410c", strokeWidth: 2 } : undefined,
      })),
    [graph],
  );
  const onInit = (instance: ReactFlowInstance) => {
    onReady((dx) => {
      const viewport = instance.getViewport();
      instance.setViewport({ ...viewport, x: viewport.x + dx });
    });
  };
  return <ReactFlow nodes={nodes} edges={edges} onInit={onInit} fitView minZoom={0.05} />;
}

function CytoscapeView({
  graph,
  onReady,
}: {
  graph: SpikeGraph;
  onReady: (pan: (dx: number) => void, delta: (g: SpikeGraph) => void) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!container.current) return;
    const cy = cytoscape({
      container: container.current,
      elements: [
        ...graph.nodes.map((n) => ({ data: { id: n.id }, position: { x: n.x, y: n.y } })),
        ...graph.edges.map((e) => ({ data: { ...e } })),
      ],
      layout: { name: "preset" },
      style: [
        { selector: "node", style: { label: "data(id)", "font-size": 8, shape: "round-rectangle" } },
        { selector: "edge[?conflict]", style: { "line-color": "#c2410c", width: 2 } },
      ],
    });
    onReady(
      (dx) => cy.panBy({ x: dx, y: 0 }),
      (next) => {
        const known = new Set(cy.elements().map((el) => el.id()));
        cy.add([
          ...next.nodes.filter((n) => !known.has(n.id)).map((n) => ({ data: { id: n.id }, position: { x: n.x, y: n.y } })),
          ...next.edges.filter((e) => !known.has(e.id)).map((e) => ({ data: { ...e } })),
        ]);
      },
    );
    return () => cy.destroy();
    // Mount once per build (the parent changes `key` to rebuild); deltas go through cy.add so the
    // spike measures an incremental update, not a full redraw.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return <div ref={container} style={{ width: "100%", height: "100%" }} />;
}
