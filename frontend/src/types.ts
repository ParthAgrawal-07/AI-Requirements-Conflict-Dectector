// Shared API types for app code and tests. They mirror the backend models in
// backend/app/models/ (requirement.py, analysis.py, enums.py). All ids are UUID strings.
// TODO: confirm optional fields and enum string casing against the backend before Sprint 1.

export type UUID = string;

export type FindingCategory =
  | "Conflicting"
  | "Duplicate"
  | "Ambiguous"
  | "Incomplete"
  | "Dependent";

export type FindingStatus =
  | "flagged"
  | "confirmed"
  | "dismissed"
  | "merged"
  | "reclassified";

export type Severity = "low" | "medium" | "high" | "critical";

export interface Requirement {
  id: UUID;
  document_id: UUID;
  /** Identifier from the source document (e.g. "REQ-001"); may be missing. */
  source_req_id: string | null;
  /** The requirement text. */
  body: string;
  /** Where it was found in the source document. */
  location: string | null;
}

interface FindingBase {
  id: UUID;
  document_id: UUID;
  category: FindingCategory;
  status: FindingStatus;
  severity: Severity | null;
  confidence: number; // 0..1
}

/** A finding refers to exactly one of: a candidate pair, or a single requirement. */
export type Finding = FindingBase &
  (
    | { candidate_pair_id: UUID; requirement_id?: null }
    | { requirement_id: UUID; candidate_pair_id?: null }
  );
