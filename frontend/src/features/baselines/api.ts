// Baselines (Pranshu — US-40 UI; API by Parth: POST/GET /projects/{p}/baselines,
// GET /baselines/{b}/compare/{other}). Keys: ["baselines", projectId] and
// ["baseline-compare", a, b]; snapshots never change, so a comparison is cached for good.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "../../api/client";
import type { UUID } from "../../api/types";

export interface Baseline {
  id: UUID;
  project_id: UUID;
  label: string;
  note: string | null;
  baseline_revision: number;
  requirement_count: number;
  created_by: UUID | null;
  created_by_name: string | null;
  created_at: string;
}

export interface Entry {
  requirement_id: UUID;
  label: string | null;
  version: number | null;
  state: string | null;
  body: string | null;
}

export interface Changed {
  requirement_id: UUID;
  label: string | null;
  from_version: number;
  to_version: number;
  before: string;
  after: string;
}

export interface Comparison {
  base: Baseline;
  target: Baseline;
  added: Entry[];
  changed: Changed[];
  removed: Entry[];
  unchanged: number;
}

export function useBaselines(projectId: string) {
  return useQuery({
    queryKey: ["baselines", projectId],
    queryFn: () => apiFetch<Baseline[]>(`/projects/${projectId}/baselines`),
  });
}

export function useFreezeBaseline(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { label: string; note?: string }) =>
      apiFetch<Baseline>(`/projects/${projectId}/baselines`, { method: "POST", json: input }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["baselines", projectId] }),
  });
}

export function useComparison(base: UUID | null, target: UUID | null) {
  return useQuery({
    queryKey: ["baseline-compare", base, target],
    enabled: Boolean(base && target && base !== target),
    queryFn: () => apiFetch<Comparison>(`/baselines/${base}/compare/${target}`),
    staleTime: Infinity,
  });
}
