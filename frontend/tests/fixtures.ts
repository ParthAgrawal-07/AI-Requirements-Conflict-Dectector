// Shared mock data for UI tests. Shapes are placeholders until the
// backend API contract is finalised (Sprint 1) - update then.
export const mockRequirement = {
  id: "REQ-001",
  text: "The system shall allow users to upload SRS documents.",
  source: "sample-srs.pdf",
};

export type FindingCategory =
  | "Conflicting"
  | "Duplicate"
  | "Ambiguous"
  | "Incomplete"
  | "Dependent";

export const mockFinding = {
  id: "F-001",
  category: "Conflicting" as FindingCategory,
  confidence: 0.87,
  requirementIds: ["REQ-001", "REQ-002"],
  rationale: "Placeholder rationale.",
};
