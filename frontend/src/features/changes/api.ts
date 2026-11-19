// Change requests (Abhijeet — US-33, US-34, US-35 UI; API by Bansil (intake), Madhav (impact,
// checks) and Parth (reviews, agreement, merge): /requirements/{id}/change-requests,
// /projects/{p}/change-requests, /change-requests/{id}[/reviews|/agreement|/checks|/merge|…].
// Keys: ["change-requests", projectId, …] for lists; ["change-request", id] and
// ["change-request", id, "reviews" | "agreement" | "checks"] for one, so a change_request.* event
// refreshes all of it with one prefix (app/socket.ts).

import { keepPreviousData, useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { apiFetch } from "../../api/client";
import type { Page, RequirementState, UUID } from "../../api/types";
import type { BadgeTone } from "../../components/Badge";

export interface UserRef {
  id: UUID;
  full_name: string;
}

export type ChangeKind = "modify" | "deprecate";
export type ChangeStatus = "draft" | "open" | "needs_update" | "approved" | "merged" | "closed" | "withdrawn";

export interface ChangeRequest {
  id: UUID;
  project_id: UUID;
  number: number;
  key: string; // "RCR-7"
  requirement: {
    id: UUID;
    label: string | null;
    state: RequirementState;
    current_version: number;
    is_protected: boolean;
    owner_id: UUID | null;
  };
  kind: ChangeKind;
  status: ChangeStatus;
  base_version: number;
  proposal_revision: number;
  proposed_body: string | null; // null for a deprecation
  base_body: string; // the text at base_version
  current_body: string; // the text now: differs from base_body once someone else merged
  reason: string;
  proposer: UserRef | null;
  resolves: { id: UUID; key: string; title: string; status: "open" | "closed" }[];
  merged_version: number | null;
  merged_at: string | null;
  closed_at: string | null;
  close_reason: string | null;
  created_at: string;
  updated_at: string;
}

export const ACTIVE: ReadonlySet<ChangeStatus> = new Set(["draft", "open", "needs_update", "approved"]);

export const STATUS_TEXT: Record<ChangeStatus, string> = {
  draft: "Draft",
  open: "Open",
  needs_update: "Needs update",
  approved: "Approved",
  merged: "Merged",
  closed: "Closed",
  withdrawn: "Withdrawn",
};

export const STATUS_TONE: Record<ChangeStatus, BadgeTone> = {
  draft: "neutral",
  open: "info",
  needs_update: "proposed",
  approved: "approved",
  merged: "approved",
  closed: "neutral",
  withdrawn: "neutral",
};

// ── Reviews and agreement (Parth — US-35, FR-65, FR-98) ────────────────────────────────────
export type ReviewDecision = "approve" | "request_changes" | "comment";

export interface InlineComment {
  field: string;
  start_offset: number | null;
  end_offset: number | null;
  body: string;
}

export interface Review {
  id: UUID;
  reviewer: UserRef | null;
  decision: ReviewDecision;
  rationale: string | null;
  proposal_revision: number;
  reviewed_base_version: number;
  dismissed: boolean; // given on an earlier revision or base version (FR-98)
  comments: InlineComment[];
  created_at: string;
}

export interface ReviewRequest {
  reviewer: UserRef | null;
  required: boolean;
  reason: string; // "owner", "direct_conflict", "compliance", "requested", …
  approved: boolean; // approved the current revision
}

export interface Reviews {
  requests: ReviewRequest[];
  reviews: Review[];
}

export interface Unmet {
  code: string;
  message: string;
}

export interface Agreement {
  mergeable: boolean;
  unmet: Unmet[];
}

// ── Impact and consequence checks (Madhav — US-11, US-34; narrative: Keval) ──────────────────
export interface Affected {
  requirement_id: UUID;
  label: string;
  depth: number; // 1 direct, 2 two steps away
  relation: string;
  reason: string;
  status: "confirmed" | "potential";
  owner_id: UUID | null;
  stakeholder_group: string | null;
  is_protected: boolean;
  finding_id: UUID | null;
  path: string[];
}

export interface Impact {
  requirement_id: UUID;
  label: string;
  affected: Affected[];
  owners: UUID[];
  stakeholder_groups: string[];
  work_items: Record<string, unknown>[];
}

export type CheckStatus = "pending" | "pass" | "warning" | "fail" | "info";

export interface Check {
  key: string;
  title: string;
  status: CheckStatus;
  message: string;
  details: Record<string, unknown>;
}

export interface DeltaEntry {
  finding_id: UUID | null;
  category: string;
  requirement_ids: UUID[];
  labels: string[];
  source: string; // "ai", "rule", "person"
  reason: string;
}

export type DeltaGroup = "resolved" | "new" | "still_open" | "must_rerun";

export interface Narrative {
  label: "AI";
  summary: string;
  points: string[];
  cited_ids: string[];
  prompt_version: string;
  model: string;
}

export interface Report {
  id: UUID;
  proposal_revision: number;
  base_version: number;
  baseline_revision: number;
  risk_level: "low" | "medium" | "high" | null;
  risk_reasons: string[];
  affected: Affected[];
  checks: Check[];
  findings_delta: Partial<Record<DeltaGroup, DeltaEntry[]>>;
  narrative: Narrative | null;
  is_stale: boolean;
  llm_calls: number;
  created_at: string;
}

export interface Checks {
  state: "pending" | "done" | "stale";
  stale_reasons: string[];
  report: Report | null;
}

// ── Queries ─────────────────────────────────────────────────────────────────────────────────
export interface ChangeRequestFilters {
  status?: ChangeStatus;
  requirement?: UUID;
  limit: number;
  offset: number;
}

export function useChangeRequests(projectId: string, filters: ChangeRequestFilters) {
  return useQuery({
    queryKey: ["change-requests", projectId, filters],
    queryFn: ({ signal }) =>
      apiFetch<Page<ChangeRequest>>(`/projects/${projectId}/change-requests`, { query: { ...filters }, signal }),
    placeholderData: keepPreviousData,
  });
}

export function useChangeRequest(id: string | undefined) {
  return useQuery({
    queryKey: ["change-request", id],
    enabled: Boolean(id),
    queryFn: () => apiFetch<ChangeRequest>(`/change-requests/${id}`),
  });
}

export function useReviews(id: string) {
  return useQuery({
    queryKey: ["change-request", id, "reviews"],
    queryFn: () => apiFetch<Reviews>(`/change-requests/${id}/reviews`),
  });
}

export function useAgreement(id: string, enabled = true) {
  return useQuery({
    queryKey: ["change-request", id, "agreement"],
    enabled,
    queryFn: () => apiFetch<Agreement>(`/change-requests/${id}/agreement`),
  });
}

export function useChecks(id: string) {
  return useQuery({
    queryKey: ["change-request", id, "checks"],
    queryFn: () => apiFetch<Checks>(`/change-requests/${id}/checks`),
  });
}

/** The change editor's pre-flight: who and what a change would touch, before it is written. */
export function useImpact(requirementId: string | null, kind: ChangeKind) {
  return useQuery({
    queryKey: ["impact", requirementId, kind],
    enabled: Boolean(requirementId),
    queryFn: () => apiFetch<Impact>(`/requirements/${requirementId}/impact`, { query: { kind } }),
  });
}

// ── Mutations ───────────────────────────────────────────────────────────────────────────────
function settle(queryClient: QueryClient, change: ChangeRequest) {
  queryClient.setQueryData(["change-request", change.id], change);
  void queryClient.invalidateQueries({ queryKey: ["change-request", change.id] });
  void queryClient.invalidateQueries({ queryKey: ["change-requests", change.project_id] });
}

export interface ChangeRequestInput {
  kind: ChangeKind;
  proposed_body?: string;
  reason: string;
  base_version: number;
  resolves: number[]; // ISS numbers
  draft: boolean;
  source_suggestion_id?: string; // US-45: the accepted AI suggestion it came from
}

export function useOpenChangeRequest(requirementId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: ChangeRequestInput) =>
      apiFetch<ChangeRequest>(`/requirements/${requirementId}/change-requests`, { method: "POST", json: input }),
    onSuccess: (change) => settle(queryClient, change),
  });
}

