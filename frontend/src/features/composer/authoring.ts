// Authoring aids in the composer (Bansil — US-51 UI; lint engine by Keval, routes by Pranshu:
// GET /lint/catalogue, POST /projects/{p}/preflight, POST /projects/{p}/improve-wording).
//
// Lint runs here, in the browser, on the catalogue the server serves — the same file
// backend/app/lint/engine.py runs — so it costs no request while typing (NFR-34). The score uses
// the same weights as the server: 100 minus 25 per error, 10 per warning, 3 per info.
// Keys: ["lint-catalogue"]; pre-flight and wording are mutations (nothing is cached or stored).

import { useMutation, useQuery } from "@tanstack/react-query";
import { apiFetch } from "../../api/client";
import type { UUID } from "../../api/types";

export type LintSeverity = "info" | "warning" | "error";
export type Quality = "good" | "fair" | "poor";

export interface LintEntry {
  id: string;
  category: string;
  pattern: string;
  message: string;
  hint: string;
  severity: LintSeverity;
}

export interface LintCatalogue {
  version: number;
  entries: LintEntry[];
}

export interface LintIssue {
  ruleId: string;
  category: string;
  severity: LintSeverity;
  start: number;
  end: number;
  match: string;
  message: string;
  hint: string;
}

export interface LintResult {
  issues: LintIssue[];
  score: number;
  quality: Quality;
}

const WEIGHTS: Record<LintSeverity, number> = { error: 25, warning: 10, info: 3 };
const MAX_ISSUES = 50;

export function scoreOf(issues: LintIssue[]): { score: number; quality: Quality } {
  const score = Math.max(0, 100 - issues.reduce((sum, issue) => sum + WEIGHTS[issue.severity], 0));
  return { score, quality: score >= 80 ? "good" : score >= 50 ? "fair" : "poor" };
}

/** Every catalogue match in reading order (a mirror of app/lint/engine.py ``lint``). */
export function lint(text: string, catalogue: LintCatalogue): LintResult {
  const issues: LintIssue[] = [];
  for (const entry of catalogue.entries) {
    let pattern: RegExp;
    try {
      pattern = new RegExp(entry.pattern, "gi");
    } catch {
      continue; // a pattern this browser cannot compile is skipped, never fatal
    }
    for (const found of text.matchAll(pattern)) {
      if (!found[0] || found.index === undefined) continue;
      issues.push({
        ruleId: entry.id,
        category: entry.category,
        severity: entry.severity,
        start: found.index,
        end: found.index + found[0].length,
        match: found[0],
        message: entry.message,
        hint: entry.hint,
      });
    }
  }
  issues.sort((a, b) => a.start - b.start || a.end - b.end || a.ruleId.localeCompare(b.ruleId));
  const kept = issues.slice(0, MAX_ISSUES);
  return { issues: kept, ...scoreOf(kept) };
}

export interface Segment {
  text: string;
  issue: LintIssue | null;
}

/** The text cut into plain runs and flagged runs, for underlining (overlaps: first one wins). */
export function segments(text: string, issues: LintIssue[]): Segment[] {
  const parts: Segment[] = [];
  let at = 0;
  for (const issue of issues) {
    if (issue.start < at) continue;
    if (issue.start > at) parts.push({ text: text.slice(at, issue.start), issue: null });
    parts.push({ text: text.slice(issue.start, issue.end), issue });
    at = issue.end;
  }
  if (at < text.length) parts.push({ text: text.slice(at), issue: null });
  return parts;
}

export function useLintCatalogue() {
  return useQuery({
    queryKey: ["lint-catalogue"],
    queryFn: () => apiFetch<LintCatalogue>("/lint/catalogue"),
    staleTime: Infinity,
  });
}

export interface LikelyFinding {
  category: string;
  requirement_id: UUID | null;
  label: string | null;
  confidence: number;
  rationale: string;
  low_confidence: boolean;
}

export interface PreflightResult {
  status: "done" | "partial" | "budget" | "unavailable";
  likely_findings: LikelyFinding[];
  compared: UUID[];
  llm_calls: number;
  budget: { remaining: number | null; monthly: number };
  label: "AI";
}

export interface WordingSuggestion {
  original: string;
  proposed: string;
  template: string;
  changes: string[];
  tbd_slots: string[];
  lint_before: number;
  lint_after: number;
  label: "AI";
}

export function usePreflight(projectId: string) {
  return useMutation({
    mutationFn: (input: { text: string; requirementId?: UUID }) =>
      apiFetch<PreflightResult>(`/projects/${projectId}/preflight`, {
        method: "POST",
        json: { text: input.text, requirement_id: input.requirementId ?? null },
      }),
  });
}

export function useImproveWording(projectId: string) {
  return useMutation({
    mutationFn: (text: string) =>
      apiFetch<WordingSuggestion>(`/projects/${projectId}/improve-wording`, {
        method: "POST",
        json: { text },
      }),
  });
}
