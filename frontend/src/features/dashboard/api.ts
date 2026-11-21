// Quality dashboard (Pranshu — US-13 UI; API by Parth: GET /projects/{p}/analytics,
// GET /workspaces/{w}/analytics). Keys: ["analytics", projectId, filters] and
// ["workspace-analytics", workspaceId]; analysis, issue and change-request events refresh them
// (app/socket.ts), so the numbers follow the work live.

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { apiFetch } from "../../api/client";
import type { RequirementState, UUID } from "../../api/types";

export type Counts = Record<string, number>;

export interface DashboardFilters {
  requirement?: UUID;
  req_type?: "functional" | "non_functional" | "constraint";
  group?: string;
  owner?: UUID;
  state?: RequirementState;
  priority?: "must" | "should" | "could" | "wont";
}

export interface ProjectDashboard {
  project_id: UUID;
  filters: Record<string, string>;
  suggested_filters: { owner?: UUID };
  findings: {
    total: number;
    by_category: Counts;
    by_severity: Counts;
    by_status: Counts;
    by_source: Counts;
  };
  requirements: { total: number; by_state: Counts };
  change_requests: { open: number; by_risk: Counts };
  issues: { open: number; closed: number; closed_by_reason: Counts; auto_open: number };
}

export interface WorkspaceRow {
  project_id: UUID;
  name: string;
  status: string;
  requirements: number;
  open_findings: number;
  high_findings: number;
  open_change_requests: number;
  high_risk_change_requests: number;
  open_issues: number;
}

export interface WorkspaceDashboard {
  projects: WorkspaceRow[];
  totals: Partial<Record<keyof WorkspaceRow, number>>;
}

export function useProjectDashboard(projectId: string, filters: DashboardFilters) {
  return useQuery({
    queryKey: ["analytics", projectId, filters],
    queryFn: ({ signal }) =>
      apiFetch<ProjectDashboard>(`/projects/${projectId}/analytics`, {
        query: { ...filters },
        signal,
      }),
    placeholderData: keepPreviousData,
  });
}

export function useWorkspaceDashboard(workspaceId: string) {
  return useQuery({
    queryKey: ["workspace-analytics", workspaceId],
    queryFn: () => apiFetch<WorkspaceDashboard>(`/workspaces/${workspaceId}/analytics`),
  });
}
