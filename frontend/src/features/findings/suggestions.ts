// AI suggestions on a finding (Abhijeet — US-45 panel; API by Madhav:
// GET /findings/{f}/suggestions, POST /findings/{f}/suggestions/regenerate,
// POST /suggestions/{s}/feedback). Key: ["suggestion", findingId]; a suggestion.ready event
// refreshes it (app/socket.ts), and while it is pending the panel polls every 3 s as a fallback.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "../../api/client";
import type { UUID } from "../../api/types";

export const TBD = "[TBD — confirm]";

export interface SuggestionOption {
  text: string;
  target: string | null; // printed ID of the requirement it replaces
  target_requirement_id: UUID | null;
  trade_off: string;
  confidence: number;
  tbd_slots: string[];
}

export interface Suggestion {
  id: UUID;
  finding_id: UUID;
  category: string;
  status: "pending" | "waiting_budget" | "ready" | "failed" | "superseded";
  label: "AI";
  options: SuggestionOption[];
  instruction: string | null;
  error: string | null;
  preferences: { user_id: UUID; full_name: string; option_index: number }[];
  my_outcome: string | null;
}

export type FeedbackAction =
  | "accepted"
  | "accepted_edited"
  | "rejected_meaning"
  | "rejected_infeasible"
  | "rejected_missing_context"
  | "deferred"
  | "prefer";

export interface Prefill {
  kind: "change_request" | "post";
  requirement_id: UUID;
  proposed_body: string;
  source_suggestion_id: UUID;
  finding_id: UUID;
  issue_id: UUID | null;
  issue_number: number | null;
  tbd_slots: string[];
}

export interface FeedbackResponse {
  feedback: { id: UUID; action: string; option_index: number | null };
  prefill: Prefill | null;
  suggestion: Suggestion | null;
}

export const REJECTIONS: { action: FeedbackAction; label: string }[] = [
  { action: "rejected_meaning", label: "changes the intended meaning" },
  { action: "rejected_infeasible", label: "infeasible" },
  { action: "rejected_missing_context", label: "AI missed context" },
];

export function useSuggestion(findingId: UUID | null) {
  return useQuery({
    queryKey: ["suggestion", findingId],
    enabled: Boolean(findingId),
    queryFn: () => apiFetch<Suggestion>(`/findings/${findingId}/suggestions`),
    refetchInterval: (query) =>
      query.state.data && ["pending", "waiting_budget"].includes(query.state.data.status) ? 3000 : false,
  });
}

export function useSuggestionFeedback(findingId: UUID) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: {
      suggestionId: UUID;
      action: FeedbackAction;
      option_index?: number;
      final_text?: string;
      reason?: string;
    }) =>
      apiFetch<FeedbackResponse>(`/suggestions/${input.suggestionId}/feedback`, {
        method: "POST",
        json: {
          action: input.action,
          option_index: input.option_index ?? null,
          final_text: input.final_text ?? null,
          reason: input.reason ?? null,
        },
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["suggestion", findingId] }),
  });
}

export function useRegenerate(findingId: UUID) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (instruction: string) =>
      apiFetch<Suggestion>(`/findings/${findingId}/suggestions/regenerate`, {
        method: "POST",
        json: { instruction },
      }),
    onSuccess: (fresh) => queryClient.setQueryData(["suggestion", findingId], fresh),
  });
}
