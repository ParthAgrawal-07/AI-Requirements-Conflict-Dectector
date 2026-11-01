import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import ReactFlow, {
  Background,
  Controls,
  type Edge,
  type Node,
  type ReactFlowInstance,
} from "reactflow";
import cytoscape, { type Core } from "cytoscape";
import "reactflow/dist/style.css";
import "./styles.css";

const NODE_COUNT = 500;
const EDGE_COUNT = 2000;
const FRAME_COUNT = 90;
const SLOW_FRAME_LIMIT_MS = 100;

type Result = {
  library: string;
  setupMs: number;
  interactionDurationMs: number;
  averageFrameMs: number;
  maximumFrameMs: number;
  slowFrames: number;
  nodeCount: number;
  edgeCount: number;
  timestamp: string;
};

function makeGraph() {
  const nodes: Node[] = Array.from({ length: NODE_COUNT }, (_, i) => ({
    id: `n${i}`,
    data: { label: `Requirement ${i + 1}` },
    position: {
      x: (i % 25) * 190,
      y: Math.floor(i / 25) * 95,
    },
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
  const rfInstance = useRef<ReactFlowInstance | null>(null);

  const mountStarted = useRef(performance.now());
  const setupTime = useRef(0);

  const [active, setActive] = useState<"reactflow" | "cytoscape">(
    "reactflow",
  );
  const [results, setResults] = useState<Result[]>([]);
  const [isRecording, setIsRecording] = useState(false);
  const [status, setStatus] = useState(
    "Choose a library, then record an interaction benchmark.",
  );

  const switchLibrary = (library: "reactflow" | "cytoscape") => {
    if (library === active || isRecording) return;

    mountStarted.current = performance.now();
    setupTime.current = 0;
    setActive(library);
  };

  const handleReactFlowInit = (instance: ReactFlowInstance) => {
    rfInstance.current = instance;

    const elapsed = performance.now() - mountStarted.current;
    setupTime.current = elapsed;

    setStatus(
      `React Flow setup completed in ${elapsed.toFixed(1)} ms.`,
    );
  };

  useEffect(() => {
    if (active !== "cytoscape" || !cyContainer.current) return;

    const started = performance.now();

    const cy = cytoscape({
      container: cyContainer.current,
      elements: [
        ...graph.nodes.map((node) => ({
          data: {
            id: node.id,
            label: String(node.data.label),
          },
        })),
        ...graph.edges.map((edge) => ({
          data: {
            id: edge.id,
            source: edge.source,
            target: edge.target,
          },
        })),
      ],
      style: [
        {
          selector: "node",
          style: {
            label: "data(label)",
            width: 22,
            height: 22,
            "font-size": 7,
            "text-wrap": "ellipsis",
            "text-max-width": "80px",
          },
        },
        {
          selector: "edge",
          style: {
            width: 1,
            "line-color": "#94a3b8",
            opacity: 0.65,
            "curve-style": "bezier",
          },
        },
      ],
      layout: {
        name: "grid",
        rows: 20,
        animate: false,
      },
      hideEdgesOnViewport: true,
      textureOnViewport: true,
    });

    cyInstance.current = cy;

    cy.one("render", () => {
      const elapsed = performance.now() - started;
      setupTime.current = elapsed;

      setStatus(
        `Cytoscape setup completed in ${elapsed.toFixed(1)} ms.`,
      );
    });

    return () => {
      cy.destroy();
      cyInstance.current = null;
    };
  }, [active, graph]);

  const recordTiming = () => {
    if (isRecording) return;

    const rf = rfInstance.current;
    const cy = cyInstance.current;

    if (active === "reactflow" && !rf) {
      setStatus("React Flow is not ready yet. Please try again.");
      return;
    }

    if (active === "cytoscape" && !cy) {
      setStatus("Cytoscape is not ready yet. Please try again.");
      return;
    }

    setIsRecording(true);
    setStatus("Running scripted pan and zoom benchmark...");

    const frameIntervals: number[] = [];
    const interactionStarted = performance.now();
    let previousFrame = interactionStarted;
    let frame = 0;

    const animate = (now: number) => {
      if (frame > 0) {
        frameIntervals.push(now - previousFrame);
      }

      previousFrame = now;

      const progress = frame / FRAME_COUNT;
      const angle = progress * Math.PI * 4;

      const x = 40 + Math.sin(angle) * 80;
      const y = 40 + Math.cos(angle) * 60;
      const zoom = 1 + Math.sin(angle) * 0.15;

      if (active === "reactflow" && rf) {
        rf.setViewport(
          { x, y, zoom },
          { duration: 0 },
        );
      } else if (active === "cytoscape" && cy) {
        cy.zoom(zoom);
        cy.pan({ x, y });
      }

      frame += 1;

      if (frame <= FRAME_COUNT) {
        requestAnimationFrame(animate);
        return;
      }

      const interactionDuration =
        performance.now() - interactionStarted;

      const averageFrame =
        frameIntervals.reduce((sum, value) => sum + value, 0) /
        Math.max(frameIntervals.length, 1);

      const maximumFrame = Math.max(...frameIntervals);

      const slowFrames = frameIntervals.filter(
        (value) => value > SLOW_FRAME_LIMIT_MS,
      ).length;

      const result: Result = {
        library:
          active === "reactflow" ? "React Flow" : "Cytoscape.js",
        setupMs: Number(setupTime.current.toFixed(2)),
        interactionDurationMs: Number(
          interactionDuration.toFixed(2),
        ),
        averageFrameMs: Number(averageFrame.toFixed(2)),
        maximumFrameMs: Number(maximumFrame.toFixed(2)),
        slowFrames,
        nodeCount: NODE_COUNT,
        edgeCount: EDGE_COUNT,
        timestamp: new Date().toISOString(),
      };

      setResults((previous) => [...previous, result]);
      setIsRecording(false);

      setStatus(
        `${result.library}: ${result.averageFrameMs} ms average frame time, ` +
          `${result.slowFrames} slow frames, setup ${result.setupMs} ms.`,
      );
    };

    requestAnimationFrame(animate);
  };

  const exportCsv = () => {
    const headers = [
      "timestamp",
      "library",
      "node_count",
      "edge_count",
      "setup_ms",
      "interaction_duration_ms",
      "average_frame_ms",
      "maximum_frame_ms",
      "slow_frames_over_100ms",
    ];

    const rows = results.map((result) =>
      [
        result.timestamp,
        result.library,
        result.nodeCount,
        result.edgeCount,
        result.setupMs,
        result.interactionDurationMs,
        result.averageFrameMs,
        result.maximumFrameMs,
        result.slowFrames,
      ].join(","),
    );

    const csv = [headers.join(","), ...rows].join("\n");
    const blob = new Blob([csv], {
      type: "text/csv;charset=utf-8",
    });

    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");

    link.href = url;
    link.download = "rcd-graph-benchmark.csv";
    link.click();

    URL.revokeObjectURL(url);
  };

  return (
    <main className="benchmark-shell">
      <header>
        <h1>RCD Graph Library Benchmark</h1>
        <p>
          Dataset: {NODE_COUNT} nodes and {EDGE_COUNT} edges.
          Test both libraries in the same browser and machine.
        </p>
      </header>

      <div className="toolbar">
        <button
          onClick={() => switchLibrary("reactflow")}
          aria-pressed={active === "reactflow"}
          disabled={isRecording}
        >
          React Flow
        </button>

        <button
          onClick={() => switchLibrary("cytoscape")}
          aria-pressed={active === "cytoscape"}
          disabled={isRecording}
        >
          Cytoscape.js
        </button>

        <button onClick={recordTiming} disabled={isRecording}>
          {isRecording ? "Recording..." : "Record timing"}
        </button>

        <button onClick={exportCsv} disabled={!results.length}>
          Export CSV
        </button>
      </div>

      <p className="status" role="status">
        {status}
      </p>

      <section className="graph-area">
        {active === "reactflow" ? (
          <ReactFlow
            nodes={graph.nodes}
            edges={graph.edges}
            fitView
            minZoom={0.05}
            maxZoom={2}
            onInit={handleReactFlowInit}
          >
            <Background />
            <Controls />
          </ReactFlow>
        ) : (
          <div ref={cyContainer} className="cy-container" />
        )}
      </section>

      <section>
        <h2>Recorded measurements</h2>

        <p>
          Each measurement runs a scripted pan and zoom interaction
          over 90 animation frames. Frame intervals are browser-level
          responsiveness indicators, not a complete GPU profiling result.
          Repeat several runs in the foreground before comparing results.
        </p>

        <table>
          <thead>
            <tr>
              <th>Library</th>
              <th>Nodes</th>
              <th>Edges</th>
              <th>Setup (ms)</th>
              <th>Avg frame (ms)</th>
              <th>Max frame (ms)</th>
              <th>Slow frames</th>
              <th>Timestamp</th>
            </tr>
          </thead>

          <tbody>
            {results.map((result, index) => (
              <tr key={`${result.timestamp}-${index}`}>
                <td>{result.library}</td>
                <td>{result.nodeCount}</td>
                <td>{result.edgeCount}</td>
                <td>{result.setupMs}</td>
                <td>{result.averageFrameMs}</td>
                <td>{result.maximumFrameMs}</td>
                <td>{result.slowFrames}</td>
                <td>{result.timestamp}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);