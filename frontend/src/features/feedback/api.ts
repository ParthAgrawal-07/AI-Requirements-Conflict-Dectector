// The AI feedback report (Abhijeet — US-15 UI; API by Keval: GET /projects/{p}/ai-feedback,
// PUT /projects/{p}/ai-feedback/threshold). Key ["ai-feedback", projectId].

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "../../api/client";
import type { UUID } from "../../api/types";

export interface FeedbackPattern {
  pattern: string; // a rule id, "AI" or "Person"
  source: "ai" | "rule" | "person";
  confirmed: number;
  dismissed: number;
  false_positive_rate: number | null;
  reasons: { reason: string; count: number }[];
  surfaced: boolean;
}

export interface FeedbackCategory {
  category: string;
  open: number;
  confirmed: number;
  dismissed: number;
  patterns: FeedbackPattern[];
  suggestions: Record<string, number>;
}

export interface FeedbackReport {
  project_id: UUID;
  threshold: number;
  categories: FeedbackCategory[];
  surfaced: { category: string; pattern: FeedbackPattern }[];
  suggestion_totals: Record<string, number>;
  self_training: false;
}

/** The six suggestion outcomes (US-45), in the order people see them. */
export const OUTCOME_TEXT: [string, string][] = [
  ["accepted", "Accepted"],
  ["accepted_edited", "Accepted after editing"],
  ["rejected_meaning", "Rejected: changes the meaning"],
  ["rejected_infeasible", "Rejected: not feasible"],
  ["rejected_missing_context", "Rejected: missing context"],
  ["deferred", "Deferred"],
];

export function useAiFeedback(projectId: string) {
  return useQuery({
    queryKey: ["ai-feedback", projectId],
    queryFn: () => apiFetch<FeedbackReport>(`/projects/${projectId}/ai-feedback`),
  });
}

export function useSetFeedbackThreshold(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (threshold: number) =>
      apiFetch<FeedbackReport>(`/projects/${projectId}/ai-feedback/threshold`, { method: "PUT", json: { threshold } }),
    onSuccess: (report) => queryClient.setQueryData(["ai-feedback", projectId], report),
  });
}

/** Share of accepted suggestions (with or without edits) among those decided; null if none. */
export function acceptanceRate(counts: Record<string, number>): number | null {
  const decided = OUTCOME_TEXT.filter(([key]) => key !== "deferred").reduce((sum, [key]) => sum + (counts[key] ?? 0), 0);
  if (decided === 0) return null;
  return Math.round((((counts.accepted ?? 0) + (counts.accepted_edited ?? 0)) / decided) * 100);
}
