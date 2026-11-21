// Decision rules and decision owners (Pranshu — US-57 UI; API by Parth:
// GET/POST /projects/{p}/decision-rules, PATCH/DELETE /decision-rules/{id},
// GET /{findings|issues|change-requests}/{id}/decision).
// Keys: ["decision-rules", projectId]; ["decision", kind, id] for one item's owner.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "../../api/client";
import type { UUID } from "../../api/types";

export type OwnerKind = "role" | "user" | "requirement_owner";

export interface NamedRef {
  kind: string;
  id: UUID | null;
  name: string;
}

export interface DecisionRule {
  id: UUID;
  name: string;
  priority: number;
  is_default: boolean;
  specificity: number;
  match_category: string | null;
  match_label: string | null;
  match_group: string | null;
  match_req_type: string | null;
  match_protected: boolean | null;
  owner: NamedRef;
  required_reviewers: NamedRef[];
  optional_reviewers: NamedRef[];
}

export interface RuleInput {
  name: string;
  match_category?: string | null;
  match_label?: string | null;
  match_group?: string | null;
  match_req_type?: string | null;
  match_protected?: boolean | null;
  owner_kind: OwnerKind;
  owner_id?: UUID | null;
  required_reviewers?: { kind: "role" | "user"; id: UUID }[];
}

export interface Decision {
  rule_id: UUID | null;
  rule_name: string;
  is_default: boolean;
  owner_kind: OwnerKind;
  owners: { id: UUID; full_name: string }[];
  required_reviewers: NamedRef[];
  sentence: string; // "Decides: Meera — rule Protected requirements"
}

export type Decidable = "findings" | "issues" | "change-requests";

/** In words, what a rule matches: "Protected · group Security". */
export function describeMatch(rule: DecisionRule): string {
  const parts = [
    rule.match_protected === true ? "Protected" : rule.match_protected === false ? "Not protected" : null,
    rule.match_category ? `category ${rule.match_category}` : null,
    rule.match_label ? `label ${rule.match_label}` : null,
    rule.match_group ? `group ${rule.match_group}` : null,
    rule.match_req_type ? `type ${rule.match_req_type.replace("_", "-")}` : null,
  ].filter(Boolean);
  return parts.length ? parts.join(" · ") : "Everything else";
}

export function useDecisionRules(projectId: string) {
  return useQuery({
    queryKey: ["decision-rules", projectId],
    queryFn: () => apiFetch<DecisionRule[]>(`/projects/${projectId}/decision-rules`),
  });
}

export function useCreateRule(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: RuleInput) =>
      apiFetch<DecisionRule>(`/projects/${projectId}/decision-rules`, { method: "POST", json: input }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["decision-rules", projectId] }),
  });
}

export function useDeleteRule(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (ruleId: UUID) => apiFetch<void>(`/decision-rules/${ruleId}`, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["decision-rules", projectId] }),
  });
}

export function useDecision(kind: Decidable, id: UUID | undefined) {
  return useQuery({
    queryKey: ["decision", kind, id],
    enabled: Boolean(id),
    queryFn: () => apiFetch<Decision>(`/${kind}/${id}/decision`),
  });
}
