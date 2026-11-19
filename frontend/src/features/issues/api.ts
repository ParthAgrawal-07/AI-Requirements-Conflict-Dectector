// Issues and raised concerns (Pranshu — US-52, US-56 UI; API by Dhavni and Bansil:
// /projects/{p}/issues, /issues/{id}, /issues/{id}/comments, /projects/{p}/concerns).
// Keys: ["issues", projectId, …] for lists, ["issue", id] and ["issue-comments", id] for one;
// an issue.* event refreshes them (app/socket.ts).

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "../../api/client";
import type { Page, RequirementState, UUID } from "../../api/types";
import type { Finding, FindingCategory } from "../findings/api";

export interface UserRef {
  id: UUID;
  full_name: string;
}

export interface IssueRequirement {
  id: UUID;
  label: string | null;
  state: RequirementState;
  owner_id: UUID | null;
}

export type IssueStatus = "open" | "closed";
export type CloseReason = "resolved_by_merge" | "finding_resolved" | "manual";

export interface Issue {
  id: UUID;
  project_id: UUID;
  number: number;
  key: string; // "ISS-3"
  title: string;
  body: string;
  status: IssueStatus;
  close_reason: CloseReason | null;
  auto: boolean;
  finding_id: UUID | null;
  author: UserRef | null; // null: opened automatically
  labels: string[];
  assignees: UserRef[];
  requirements: IssueRequirement[];
  comment_count: number;
  created_at: string;
  updated_at: string;
  closed_at: string | null;
  closed_by: UUID | null;
}

export interface IssueComment {
  id: UUID;
  author: UserRef | null; // null: written by the app (an auto issue's question)
  body: string;
  created_at: string;
}

export interface IssueFilters {
  status?: IssueStatus;
  label?: string;
  assignee?: UUID;
  requirement?: UUID;
  limit: number;
  offset: number;
}

/** Who found what an issue is about: the analysis (an auto issue), a person (a concern) or a
 *  rule check (Sprint 5). Read from the issue itself — the badge needs no extra request. */
export type IssueSource = "AI" | "Rule" | "Person";

export function sourceOf(issue: Pick<Issue, "auto" | "labels">): IssueSource | null {
  if (issue.auto) return "AI";
  if (issue.labels.includes("rule")) return "Rule";
  if (issue.labels.includes("concern")) return "Person";
  return null;
}

export const CLOSE_REASON_TEXT: Record<CloseReason, string> = {
  resolved_by_merge: "resolved by a merged change request",
  finding_resolved: "its finding was resolved",
  manual: "closed by hand",
};

export function useIssues(projectId: string, filters: IssueFilters) {
  return useQuery({
    queryKey: ["issues", projectId, filters],
    queryFn: ({ signal }) =>
      apiFetch<Page<Issue>>(`/projects/${projectId}/issues`, { query: { ...filters }, signal }),
    placeholderData: keepPreviousData,
  });
}

export function useIssue(issueId: string | undefined) {
  return useQuery({
    queryKey: ["issue", issueId],
    enabled: Boolean(issueId),
    queryFn: () => apiFetch<Issue>(`/issues/${issueId}`),
  });
}

export function useIssueComments(issueId: string | undefined) {
  return useQuery({
    queryKey: ["issue-comments", issueId],
    enabled: Boolean(issueId),
    queryFn: () => apiFetch<IssueComment[]>(`/issues/${issueId}/comments`),
  });
}

export interface IssueInput {
  title: string;
  body?: string;
  labels?: string[];
  assignee_ids?: UUID[];
  requirement_ids: UUID[];
}

export function useCreateIssue(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: IssueInput) =>
      apiFetch<Issue>(`/projects/${projectId}/issues`, { method: "POST", json: input }),
    onSuccess: (issue) => {
      queryClient.setQueryData(["issue", issue.id], issue);
      void queryClient.invalidateQueries({ queryKey: ["issues", projectId] });
    },
  });
}

export interface IssueUpdate {
  title?: string;
  body?: string;
  labels?: string[];
  assignee_ids?: UUID[];
  status?: IssueStatus;
}

export function useUpdateIssue(issueId: string, projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: IssueUpdate) =>
      apiFetch<Issue>(`/issues/${issueId}`, { method: "PATCH", json: input }),
    onSuccess: (issue) => {
      queryClient.setQueryData(["issue", issue.id], issue);
      void queryClient.invalidateQueries({ queryKey: ["issues", projectId] });
    },
  });
}

export function useAddComment(issueId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: string) =>
      apiFetch<IssueComment>(`/issues/${issueId}/comments`, { method: "POST", json: { body } }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["issue-comments", issueId] });
      void queryClient.invalidateQueries({ queryKey: ["issue", issueId] });
    },
  });
}

// ── Raise a concern (US-56, Bansil's API) ──────────────────────────────────────────────────
export interface ConcernInput {
  category: FindingCategory;
  requirement_ids: UUID[];
  explanation: string;
  external_ref?: string;
  severity: "low" | "medium" | "high";
}

export interface Concern {
  finding: Finding;
  issue_id: UUID;
  issue_key: string;
  ai_miss: boolean;
}

export function useRaiseConcern(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: ConcernInput) =>
      apiFetch<Concern>(`/projects/${projectId}/concerns`, { method: "POST", json: input }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["issues", projectId] });
      void queryClient.invalidateQueries({ queryKey: ["findings", projectId] });
    },
  });
}
