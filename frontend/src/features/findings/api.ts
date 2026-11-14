// Findings (Abhijeet — US-07 UI; API by Keval: GET /projects/{p}/findings, GET /findings/{id}).
// Key ["findings", projectId, …] — an analysis.completed event refreshes every page of it.

import { keepPreviousData, useQuery } from "@tanstack/react-query";
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
}

export interface FindingFilters {
  category?: FindingCategory;
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
