import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "../../api/client";
import type { Page, RequirementOrigin, RequirementRead, RequirementState } from "../../api/types";

export interface RequirementFilters {
  q?: string;
  state?: RequirementState;
  origin?: RequirementOrigin;
  owner?: string;
  limit: number;
  offset: number;
}

/** GET /projects/{p}/requirements (US-04). Key starts with ["requirements", projectId] so a
 *  finished extraction (analysis.progress done) refreshes every page of it. */
export function useRequirements(projectId: string, filters: RequirementFilters) {
  return useQuery({
    queryKey: ["requirements", projectId, filters],
    queryFn: ({ signal }) =>
      apiFetch<Page<RequirementRead>>(`/projects/${projectId}/requirements`, {
        query: { ...filters },
        signal,
      }),
    placeholderData: keepPreviousData,
  });
}

// ── Ownership (US-36, Bansil's API) ──────────────────────────────────────────────────────────
export interface OwnershipRequest {
  id: string;
  requirement_id: string;
  requester_id: string;
  status: "pending" | "accepted" | "declined";
  note: string | null;
  decided_by: string | null;
  decided_at: string | null;
  created_at: string;
}

export function useOwnershipRequests(requirementId: string, enabled = true) {
  return useQuery({
    queryKey: ["ownership-requests", requirementId],
    enabled,
    queryFn: () =>
      apiFetch<OwnershipRequest[]>(`/requirements/${requirementId}/ownership-requests`),
  });
}

export function useRequestOwnership(requirementId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (note: string) =>
      apiFetch<OwnershipRequest>(`/requirements/${requirementId}/ownership-requests`, {
        method: "POST",
        json: { note: note.trim() || null },
      }),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: ["ownership-requests", requirementId] }),
  });
}

export function useDecideOwnership(requirementId: string, projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ requestId, accept }: { requestId: string; accept: boolean }) =>
      apiFetch<OwnershipRequest>(`/ownership-requests/${requestId}/decision`, {
        method: "POST",
        json: { accept },
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["ownership-requests", requirementId] });
      void queryClient.invalidateQueries({ queryKey: ["requirements", projectId] });
      void queryClient.invalidateQueries({ queryKey: ["requirement", requirementId] });
    },
  });
}

// ── Version history (US-12, Parth's API: GET /requirements/{id}/versions) ────────────────────
export interface RequirementVersion {
  version_no: number;
  body: string;
  changed_by: { id: string; full_name: string } | null; // null for the extracted first version
  changed_at: string;
  change_request: { id: string; key: string } | null; // the RCR it was merged from
}

/** Newest first. Key ["versions", id]: a merge (change_request.merged) refreshes it. */
export function useVersions(requirementId: string | null) {
  return useQuery({
    queryKey: ["versions", requirementId],
    enabled: Boolean(requirementId),
    queryFn: () => apiFetch<RequirementVersion[]>(`/requirements/${requirementId}/versions`),
  });
}
