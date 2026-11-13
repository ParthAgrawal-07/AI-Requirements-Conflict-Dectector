// Project creation and project context (Abhijeet — US-24, US-60; API by Parth and Bansil,
// contract in docs/contracts/composer-and-context.md §4).

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "../../api/client";
import type { Project, ProjectStatus, UUID } from "../../api/types";

export type BriefField =
  | "purpose"
  | "scope"
  | "actors"
  | "environment"
  | "glossary"
  | "constraints"
  | "quality_goals"
  | "regulations"
  | "references";

export interface GlossaryEntry {
  term: string;
  meaning: string;
}

export interface BriefValues {
  purpose?: string | null;
  scope_in?: string | null;
  scope_out?: string | null;
  actors?: string[] | null;
  environment?: string | null;
  glossary?: GlossaryEntry[] | null;
  constraints?: string | null;
  quality_goals?: string | null;
  regulations?: string | null;
  references?: { title: string; url: string | null }[] | null;
}

export interface BriefFieldState {
  field: BriefField;
  label: string;
  required: boolean;
  filled: boolean;
  status: "ai_drafted" | "confirmed" | null;
}

export interface ProjectContext {
  project_id: UUID;
  project_status: ProjectStatus;
  context_version: number;
  latest: {
    version: number;
    values: BriefValues;
    field_status: Record<string, "ai_drafted" | "confirmed">;
    summary: string | null;
    source_document_id: UUID | null;
    created_at: string;
  } | null;
  fields: BriefFieldState[];
  missing_fields: string[];
  required_confirmed: number;
  required_total: number;
}

export interface ContextSaveResult {
  context: ProjectContext;
  created: boolean;
  activated: boolean;
  open_findings_to_rerun: number;
}

export function contextKey(projectId: string) {
  return ["context", projectId];
}

export function useProjectContext(projectId: string, options: { poll?: boolean } = {}) {
  return useQuery({
    queryKey: contextKey(projectId),
    queryFn: () => apiFetch<ProjectContext>(`/projects/${projectId}/context`),
    // While an initial SRS is being processed, its AI draft appears without a reload.
    refetchInterval: options.poll ? 3000 : false,
  });
}

export function useSaveContext(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { fields: BriefValues; confirm: BriefField[]; reason?: string }) =>
      apiFetch<ContextSaveResult>(`/projects/${projectId}/context`, { method: "PUT", json: body }),
    onSuccess: (result) => {
      queryClient.setQueryData(contextKey(projectId), result.context);
      void queryClient.invalidateQueries({ queryKey: ["project", projectId] });
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}

export function useCreateProject(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; description: string | null }) =>
      apiFetch<Project>(`/workspaces/${workspaceId}/projects`, { method: "POST", json: body }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["projects", workspaceId] }),
  });
}
