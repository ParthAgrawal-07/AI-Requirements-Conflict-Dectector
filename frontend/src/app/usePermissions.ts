// What the signed-in member may do here (Pranshu — US-27, FR-80).
//
// A convenience for hiding actions, never the gate: every route checks its permission on the
// server regardless (app/core/auth.py). Reads GET /me/permissions for a project or a workspace.

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../api/client";
import type { MyPermissions } from "../api/types";

export type Scope = { projectId: string } | { workspaceId: string };

export interface Permissions {
  can: (permission: string) => boolean;
  role: string | null;
  isLoading: boolean;
}

export function permissionsKey(scope: Scope | null): unknown[] {
  if (!scope) return ["permissions", "none"];
  return "projectId" in scope
    ? ["permissions", "project", scope.projectId]
    : ["permissions", "workspace", scope.workspaceId];
}

export function usePermissions(scope: Scope | null): Permissions {
  const query = useQuery({
    queryKey: permissionsKey(scope),
    enabled: scope !== null,
    queryFn: () =>
      apiFetch<MyPermissions>("/me/permissions", {
        query:
          scope && "projectId" in scope
            ? { project: scope.projectId }
            : { workspace: scope ? scope.workspaceId : undefined },
      }),
  });
  const granted = new Set(query.data?.permissions ?? []);
  // Protected-only grants (Compliance Reviewer's finding.review) do not unlock general actions.
  for (const restricted of query.data?.protected_only ?? []) granted.delete(restricted);
  return {
    can: (permission: string) => granted.has(permission),
    role: query.data?.role.name ?? null,
    isLoading: query.isLoading,
  };
}
