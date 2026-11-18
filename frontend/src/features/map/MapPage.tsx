import { useMemo, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { useProjectRealtime } from "../../app/socket";
import { usePermissions } from "../../app/usePermissions";
import { useMembers } from "../channels/api";
import { useGraph, useSavePositions, type EdgeKind, type GraphNode } from "./api";
import { ChangesFeed } from "./ChangesFeed";
import { GraphCanvas } from "./GraphCanvas";
import { Legend } from "./Legend";
import { NodeDrawer } from "./NodeDrawer";
import { TableView } from "./TableView";
import { useGraphDeltas } from "./useGraphDeltas";

const KIND_FILTERS: { kinds: EdgeKind[]; label: string }[] = [
  { kinds: ["conflict"], label: "Conflicts" },
  { kinds: ["duplicate"], label: "Duplicates" },
  { kinds: ["depends_on"], label: "Dependencies" },
  { kinds: ["ambiguous", "incomplete"], label: "Ambiguous / incomplete" },
  { kinds: ["link"], label: "Human links" },
];
const STATE_FILTERS: { states: GraphNode["state"][]; label: string }[] = [
  { states: ["Approved", "Implemented"], label: "Baseline" },
  { states: ["Proposed", "Under_Review"], label: "Proposed" },
  { states: ["Rejected", "Deprecated"], label: "Rejected / deprecated" },
];

/** The live requirements map (US-14, interface design §9): requirements and their relationships,
 *  kept current by graph.delta, with filters, search, focus mode, the written feed and a table
 *  view of the same data. Opening a node shows its drawer (lifecycle, owner, findings, review). */
export function MapPage() {
  const { workspaceId, projectId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  useProjectRealtime(projectId);
  const graph = useGraph(projectId);
  const { feed, pulsing } = useGraphDeltas(projectId);
  const { can } = usePermissions({ projectId });
  const save = useSavePositions(projectId);
  const members = useMembers(workspaceId);
  const names = useMemo(
    () => new Map((members.data ?? []).map((m) => [m.user.id, m.user.full_name])),
    [members.data],
  );

  const [hiddenKinds, setHiddenKinds] = useState<Set<EdgeKind>>(new Set());
  const [hiddenStates, setHiddenStates] = useState<Set<string>>(new Set(["Rejected", "Deprecated"]));
  const [group, setGroup] = useState("");
  const [owner, setOwner] = useState("");
  const [search, setSearch] = useState("");
  const [depth, setDepth] = useState<1 | 2>(1);
  const [table, setTable] = useState(false);
  const [highlight, setHighlight] = useState<ReadonlySet<string>>(new Set());
  const focusId = params.get("focus");

  const select = (id: string | null) =>
    setParams((current) => {
      const next = new URLSearchParams(current);
      if (id) next.set("focus", id);
      else next.delete("focus");
      return next;
    });

  const data = graph.data;
  const { nodes, edges } = useMemo(() => {
    if (!data) return { nodes: [], edges: [] };
    const term = search.trim().toLowerCase();
    const shown = data.nodes.filter(
      (node) =>
        !hiddenStates.has(node.state) &&
        (!group || node.group === group) &&
        (!owner || node.owner_id === owner) &&
        (!term || (node.label ?? "").toLowerCase().includes(term)),
    );
    const ids = new Set(shown.map((node) => node.id));
    return {
      nodes: shown,
      edges: data.edges.filter(
        (edge) => !hiddenKinds.has(edge.kind) && ids.has(edge.source) && ids.has(edge.target),
      ),
    };
  }, [data, hiddenKinds, hiddenStates, group, owner, search]);
  const groups = useMemo(
    () => [...new Set((data?.nodes ?? []).map((n) => n.group).filter((g): g is string => Boolean(g)))].sort(),
    [data],
  );
  const pulse = useMemo(() => new Set([...pulsing, ...highlight]), [pulsing, highlight]);

  const toggle = <T,>(set: Set<T>, values: T[], update: (next: Set<T>) => void) => {
    const next = new Set(set);
    const on = values.every((value) => next.has(value));
    values.forEach((value) => (on ? next.delete(value) : next.add(value)));
    update(next);
  };

  return (
    <div className="page map-page">
      <header className="page-header">
        <h1>Map</h1>
        <span className="muted small">
          {data ? `${data.nodes.length} requirements · revision ${data.revision}` : ""}
        </span>
      </header>

      <div className="map-toolbar" role="toolbar" aria-label="Map filters">
        <fieldset className="pill-group">
          <legend className="sr-only">Show relationships</legend>
          {KIND_FILTERS.map((filter) => (
            <button
              key={filter.label}
              type="button"
              className="pill"
              aria-pressed={!filter.kinds.every((k) => hiddenKinds.has(k))}
              onClick={() => toggle(hiddenKinds, filter.kinds, setHiddenKinds)}
            >
              {filter.label}
            </button>
          ))}
        </fieldset>
        <fieldset className="pill-group">
          <legend className="sr-only">Show requirements</legend>
          {STATE_FILTERS.map((filter) => (
            <button
              key={filter.label}
              type="button"
              className="pill"
              aria-pressed={!filter.states.every((s) => hiddenStates.has(s))}
              onClick={() => toggle(hiddenStates, filter.states as string[], setHiddenStates)}
            >
              {filter.label}
            </button>
          ))}
        </fieldset>
        <label>
          <span className="sr-only">Group</span>
          <select className="select" value={group} onChange={(e) => setGroup(e.target.value)}>
            <option value="">Every group</option>
            {groups.map((g) => (
              <option key={g} value={g}>
                {g}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className="sr-only">Owner</span>
          <select className="select" value={owner} onChange={(e) => setOwner(e.target.value)}>
            <option value="">Every owner</option>
            {[...names].map(([id, name]) => (
              <option key={id} value={id}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className="sr-only">Search by ID</span>
          <input
            className="input"
            type="search"
            placeholder="Search REQ-…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
        <label className="small">
          Focus{" "}
          <select className="select" value={depth} onChange={(e) => setDepth(Number(e.target.value) as 1 | 2)}>
            <option value={1}>1 hop</option>
            <option value={2}>2 hops</option>
          </select>
        </label>
        <button type="button" className="pill" aria-pressed={table} onClick={() => setTable(!table)}>
          Table view
        </button>
        <Legend />
      </div>

      {graph.isLoading && <p className="muted">Loading the map…</p>}
      {graph.isError && <p role="alert">The map could not be loaded.</p>}
      {data &&
        (table ? (
          <TableView nodes={nodes} edges={edges} names={names} onSelect={select} />
        ) : (
          <GraphCanvas
            nodes={nodes}
            edges={edges}
            pulsing={pulse}
            focusId={focusId}
            focusDepth={depth}
            onSelect={select}
            onMoved={can("req.comment") ? (positions) => save.mutate(positions) : null}
          />
        ))}
      {data && data.nodes.length === 0 && (
        <p className="empty-state">
          No requirements yet. Upload an SRS or propose a requirement: it appears here as soon as it
          is analysed.
        </p>
      )}

      <ChangesFeed items={feed} onSelect={(ids) => setHighlight(new Set(ids))} />
      <NodeDrawer projectId={projectId} requirementId={focusId} names={names} onClose={() => select(null)} />
    </div>
  );
}
