// The map's history and preview (Pranshu — US-50 UI; API by Dhavni):
// GET /projects/{p}/graph/revisions, GET …/graph/revisions/{id}, GET /change-requests/{id}/graph-preview.
// A frozen map never changes, so it is cached for good.

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../../api/client";
import type { UUID } from "../../api/types";
import type { EdgeKind, GraphEdge, GraphNode } from "./api";

export interface RevisionPoint {
  id: UUID | null; // null for "Now"
  label: string;
  kind: "baseline_revision" | "baseline" | "now";
  baseline_revision: number;
  graph_revision: number;
  at: string | null;
  baseline_id: UUID | null;
  nodes: number;
  edges: number;
}

export interface HistoricMap {
  project_id: UUID;
  snapshot_id: UUID;
  label: string;
  read_only: true;
  baseline_revision: number;
  graph_revision: number;
  captured_at: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface GhostEdge {
  source: UUID;
  target: UUID;
  kind: EdgeKind;
  labels: string[];
  reason: string;
}

export interface GraphPreview {
  change_request_id: UUID;
  number: number;
  kind: string;
  requirement_id: UUID;
  report_id: UUID | null;
  checks_pending: boolean;
  stale: string[];
  fading_edge_ids: UUID[];
  glowing_edges: GhostEdge[];
  affected_node_ids: UUID[];
  removed_node_ids: UUID[];
  sentences: string[];
}

/** What the canvas draws on top of the map: fading and ghost edges, outlined and fading nodes. */
export interface PreviewOverlay {
  fadingEdgeIds: ReadonlySet<string>;
  ghostEdges: GhostEdge[];
  affectedNodeIds: ReadonlySet<string>;
  removedNodeIds: ReadonlySet<string>;
  ghostNode?: { id: string; label: string } | null; // a pre-flight draft
}

export function useRevisions(projectId: string) {
  return useQuery({
    queryKey: ["graph-revisions", projectId],
    queryFn: () => apiFetch<RevisionPoint[]>(`/projects/${projectId}/graph/revisions`),
  });
}

export function useHistoricMap(projectId: string, snapshotId: string | null) {
  return useQuery({
    queryKey: ["graph-revision", snapshotId],
    enabled: Boolean(snapshotId),
    staleTime: Infinity,
    queryFn: () => apiFetch<HistoricMap>(`/projects/${projectId}/graph/revisions/${snapshotId}`),
  });
}

export function useGraphPreview(changeRequestId: string | null) {
  return useQuery({
    queryKey: ["graph-preview", changeRequestId],
    enabled: Boolean(changeRequestId),
    queryFn: () => apiFetch<GraphPreview>(`/change-requests/${changeRequestId}/graph-preview`),
  });
}

export function overlayOf(preview: GraphPreview): PreviewOverlay {
  return {
    fadingEdgeIds: new Set([...preview.fading_edge_ids]),
    ghostEdges: preview.glowing_edges,
    affectedNodeIds: new Set([...preview.affected_node_ids]),
    removedNodeIds: new Set([...preview.removed_node_ids]),
  };
}

// A pre-flight draft handed over by the composer ("Preview on map"). Per-tab convenience only:
// sessionStorage may be unavailable, and then the button simply has nothing to show.
export const DRAFT_PREVIEW_KEY = "rcd.preview.draft";

export interface DraftPreview {
  projectId: string;
  findings: { category: string; requirement_id: string | null; label: string | null }[];
}

export function saveDraftPreview(preview: DraftPreview): boolean {
  try {
    sessionStorage.setItem(DRAFT_PREVIEW_KEY, JSON.stringify(preview));
    return true;
  } catch {
    return false;
  }
}

export function loadDraftPreview(projectId: string): DraftPreview | null {
  try {
    const raw = sessionStorage.getItem(DRAFT_PREVIEW_KEY);
    const parsed = raw ? (JSON.parse(raw) as DraftPreview) : null;
    return parsed && parsed.projectId === projectId ? parsed : null;
  } catch {
    return null;
  }
}

const CATEGORY_KIND: Record<string, EdgeKind> = {
  Conflicting: "conflict",
  Duplicate: "duplicate",
  Dependent: "depends_on",
};

export const DRAFT_NODE_ID = "draft-preview";

export function draftOverlay(draft: DraftPreview): PreviewOverlay {
  return {
    fadingEdgeIds: new Set(),
    ghostEdges: draft.findings
      .filter((f) => f.requirement_id && CATEGORY_KIND[f.category])
      .map((f) => ({
        source: DRAFT_NODE_ID,
        target: f.requirement_id as string,
        kind: CATEGORY_KIND[f.category],
        labels: ["Draft", f.label ?? ""],
        reason: `Likely ${f.category.toLowerCase()} (pre-flight)`,
      })),
    affectedNodeIds: new Set(draft.findings.map((f) => f.requirement_id).filter((id): id is string => Boolean(id))),
    removedNodeIds: new Set(),
    ghostNode: { id: DRAFT_NODE_ID, label: "Draft" },
  };
}
