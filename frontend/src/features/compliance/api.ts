// Compliance protection (Abhijeet — US-18 UI; API by Parth: PUT /requirements/{r}/protection,
// GET /projects/{p}/compliance/queue, GET /projects/{p}/compliance/audit?format=json|csv).
// Keys: ["compliance-queue", projectId]; a protection change also refreshes the requirement,
// the map (its nodes carry is_protected) and the findings that show the flag.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiDownload, apiFetch } from "../../api/client";
import type { UUID } from "../../api/types";

export type QueueKind = "finding" | "change_request" | "signoff";
export type QueueStatus = "awaiting_decision" | "awaiting_approval" | "approved" | "awaiting_signoff";

export interface QueueItem {
  kind: QueueKind;
  id: UUID;
  requirement_ids: UUID[];
  labels: string[];
  title: string;
  status: QueueStatus;
  since: string;
  done_by: UUID | null;
  done_by_name: string | null;
}

export interface ProtectedRequirement {
  requirement_id: UUID;
  label: string;
  state: string;
  current_version: number;
  signed_off_version: number | null;
  signed_off_by: UUID | null;
  signed_off_by_name: string | null;
  signed_off_at: string | null;
  protected_by: UUID | null;
  protected_by_name: string | null;
  protected_at: string | null;
  protection_reason: string | null;
}

export interface ComplianceQueue {
  pending: QueueItem[];
  protected: ProtectedRequirement[];
}

export interface Protection {
  requirement_id: UUID;
  label: string | null;
  is_protected: boolean;
  protected_by: UUID | null;
  protected_at: string | null;
  protection_reason: string | null;
}

export const STATUS_TEXT: Record<QueueStatus, string> = {
  awaiting_decision: "Awaiting a compliance decision",
  awaiting_approval: "Awaiting compliance approval",
  approved: "Approved by compliance",
  awaiting_signoff: "Awaiting sign-off",
};

export const KIND_TEXT: Record<QueueKind, string> = {
  finding: "Finding",
  change_request: "Change request",
  signoff: "Sign-off",
};

export function useComplianceQueue(projectId: string, enabled = true) {
  return useQuery({
    queryKey: ["compliance-queue", projectId],
    enabled,
    queryFn: () => apiFetch<ComplianceQueue>(`/projects/${projectId}/compliance/queue`),
  });
}

export function useSetProtection(projectId: string, requirementId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { protected: boolean; reason?: string }) =>
      apiFetch<Protection>(`/requirements/${requirementId}/protection`, {
        method: "PUT",
        json: { protected: input.protected, reason: input.reason },
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["requirement", requirementId] });
      void queryClient.invalidateQueries({ queryKey: ["compliance-queue", projectId] });
      void queryClient.invalidateQueries({ queryKey: ["graph", projectId] });
      void queryClient.invalidateQueries({ queryKey: ["findings", projectId] });
    },
  });
}

/** The immutable trail as a file. The server records the export itself in the audit log. */
export function downloadTrail(projectId: string, format: "csv" | "json"): Promise<void> {
  return apiDownload(`/projects/${projectId}/compliance/audit`, `compliance-trail.${format}`, { format });
}
