// Change requests (Abhijeet — US-33, US-34, US-35 UI; API by Bansil (intake), Madhav (impact,
// checks) and Parth (reviews, agreement, merge): /requirements/{id}/change-requests,
// /projects/{p}/change-requests, /change-requests/{id}[/reviews|/agreement|/checks|/merge|…].
// Keys: ["change-requests", projectId, …] for lists; ["change-request", id] and
// ["change-request", id, "reviews" | "agreement" | "checks"] for one, so a change_request.* event
// refreshes all of it with one prefix (app/socket.ts).

import type { RequirementState, UUID } from "../../api/types";
import type { BadgeTone } from "../../components/Badge";

export interface UserRef {
  id: UUID;
  full_name: string;
}

export type ChangeKind = "modify" | "deprecate";
export type ChangeStatus = "draft" | "open" | "needs_update" | "approved" | "merged" | "closed" | "withdrawn";

export interface ChangeRequest {
  id: UUID;
  project_id: UUID;
  number: number;
  key: string; // "RCR-7"
  requirement: {
    id: UUID;
    label: string | null;
    state: RequirementState;
    current_version: number;
    is_protected: boolean;
    owner_id: UUID | null;
  };
  kind: ChangeKind;
  status: ChangeStatus;
  base_version: number;
  proposal_revision: number;
  proposed_body: string | null; // null for a deprecation
  base_body: string; // the text at base_version
  current_body: string; // the text now: differs from base_body once someone else merged
  reason: string;
  proposer: UserRef | null;
  resolves: { id: UUID; key: string; title: string; status: "open" | "closed" }[];
  merged_version: number | null;
  merged_at: string | null;
  closed_at: string | null;
  close_reason: string | null;
  created_at: string;
  updated_at: string;
}

export const ACTIVE: ReadonlySet<ChangeStatus> = new Set(["draft", "open", "needs_update", "approved"]);

export const STATUS_TEXT: Record<ChangeStatus, string> = {
  draft: "Draft",
  open: "Open",
  needs_update: "Needs update",
  approved: "Approved",
  merged: "Merged",
  closed: "Closed",
  withdrawn: "Withdrawn",
};

export const STATUS_TONE: Record<ChangeStatus, BadgeTone> = {
  draft: "neutral",
  open: "info",
  needs_update: "proposed",
  approved: "approved",
  merged: "approved",
  closed: "neutral",
  withdrawn: "neutral",
};

// ── Reviews and agreement (Parth — US-35, FR-65, FR-98) ────────────────────────────────────
export type ReviewDecision = "approve" | "request_changes" | "comment";

export interface InlineComment {
  field: string;
  start_offset: number | null;
  end_offset: number | null;
  body: string;
}

export interface Review {
  id: UUID;
  reviewer: UserRef | null;
  decision: ReviewDecision;
  rationale: string | null;
  proposal_revision: number;
  reviewed_base_version: number;
  dismissed: boolean; // given on an earlier revision or base version (FR-98)
  comments: InlineComment[];
  created_at: string;
}

export interface ReviewRequest {
  reviewer: UserRef | null;
  required: boolean;
  reason: string; // "owner", "direct_conflict", "compliance", "requested", …
  approved: boolean; // approved the current revision
}

export interface Reviews {
  requests: ReviewRequest[];
  reviews: Review[];
}

export interface Unmet {
  code: string;
  message: string;
}

export interface Agreement {
  mergeable: boolean;
  unmet: Unmet[];
}

// ── Impact and consequence checks (Madhav — US-11, US-34; narrative: Keval) ──────────────────
export interface Affected {
  requirement_id: UUID;
  label: string;
  depth: number; // 1 direct, 2 two steps away
  relation: string;
  reason: string;
  status: "confirmed" | "potential";
  owner_id: UUID | null;
  stakeholder_group: string | null;
  is_protected: boolean;
  finding_id: UUID | null;
  path: string[];
}

export interface Impact {
  requirement_id: UUID;
  label: string;
  affected: Affected[];
  owners: UUID[];
  stakeholder_groups: string[];
  work_items: Record<string, unknown>[];
}

export type CheckStatus = "pending" | "pass" | "warning" | "fail" | "info";

export interface Check {
  key: string;
  title: string;
  status: CheckStatus;
  message: string;
  details: Record<string, unknown>;
}

export interface DeltaEntry {
  finding_id: UUID | null;
  category: string;
  requirement_ids: UUID[];
  labels: string[];
  source: string; // "ai", "rule", "person"
  reason: string;
}

export type DeltaGroup = "resolved" | "new" | "still_open" | "must_rerun";

export interface Narrative {
  label: "AI";
  summary: string;
  points: string[];
  cited_ids: string[];
  prompt_version: string;
  model: string;
}

export interface Report {
  id: UUID;
  proposal_revision: number;
  base_version: number;
  baseline_revision: number;
  risk_level: "low" | "medium" | "high" | null;
  risk_reasons: string[];
  affected: Affected[];
  checks: Check[];
  findings_delta: Partial<Record<DeltaGroup, DeltaEntry[]>>;
  narrative: Narrative | null;
  is_stale: boolean;
  llm_calls: number;
  created_at: string;
}

export interface Checks {
  state: "pending" | "done" | "stale";
  stale_reasons: string[];
  report: Report | null;
}
