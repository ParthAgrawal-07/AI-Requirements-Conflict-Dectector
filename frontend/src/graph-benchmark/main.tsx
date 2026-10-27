import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import ReactFlow, { Background, Controls, type Edge, type Node } from "reactflow";
import cytoscape, { type Core } from "cytoscape";
import "reactflow/dist/style.css";
import "./styles.css";

const NODE_COUNT = 500;
const EDGE_COUNT = 2000;
type Result = {
  library: string;
  renderMs: number;
  nodeCount: number;
  edgeCount: number;
  timestamp: string;
};

function makeGraph() {
  const nodes: Node[] = Array.from({ length: NODE_COUNT }, (_, i) => ({
    id: `n${i}`,
    data: { label: `Requirement ${i + 1}` },
    position: { x: (i % 25) * 190, y: Math.floor(i / 25) * 95 },
    style: { width: 145, fontSize: 10 },
  }));
  const edges: Edge[] = Array.from({ length: EDGE_COUNT }, (_, i) => ({
    id: `e${i}`,
    source: `n${i % NODE_COUNT}`,
    target: `n${(i * 7 + 13) % NODE_COUNT}`,
  }));
  return { nodes, edges };
}

function App() {
  const graph = useMemo(makeGraph, []);
  const cyContainer = useRef<HTMLDivElement>(null);
  const cyInstance = useRef<Core | null>(null);
  const [active, setActive] = useState<"reactflow" | "cytoscape">("reactflow");
  const [results, setResults] = useState<Result[]>([]);
  const [status, setStatus] = useState("Choose a library, then record a timing.");

  useEffect(() => {
    if (active !== "cytoscape" || !cyContainer.current) return;
    const started = performance.now();
    const cy = cytoscape({
      container: cyContainer.current,
      elements: [
        ...graph.nodes.map((n) => ({ data: { id: n.id, label: String(n.data.label) } })),
        ...graph.edges.map((e) => ({
          data: { id: e.id, source: e.source, target: e.target },
        })),
      ],
      style: [
        { selector: "node", style: {
          label: "data(label)", width: 22, height: 22, "font-size": 7,
          "text-wrap": "ellipsis", "text-max-width": "80px",
        } },
        { selector: "edge", style: {
          width: 1, "line-color": "#94a3b8", opacity: 0.65, "curve-style": "bezier",
        } },
      ],
      layout: { name: "grid", rows: 20, animate: false },
      hideEdgesOnViewport: true,
      textureOnViewport: true,
    });
    cyInstance.current = cy;
    cy.one("render", () => setStatus(
      `Cytoscape setup took ${(performance.now() - started).toFixed(1)} ms. Repeat runs before drawing conclusions.`,
    ));
    return () => { cy.destroy(); cyInstance.current = null; };
  }, [active, graph]);

  const recordTiming = () => {
    const started = performance.now();
    requestAnimationFrame(() => requestAnimationFrame(() => {
      const result: Result = {
        library: active === "reactflow" ? "React Flow" : "Cytoscape.js",
        renderMs: Number((performance.now() - started).toFixed(2)),
        nodeCount: NODE_COUNT,
        edgeCount: EDGE_COUNT,
        timestamp: new Date().toISOString(),
      };
      setResults((previous) => [...previous, result]);
      setStatus(`Recorded ${result.library}: ${result.renderMs} ms to two animation frames. This is an indicative browser measure, not a rigorous benchmark.`);
    }));
  };

  const exportCsv = () => {
    const rows = [
      "timestamp,library,node_count,edge_count,render_ms",
      ...results.map((r) => `${r.timestamp},${r.library},${r.nodeCount},${r.edgeCount},${r.renderMs}`),
    ];
    const blob = new Blob([rows.join("\n")], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "rcd-graph-benchmark.csv";
    link.click();
    URL.revokeObjectURL(url);
  };

  return <main className="benchmark-shell">
    <header>
      <h1>RCD Graph Library Benchmark</h1>
      <p>Dataset: {NODE_COUNT} nodes and {EDGE_COUNT} edges. Test both libraries in the same browser and machine.</p>
    </header>
    <div className="toolbar">
      <button onClick={() => setActive("reactflow")} aria-pressed={active === "reactflow"}>React Flow</button>
      <button onClick={() => setActive("cytoscape")} aria-pressed={active === "cytoscape"}>Cytoscape.js</button>
      <button onClick={recordTiming}>Record timing</button>
      <button onClick={exportCsv} disabled={!results.length}>Export CSV</button>
    </div>
    <p className="status" role="status">{status}</p>
    <section className="graph-area">
      {active === "reactflow" ? <ReactFlow nodes={graph.nodes} edges={graph.edges} fitView minZoom={0.05} maxZoom={2}>
        <Background /><Controls />
      </ReactFlow> : <div ref={cyContainer} className="cy-container" />}
    </section>
    <section>
      <h2>Recorded measurements</h2>
      <p>Repeat several runs. Compare medians, pan/zoom responsiveness, selection and layout readability. This page does not automatically choose a winner.</p>
      <table><thead><tr><th>Library</th><th>Nodes</th><th>Edges</th><th>Timing (ms)</th><th>Timestamp</th></tr></thead>
        <tbody>{results.map((r, i) => <tr key={`${r.timestamp}-${i}`}><td>{r.library}</td><td>{r.nodeCount}</td><td>{r.edgeCount}</td><td>{r.renderMs}</td><td>{r.timestamp}</td></tr>)}</tbody>
      </table>
    </section>
  </main>;
}

createRoot(document.getElementById("root")!).render(<React.StrictMode><App /></React.StrictMode>);
