// Findings (Abhijeet — US-07, US-10 UI; API by Keval, Parth and Madhav: GET /projects/{p}/findings,
// GET /findings/{id}, POST /findings/{id}/review, POST /clarifications/{id}/answer).
// Key ["findings", projectId, …] — an analysis.completed event or a map delta refreshes it.

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "../../api/client";
import type { Page, RequirementOrigin, RequirementState, UUID } from "../../api/types";

export type FindingCategory = "Conflicting" | "Duplicate" | "Ambiguous" | "Incomplete" | "Dependent";
export type FindingStatus = "flagged" | "confirmed" | "dismissed" | "merged" | "reclassified";

export interface FindingRequirement {
  id: UUID;
  label: string | null;
  body: string;
  state: RequirementState;
  is_protected: boolean;
  origin: RequirementOrigin;
  section_heading: string | null;
  location: string | null;
  document_id: UUID | null;
  origin_message_id: UUID | null;
}

export interface EvidenceSpan {
  requirement_id: UUID;
  label: string;
  quote: string;
  start: number;
  end: number;
}

export interface Finding {
  id: UUID;
  project_id: UUID;
  source: "AI";
  category: FindingCategory;
  status: FindingStatus;
  severity: "low" | "medium" | "high" | null;
  confidence: number;
  confidence_percent: number;
  low_confidence: boolean;
  explanation: string;
  evidence_spans: EvidenceSpan[];
  requirements: FindingRequirement[];
  dependency_direction: string | null;
  vague_terms: string[];
  missing_information: string[];
  context_version: number | null;
  prompt_version: string | null;
  analysis_run_id: UUID | null;
  created_at: string;
  /** US-10: what the model said, kept after a human reclassifies it (FR-20). */
  ai_category?: FindingCategory | null;
  merged_into_id?: UUID | null;
  reviewed_by?: UUID | null;
  reviewed_at?: string | null;
  /** US-09: the question, once generated; "resolved" = accepted and its question answered. */
  clarification?: Clarification | null;
  resolved?: boolean;
  llm_model?: string | null;
}

export interface Clarification {
  id: UUID;
  finding_id: UUID;
  question: string;
  addressed_to: string | null;
  answered: boolean;
  resolution: string | null;
  resolved_by: UUID | null;
  resolved_at: string | null;
}

export type ReviewAction = "confirm" | "dismiss" | "merge" | "reclassify" | "reopen" | "escalate";

export interface ReviewInput {
  action: ReviewAction;
  reason?: string;
  category?: FindingCategory;
  merge_into?: UUID;
}

export const STATUS_LABEL: Record<FindingStatus, string> = {
  flagged: "Open",
  confirmed: "Accepted",
  dismissed: "Dismissed",
  merged: "Merged",
  reclassified: "Reclassified",
};

export const PAIR_CATEGORIES: FindingCategory[] = ["Conflicting", "Duplicate", "Dependent"];
export const SINGLE_CATEGORIES: FindingCategory[] = ["Ambiguous", "Incomplete"];

export interface FindingFilters {
  category?: FindingCategory;
  status?: FindingStatus;
  requirement?: UUID;
  low_confidence?: boolean;
  limit: number;
  offset: number;
}

export function useFindings(projectId: string, filters: FindingFilters) {
  return useQuery({
    queryKey: ["findings", projectId, filters],
    queryFn: ({ signal }) =>
      apiFetch<Page<Finding>>(`/projects/${projectId}/findings`, { query: { ...filters }, signal }),
    placeholderData: keepPreviousData,
  });
}

export function useFinding(findingId: string | null) {
  return useQuery({
    queryKey: ["finding", findingId],
    enabled: Boolean(findingId),
    queryFn: () => apiFetch<Finding>(`/findings/${findingId}`),
  });
}

/** US-10. The map hears about it from the graph.delta the server publishes. */
export function useReviewFinding(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ findingId, input }: { findingId: UUID; input: ReviewInput }) =>
      apiFetch<Finding>(`/findings/${findingId}/review`, { method: "POST", json: input }),
    onSuccess: (finding) => {
      queryClient.setQueryData(["finding", finding.id], finding);
      void queryClient.invalidateQueries({ queryKey: ["findings", projectId] });
    },
  });
}

/** US-09, FR-23: mark a clarification question answered with the resolution. */
export function useAnswerClarification(projectId: string, findingId: UUID) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ clarificationId, resolution }: { clarificationId: UUID; resolution: string }) =>
      apiFetch<Clarification>(`/clarifications/${clarificationId}/answer`, {
        method: "POST",
        json: { resolution },
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["finding", findingId] });
      void queryClient.invalidateQueries({ queryKey: ["findings", projectId] });
    },
  });
}

export function isProtected(finding: Finding): boolean {
  return finding.requirements.some((requirement) => requirement.is_protected);
}

/** The category badge: icon and word, never colour alone (NFR-29). */
export const CATEGORY_ICONS: Record<FindingCategory, string> = {
  Conflicting: "✕",
  Duplicate: "⧉",
  Ambiguous: "?",
  Incomplete: "…",
  Dependent: "→",
};

/** Split a requirement's text into plain and highlighted parts from its evidence spans. */
export function highlight(body: string, spans: EvidenceSpan[]): { text: string; marked: boolean }[] {
  const ordered = [...spans].sort((a, b) => a.start - b.start);
  const parts: { text: string; marked: boolean }[] = [];
  let at = 0;
  for (const span of ordered) {
    if (span.start < at || span.end > body.length) continue; // overlapping or out of range
    if (span.start > at) parts.push({ text: body.slice(at, span.start), marked: false });
    parts.push({ text: body.slice(span.start, span.end), marked: true });
    at = span.end;
  }
  if (at < body.length) parts.push({ text: body.slice(at), marked: false });
  return parts;
}
