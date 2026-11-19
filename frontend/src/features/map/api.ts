// The live requirements map (Abhijeet — US-14 UI; API by Dhavni, contract in
// docs/contracts/realtime.md §6). Keys: ["graph", projectId] holds the snapshot the deltas are
// applied to; ["requirement", id] the drawer's detail.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "../../api/client";
import type { RequirementRead, RequirementState, UUID } from "../../api/types";

export type EdgeKind = "conflict" | "duplicate" | "depends_on" | "ambiguous" | "incomplete" | "link";
export type EdgeStatus = "flagged" | "confirmed" | "dismissed" | "merged" | "reclassified";

export interface GraphNode {
  id: UUID;
  label: string | null;
  state: RequirementState;
  group: string | null;
  owner_id: UUID | null;
  req_type: string | null;
  origin: "document" | "post" | "change_request";
  is_protected: boolean;
  open_issues: number;
  x: number | null;
  y: number | null;
}

export interface GraphEdge {
  id: UUID;
  source: UUID;
  target: UUID; // == source: a single-requirement finding, drawn as a badge on the node
  kind: EdgeKind;
  status: EdgeStatus;
  severity: "low" | "medium" | "high" | null;
  confidence: number | null;
}

export interface GraphSnapshot {
  project_id: UUID;
  revision: number;
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface GraphDelta {
  project_id: UUID;
  from_revision: number;
  to_revision: number;
  actor_id: UUID | null;
  actor_name: string | null;
  added: { nodes: GraphNode[]; edges: GraphEdge[] };
  changed: { nodes: GraphNode[]; edges: GraphEdge[] };
  removed: { node_ids: UUID[]; edge_ids: UUID[] };
  sentences: string[];
}

export const graphKey = (projectId: string) => ["graph", projectId];

export function useGraph(projectId: string) {
  return useQuery({
    queryKey: graphKey(projectId),
    queryFn: () => apiFetch<GraphSnapshot>(`/projects/${projectId}/graph`),
    staleTime: Infinity, // kept current by graph.delta; a gap or a reconnect refetches
  });
}

/** The snapshot after ``delta``, or null when the delta does not follow it (a missed event: the
 *  caller re-fetches). Pure, so the order and the gaps are easy to test. */
export function applyDelta(snapshot: GraphSnapshot, delta: GraphDelta): GraphSnapshot | null {
  if (delta.from_revision !== snapshot.revision) return null;
  const nodes = new Map(snapshot.nodes.map((node) => [node.id, node]));
  const edges = new Map(snapshot.edges.map((edge) => [edge.id, edge]));
  for (const node of [...delta.added.nodes, ...delta.changed.nodes]) {
    const before = nodes.get(node.id);
    // A layout-free change keeps the position this client already has.
    nodes.set(node.id, node.x === null && before ? { ...node, x: before.x, y: before.y } : node);
  }
  for (const edge of [...delta.added.edges, ...delta.changed.edges]) edges.set(edge.id, edge);
  for (const id of delta.removed.node_ids) nodes.delete(id);
  for (const id of delta.removed.edge_ids) edges.delete(id);
  return {
    ...snapshot,
    revision: delta.to_revision,
    nodes: [...nodes.values()],
    edges: [...edges.values()],
  };
}

export function useSavePositions(projectId: string) {
  return useMutation({
    mutationFn: (positions: { requirement_id: UUID; x: number; y: number }[]) =>
      apiFetch<void>(`/projects/${projectId}/graph/positions`, {
        method: "PUT",
        json: { positions },
      }),
  });
}

// ── The requirement drawer (US-37 moves, US-36 owner) ───────────────────────────────────────
export interface Transition {
  from_state: RequirementState;
  to_state: RequirementState;
  version: number;
  actor_id: UUID;
  reason: string | null;
  accepted_risk: boolean;
  created_at: string;
}

export interface RequirementDetail extends RequirementRead {
  req_type: string | null;
  priority: string | null;
  rationale: string | null;
  acceptance_criteria: { given: string; when: string; then: string }[];
  tags: string[];
  origin_message_id: UUID | null;
  signed_off_version: number | null;
  allowed_transitions: RequirementState[];
  readiness: { analysis_current: boolean; open_high_findings: UUID[]; needs_signoff: boolean };
  transitions: Transition[];
}

export function useRequirement(requirementId: string | null) {
  return useQuery({
    queryKey: ["requirement", requirementId],
    enabled: Boolean(requirementId),
    queryFn: () => apiFetch<RequirementDetail>(`/requirements/${requirementId}`),
  });
}

export interface MoveInput {
  state: RequirementState;
  version: number;
  reason?: string;
  accepted_risk?: boolean;
}

export function useMoveRequirement(requirementId: string, projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: MoveInput) =>
      apiFetch<RequirementDetail>(`/requirements/${requirementId}`, {
        method: "PATCH",
        json: input,
      }),
    onSuccess: (detail) => {
      queryClient.setQueryData(["requirement", requirementId], detail);
      void queryClient.invalidateQueries({ queryKey: ["requirements", projectId] });
    },
  });
}
