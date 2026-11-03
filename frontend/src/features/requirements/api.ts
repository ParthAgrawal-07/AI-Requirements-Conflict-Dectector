import { keepPreviousData, useQuery } from "@tanstack/react-query";
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
