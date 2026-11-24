// The written change log beside the map (Pranshu — US-55 UI; API by Dhavni and Keval:
// GET /projects/{p}/changes, GET|POST /projects/{p}/changes/summary, PUT …/changes/seen).
// Keys: ["changes", projectId, filters] — invalidated by every graph.delta (useGraphDeltas).

import { useMutation, useQuery } from "@tanstack/react-query";
import { apiFetch } from "../../api/client";
import type { UUID } from "../../api/types";

export type ChangeKind =
  | "added"
  | "changed"
  | "state"
  | "owner"
  | "analysed"
  | "conflict_found"
  | "conflict_resolved"
  | "reviewed"
  | "issue"
  | "change_request"
  | "merged"
  | "concern"
  | "link";

/** The filter groups the panel offers (AC: added, changed, merged, conflict found or resolved,
 *  link), each mapped to the stored kinds. */
export const KIND_GROUPS: { label: string; kinds: ChangeKind[] }[] = [
  { label: "Added", kinds: ["added"] },
  { label: "Changed", kinds: ["changed", "state", "owner", "change_request"] },
  { label: "Merged", kinds: ["merged"] },
  { label: "Conflict found", kinds: ["conflict_found", "analysed", "concern"] },
  { label: "Conflict resolved", kinds: ["conflict_resolved", "reviewed"] },
  { label: "Issues", kinds: ["issue"] },
  { label: "Links", kinds: ["link"] },
];

export interface ChangeEvent {
  id: UUID;
  at: string;
  revision: number | null;
  kind: ChangeKind;
  sentence: string;
  actor_id: UUID | null;
  actor_name: string | null;
  node_ids: UUID[];
  edge_ids: UUID[];
  backfilled: boolean;
}

export interface ChangePage {
  items: ChangeEvent[];
  next_before: string | null;
}

export interface ChangeFilters {
  actor?: string;
  kinds?: ChangeKind[];
  requirement?: string;
  since?: string;
  untilRevision?: number | null;
}

export interface Summary {
  since: string | null;
  until: string;
  since_label: string;
  counts: Record<string, number>;
  count_lines: string[];
  highlights: ChangeEvent[];
  total_events: number;
  markdown: string;
  narrative: { text: string; ai: true; provider: string | null; model: string | null } | null;
  narrative_status?: "ok" | "not_requested" | "no_model" | "unavailable";
}

export type SummaryStart =
  | { kind: "baseline"; baselineId: string }
  | { kind: "date"; since: string }
  | { kind: "visit" };

function query(filters: ChangeFilters, before?: string): string {
  const params = new URLSearchParams();
  if (filters.actor) params.set("actor", filters.actor);
  if (filters.requirement) params.set("requirement", filters.requirement);
  if (filters.since) params.set("since", filters.since);
  if (filters.untilRevision !== undefined && filters.untilRevision !== null) {
    params.set("until_revision", String(filters.untilRevision));
  }
  for (const kind of filters.kinds ?? []) params.append("kind", kind);
  if (before) params.set("before", before);
  params.set("limit", "50");
  return params.toString();
}

export function changesKey(projectId: string): unknown[] {
  return ["changes", projectId];
}

export function useChanges(projectId: string, filters: ChangeFilters, before?: string) {
  return useQuery({
    queryKey: [...changesKey(projectId), filters, before ?? null],
    queryFn: () => apiFetch<ChangePage>(`/projects/${projectId}/changes?${query(filters, before)}`),
  });
}

function startBody(start: SummaryStart): Record<string, unknown> {
  if (start.kind === "baseline") return { since_baseline_id: start.baselineId };
  if (start.kind === "date") return { since: start.since };
  return { since_last_visit: true };
}

/** "Summarise changes since…": exact counts, important changes, Markdown — plus, when asked, one
 *  AI paragraph built only from them (shown labelled AI). */
export function useSummarise(projectId: string) {
  return useMutation({
    mutationFn: ({ start, narrative }: { start: SummaryStart; narrative: boolean }) =>
      apiFetch<Summary>(`/projects/${projectId}/changes/summary`, {
        method: "POST",
        json: { ...startBody(start), narrative },
      }),
  });
}

export function useMarkSeen(projectId: string) {
  return useMutation({
    mutationFn: () =>
      apiFetch<{ seen_at: string; previous: string | null }>(`/projects/${projectId}/changes/seen`, {
        method: "PUT",
      }),
  });
}
