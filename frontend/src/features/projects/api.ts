// Workspace, project and document queries (Pranshu — US-01, US-03, US-24).
// Query keys are shared with app/socket.ts, which invalidates ["documents", projectId] on
// analysis.progress events.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "../../api/client";
import type {
  DocumentRead,
  ImportMode,
  Page,
  Project,
  WorkspaceMembership,
} from "../../api/types";

export function useWorkspaces() {
  return useQuery({
    queryKey: ["workspaces"],
    queryFn: () => apiFetch<WorkspaceMembership[]>("/workspaces"),
  });
}

export function useProjects(workspaceId: string | undefined) {
  return useQuery({
    queryKey: ["projects", workspaceId],
    enabled: Boolean(workspaceId),
    queryFn: () =>
      apiFetch<Page<Project>>(`/workspaces/${workspaceId}/projects`, { query: { limit: 100 } }),
  });
}

export function useProject(projectId: string | undefined) {
  return useQuery({
    queryKey: ["project", projectId],
    enabled: Boolean(projectId),
    queryFn: () => apiFetch<Project>(`/projects/${projectId}`),
  });
}

const ACTIVE: DocumentRead["status"][] = ["queued", "processing"];

/** The project's documents. Polls every 3 s while one is still processing — the fallback for
 *  when the socket is down (US-03); with the socket up, events refresh it sooner. */
export function useDocuments(projectId: string | undefined) {
  return useQuery({
    queryKey: ["documents", projectId],
    enabled: Boolean(projectId),
    queryFn: () =>
      apiFetch<Page<DocumentRead>>(`/projects/${projectId}/documents`, { query: { limit: 50 } }),
    refetchInterval: (query) =>
      query.state.data?.items.some((doc) => ACTIVE.includes(doc.status)) ? 3000 : false,
  });
}

export interface UploadInput {
  file: File;
  importMode: ImportMode;
  stakeholderGroup?: string;
}

export function useUploadDocument(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ file, importMode, stakeholderGroup }: UploadInput) => {
      const form = new FormData();
      form.append("file", file);
      form.append("import_mode", importMode);
      if (stakeholderGroup?.trim()) form.append("stakeholder_group", stakeholderGroup.trim());
      return apiFetch<DocumentRead>(`/projects/${projectId}/documents`, {
        method: "POST",
        form,
      });
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["documents", projectId] }),
  });
}

const LAST_KEY = "rcd.lastProject";

/** The last workspace/project opened in this browser (US-24: it opens by default). Not auth
 *  state, so browser storage is fine; nothing breaks when storage is unavailable. */
export function rememberLastProject(workspaceId: string, projectId?: string): void {
  try {
    localStorage.setItem(LAST_KEY, JSON.stringify({ workspaceId, projectId }));
  } catch {
    /* private mode or blocked storage */
  }
}

export function lastProject(): { workspaceId: string; projectId?: string } | null {
  try {
    const raw = localStorage.getItem(LAST_KEY);
    return raw ? (JSON.parse(raw) as { workspaceId: string; projectId?: string }) : null;
  } catch {
    return null;
  }
}
