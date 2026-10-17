// Shared mock data for UI tests. Shapes come from src/types.ts, which mirrors the
// backend models, so a field mismatch fails typecheck instead of passing silently.
import type { Finding, Requirement } from "../src/types";

export const mockRequirement = {
  id: "11111111-1111-4111-8111-111111111111",
  document_id: "22222222-2222-4222-8222-222222222222",
  source_req_id: "REQ-001",
  body: "The system shall allow users to upload SRS documents.",
  location: "Section 3.1",
} satisfies Requirement;

export const mockFinding = {
  id: "33333333-3333-4333-8333-333333333333",
  document_id: mockRequirement.document_id,
  category: "Conflicting",
  status: "flagged",
  severity: null,
  confidence: 0.87,
  candidate_pair_id: "44444444-4444-4444-8444-444444444444",
} satisfies Finding;
