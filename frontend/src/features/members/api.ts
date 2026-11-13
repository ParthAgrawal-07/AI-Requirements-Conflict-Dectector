// Members, roles, join codes and join requests (Abhijeet — US-24, US-25; API by Madhav and Parth,
// contract in docs/contracts/join_codes.md).

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "../../api/client";
import type { RoleRef, UUID } from "../../api/types";

export interface RoleRead extends RoleRef {
  description: string | null;
  permissions: string[];
  grantable_by_join_code: boolean;
}

export type JoinCodeStatus = "active" | "revoked" | "expired" | "exhausted";

export interface JoinCode {
  id: UUID;
  workspace_id: UUID;
  project_id: UUID | null;
  code_hint: string;
  role: RoleRef;
  expires_at: string;
  max_uses: number | null;
  uses: number;
  requires_approval: boolean;
  status: JoinCodeStatus;
  created_by: UUID;
  created_at: string;
  revoked_at: string | null;
}

export interface CreatedJoinCode extends JoinCode {
  code: string; // shown once
}

export interface JoinCodeInput {
  role_id: UUID;
  project_id: UUID | null;
  expires_in_days: 1 | 7 | 30;
  max_uses: number | null;
  requires_approval: boolean;
}

export interface JoinRequest {
  id: UUID;
  workspace_id: UUID;
  project_id: UUID | null;
  join_code_id: UUID;
  user: { id: UUID; full_name: string; email: string };
  role: RoleRef;
  status: "pending" | "approved" | "denied" | "expired";
  created_at: string;
  decided_by: UUID | null;
  decided_at: string | null;
}

export interface JoinResult {
  status: "joined" | "pending_approval";
  workspace_id: UUID;
  project_id: UUID | null;
  join_request_id: UUID | null;
}

export function useRoles(workspaceId: string) {
  return useQuery({
    queryKey: ["roles", workspaceId],
    queryFn: () => apiFetch<RoleRead[]>(`/workspaces/${workspaceId}/roles`),
  });
}

export function useJoinCodes(workspaceId: string) {
  return useQuery({
    queryKey: ["join-codes", workspaceId],
    queryFn: () => apiFetch<JoinCode[]>(`/workspaces/${workspaceId}/join-codes`),
    refetchOnMount: "always", // uses change while the tab is closed; show current counts
  });
}

export function useCreateJoinCode(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: JoinCodeInput) =>
      apiFetch<CreatedJoinCode>(`/workspaces/${workspaceId}/join-codes`, {
        method: "POST",
        json: input,
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["join-codes", workspaceId] }),
  });
}

export function useRevokeJoinCode(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: UUID) => apiFetch<void>(`/join-codes/${id}`, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["join-codes", workspaceId] }),
  });
}

export function useJoinRequests(workspaceId: string) {
  return useQuery({
    queryKey: ["join-requests", workspaceId],
    queryFn: () => apiFetch<JoinRequest[]>(`/workspaces/${workspaceId}/join-requests`),
    refetchOnMount: "always",
  });
}

export function useDecideJoinRequest(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, approve, roleId }: { id: UUID; approve: boolean; roleId?: UUID }) =>
      apiFetch<JoinRequest>(`/workspaces/${workspaceId}/join-requests/${id}/decision`, {
        method: "POST",
        json: { approve, role_id: roleId ?? null },
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["join-requests", workspaceId] }),
  });
}

export function useJoinWithCode() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (code: string) =>
      apiFetch<JoinResult>("/join", { method: "POST", json: { code } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["workspaces"] }),
  });
}

export function useCreateWorkspace() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) =>
      apiFetch<{ id: UUID; name: string }>("/workspaces", { method: "POST", json: { name } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["workspaces"] }),
  });
}