export interface ChangeRequestUpdate {
  proposed_body?: string;
  reason?: string;
  rebase?: boolean;
  open?: boolean;
}

export function useUpdateChangeRequest(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: ChangeRequestUpdate) =>
      apiFetch<ChangeRequest>(`/change-requests/${id}`, { method: "PATCH", json: input }),
    onSuccess: (change) => settle(queryClient, change),
  });
}

export interface ReviewInput {
  decision: ReviewDecision;
  rationale?: string;
  comments: InlineComment[];
}

export function useSubmitReview(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: ReviewInput) =>
      apiFetch<ChangeRequest>(`/change-requests/${id}/reviews`, { method: "POST", json: input }),
    onSuccess: (change) => settle(queryClient, change),
  });
}

export function useAddReviewer(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (reviewerId: UUID) =>
      apiFetch<ReviewRequest>(`/change-requests/${id}/reviewers`, { method: "POST", json: { reviewer_id: reviewerId } }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["change-request", id] }),
  });
}

/** Merge (rcr.merge): version n+1, or a 409 ``merge_blocked`` whose details are the unmet
 *  conditions (ApiError.details). A merge also moves the requirement, its versions and issues. */
export function useMerge(change: ChangeRequest) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (acceptedRiskReason: string | undefined) =>
      apiFetch<ChangeRequest>(`/change-requests/${change.id}/merge`, {
        method: "POST",
        json: { accepted_risk_reason: acceptedRiskReason },
      }),
    onSuccess: (merged) => {
      settle(queryClient, merged);
      void queryClient.invalidateQueries({ queryKey: ["requirement", merged.requirement.id] });
      void queryClient.invalidateQueries({ queryKey: ["versions", merged.requirement.id] });
      void queryClient.invalidateQueries({ queryKey: ["requirements", merged.project_id] });
      void queryClient.invalidateQueries({ queryKey: ["issues", merged.project_id] });
    },
    onError: () => void queryClient.invalidateQueries({ queryKey: ["change-request", change.id, "agreement"] }),
  });
}

export function useCloseChangeRequest(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (reason: string) =>
      apiFetch<ChangeRequest>(`/change-requests/${id}/close`, { method: "POST", json: { reason } }),
    onSuccess: (change) => settle(queryClient, change),
  });
}

export function useWithdraw(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch<ChangeRequest>(`/change-requests/${id}/withdraw`, { method: "POST" }),
    onSuccess: (change) => settle(queryClient, change),
  });
}

export function useRerunChecks(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch<void>(`/change-requests/${id}/checks/rerun`, { method: "POST" }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["change-request", id, "checks"] }),
  });
}
