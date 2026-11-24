import { useMemo, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { useProjectRealtime } from "../../app/socket";
import { usePermissions } from "../../app/usePermissions";
import { ChangesPanel } from "../analytics/ChangesPanel";
import { useMembers } from "../channels/api";
import { useGraph, useSavePositions, type EdgeKind, type GraphNode } from "./api";
import { ChangesFeed } from "./ChangesFeed";
import { GraphCanvas } from "./GraphCanvas";
import {
  draftOverlay,
  loadDraftPreview,
  overlayOf,
  useGraphPreview,
  useHistoricMap,
  useRevisions,
  type DraftPreview,
} from "./history";
import { Legend } from "./Legend";
import { NodeDrawer } from "./NodeDrawer";
import { PreviewLayer, type Layers } from "./PreviewLayer";
import { TableView } from "./TableView";
import { TimeSlider } from "./TimeSlider";
import { useGraphDeltas } from "./useGraphDeltas";

const KIND_FILTERS: { kinds: EdgeKind[]; label: string }[] = [
  { kinds: ["conflict"], label: "Conflicts" },
  { kinds: ["duplicate"], label: "Duplicates" },
  { kinds: ["depends_on"], label: "Dependencies" },
  { kinds: ["ambiguous", "incomplete"], label: "Ambiguous / incomplete" },
  { kinds: ["link"], label: "Human links" },
];
const BASELINE_STATES = new Set(["Approved", "Implemented"]);
const PROPOSED_STATES = new Set(["Proposed", "Under_Review"]);
const CLUSTER_ABOVE = 300; // nodes: above this the map opens clustered by group (US-50)
type GroupBy = "" | "group" | "type" | "owner";

/** The live requirements map (US-14, interface design §9): requirements and their relationships,
 *  kept current by graph.delta, with filters, search, focus mode, the written feed and a table view.
 *  Sprint 6 (Pranshu): layers Baseline / Proposed / Preview (US-50), the time slider (a point in the
 *  past shows that map read-only), grouping and clusters, and the Changes panel (US-55). */
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
  const [showRetired, setShowRetired] = useState(false);
  const [layers, setLayers] = useState<Layers>({
    baseline: true,
    proposed: true, // on by default (SX-17)
    preview: params.get("preview") === "draft",
  });
  const [changeRequestId, setChangeRequestId] = useState<string | null>(params.get("preview_cr"));
  const [draft, setDraft] = useState<DraftPreview | null>(() =>
    params.get("preview") === "draft" ? loadDraftPreview(projectId) : null,
  );
  const [snapshotId, setSnapshotId] = useState<string | null>(null);
  const [group, setGroup] = useState("");
  const [owner, setOwner] = useState("");
  const [groupBy, setGroupBy] = useState<GroupBy | null>(null); // null = the default for the size
  const [search, setSearch] = useState("");
  const [depth, setDepth] = useState<1 | 2>(1);
  const [table, setTable] = useState(false);
  const [highlight, setHighlight] = useState<ReadonlySet<string>>(new Set());
  const [hovered, setHovered] = useState<string | null>(null);
  const focusId = params.get("focus");

  const revisions = useRevisions(projectId);
  const historic = useHistoricMap(projectId, snapshotId);
  const readOnly = snapshotId !== null;
  const preview = useGraphPreview(layers.preview && !readOnly ? changeRequestId : null);

  const select = (id: string | null) =>
    setParams((current) => {
      const next = new URLSearchParams(current);
      if (id) next.set("focus", id);
      else next.delete("focus");
      return next;
    });

  const data = readOnly ? historic.data : graph.data;
  const { nodes, edges } = useMemo(() => {
    if (!data) return { nodes: [], edges: [] };
    const term = search.trim().toLowerCase();
    const shown = data.nodes.filter(
      (node) =>
        (layers.baseline || !BASELINE_STATES.has(node.state)) &&
        (layers.proposed || !PROPOSED_STATES.has(node.state)) &&
        (showRetired || BASELINE_STATES.has(node.state) || PROPOSED_STATES.has(node.state)) &&
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
  }, [data, hiddenKinds, showRetired, layers, group, owner, search]);
  const groups = useMemo(
    () => [...new Set((data?.nodes ?? []).map((n) => n.group).filter((g): g is string => Boolean(g)))].sort(),
    [data],
  );
  const pulse = useMemo(() => new Set([...pulsing, ...highlight]), [pulsing, highlight]);
  const overlay = useMemo(() => {
    if (!layers.preview || readOnly) return null;
    if (changeRequestId) return preview.data ? overlayOf(preview.data) : null;
    return draft ? draftOverlay(draft) : null;
  }, [layers.preview, readOnly, changeRequestId, preview.data, draft]);
  const effectiveGroupBy: GroupBy = groupBy ?? (nodes.length > CLUSTER_ABOVE ? "group" : "");
  const groupOf = useMemo(() => {
    if (!effectiveGroupBy) return null;
    return (node: GraphNode): string | null => {
      if (effectiveGroupBy === "group") return node.group;
      if (effectiveGroupBy === "type") return node.req_type ? node.req_type.replace("_", "-") : null;
      return node.owner_id ? (names.get(node.owner_id) ?? "Another member") : "Unassigned";
    };
  }, [effectiveGroupBy, names]);

  const toggleKinds = (values: EdgeKind[]) => {
    const next = new Set(hiddenKinds);
    const on = values.every((value) => next.has(value));
    values.forEach((value) => (on ? next.delete(value) : next.add(value)));
    setHiddenKinds(next);
  };
  const point = (revisions.data ?? []).find((p) => p.id === snapshotId);

  return (
    <div className="page map-page">
      <header className="page-header">
        <h1>Map</h1>
        <span className="muted small">
          {data
            ? readOnly
              ? `${data.nodes.length} requirements · ${historic.data?.label ?? ""} (read-only)`
              : `${data.nodes.length} requirements · revision ${graph.data?.revision ?? ""}`
            : ""}
        </span>
      </header>

      <div className="map-toolbar" role="toolbar" aria-label="Map filters">
        <PreviewLayer
          projectId={projectId}
          layers={layers}
          onLayers={setLayers}
          changeRequestId={changeRequestId}
          onChangeRequest={setChangeRequestId}
          draft={draft}
          onClearDraft={() => setDraft(null)}
          readOnly={readOnly}
        />
        <fieldset className="pill-group">
          <legend className="sr-only">Show relationships</legend>
          {KIND_FILTERS.map((filter) => (
            <button
              key={filter.label}
              type="button"
              className="pill"
              aria-pressed={!filter.kinds.every((k) => hiddenKinds.has(k))}
              onClick={() => toggleKinds(filter.kinds)}
            >
              {filter.label}
            </button>
          ))}
          <button type="button" className="pill" aria-pressed={showRetired} onClick={() => setShowRetired(!showRetired)}>
            Rejected / deprecated
          </button>
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
        <label className="small">
          Group by{" "}
          <select className="select" value={effectiveGroupBy} onChange={(e) => setGroupBy(e.target.value as GroupBy)}>
            <option value="">nothing</option>
            <option value="group">stakeholder group</option>
            <option value="type">type</option>
            <option value="owner">owner</option>
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

      <TimeSlider
        points={revisions.data ?? []}
        value={snapshotId}
        onChange={(id) => setSnapshotId(id)}
      />

      {(readOnly ? historic.isLoading : graph.isLoading) && <p className="muted">Loading the map…</p>}
      {graph.isError && <p role="alert">The map could not be loaded.</p>}
      <div className="map-body">
        <div className="map-main">
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
                onMoved={!readOnly && can("req.comment") ? (positions) => save.mutate(positions) : null}
                preview={overlay}
                onHover={setHovered}
                groupOf={groupOf}
              />
            ))}
          {data && data.nodes.length === 0 && (
            <p className="empty-state">
              No requirements yet. Upload an SRS or propose a requirement: it appears here as soon as it
              is analysed.
            </p>
          )}
          {!readOnly && <ChangesFeed items={feed} onSelect={(ids) => setHighlight(new Set(ids))} />}
        </div>
        <ChangesPanel
          projectId={projectId}
          names={names}
          untilRevision={point ? point.graph_revision : null}
          hoveredNode={hovered}
          onSelect={(ids) => setHighlight(new Set(ids))}
        />
      </div>
      <NodeDrawer projectId={projectId} requirementId={focusId} names={names} onClose={() => select(null)} />
    </div>
  );
}
