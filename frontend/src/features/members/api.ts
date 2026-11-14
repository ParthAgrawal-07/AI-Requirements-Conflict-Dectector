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

// ── Members, custom roles and project roles (US-26, US-49; API by Parth) ──────────────────────
export { useMembers, type Member } from "../channels/api";

export interface PermissionInfo {
  name: string;
  description: string;
  group: "Workspace" | "Requirements" | "Review" | "Governance";
}

export interface ReassignmentItem {
  kind: "requirement";
  id: UUID;
  project_id: UUID;
  label: string | null;
  former_owner_id: UUID;
  former_owner_name: string;
}

export interface RoleInput {
  name: string;
  description: string | null;
  permissions: string[];
}

export function usePermissionCatalogue() {
  return useQuery({
    queryKey: ["permission-catalogue"],
    queryFn: () => apiFetch<PermissionInfo[]>("/permissions"),
    staleTime: Infinity, // changes only with a deployment
  });
}

export function useNeedsReassignment(workspaceId: string, enabled: boolean) {
  return useQuery({
    queryKey: ["needs-reassignment", workspaceId],
    enabled,
    queryFn: () => apiFetch<ReassignmentItem[]>(`/workspaces/${workspaceId}/needs-reassignment`),
  });
}

function useWorkspaceMutation<TInput, TResult>(
  workspaceId: string,
  request: (input: TInput) => Promise<TResult>,
  keys: string[],
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: request,
    onSuccess: () =>
      Promise.all(keys.map((key) => queryClient.invalidateQueries({ queryKey: [key, workspaceId] }))),
  });
}

export function useChangeRole(workspaceId: string) {
  return useWorkspaceMutation(
    workspaceId,
    ({ userId, roleId }: { userId: UUID; roleId: UUID }) =>
      apiFetch(`/workspaces/${workspaceId}/members/${userId}`, { method: "PATCH", json: { role_id: roleId } }),
    ["members"],
  );
}

export function useRemoveMember(workspaceId: string) {
  return useWorkspaceMutation(
    workspaceId,
    (userId: UUID) => apiFetch<void>(`/workspaces/${workspaceId}/members/${userId}`, { method: "DELETE" }),
    ["members", "needs-reassignment"],
  );
}

export function useLeaveWorkspace(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch<void>(`/workspaces/${workspaceId}/leave`, { method: "POST" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["workspaces"] }),
  });
}

export function useCreateRole(workspaceId: string) {
  return useWorkspaceMutation(
    workspaceId,
    (input: RoleInput) => apiFetch<RoleRead>(`/workspaces/${workspaceId}/roles`, { method: "POST", json: input }),
    ["roles"],
  );
}

export function useUpdateRole(workspaceId: string) {
  return useWorkspaceMutation(
    workspaceId,
    ({ id, ...input }: RoleInput & { id: UUID }) =>
      apiFetch<RoleRead>(`/roles/${id}`, { method: "PATCH", json: input }),
    ["roles"],
  );
}

export function useDeleteRole(workspaceId: string) {
  return useWorkspaceMutation(
    workspaceId,
    (id: UUID) => apiFetch<void>(`/roles/${id}`, { method: "DELETE" }),
    ["roles"],
  );
}

export interface ProjectMember {
  user_id: UUID;
  full_name: string;
  role_override: RoleRef | null;
  added_at: string;
}

export function useProjectMembers(projectId: string | null) {
  return useQuery({
    queryKey: ["project-members", projectId],
    enabled: Boolean(projectId),
    queryFn: () => apiFetch<ProjectMember[]>(`/projects/${projectId}/members`),
  });
}

/** PUT /projects/{p}/members/{u}: the project-level role, or null for the workspace role. */
export function useSetProjectRole(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, roleId }: { userId: UUID; roleId: UUID | null }) =>
      apiFetch<ProjectMember>(`/projects/${projectId}/members/${userId}`, {
        method: "PUT",
        json: { role_override_id: roleId },
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["project-members", projectId] }),
  });
}
