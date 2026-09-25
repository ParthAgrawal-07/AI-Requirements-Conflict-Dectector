# Testing & QA

**Test Plan, Test Cases, and Bug Tracker Process**

| | |
|---|---|
| **Backend** | Pytest |
| **Frontend** | Vitest + React Testing Library |
| **Status** | Planned — no tests written yet |

---

## 1. Test Strategy

| Level | Tooling | Focus |
|---|---|---|
| Unit | Pytest (backend), Vitest (frontend) | Ingestion parsers, similarity ranking, prompt templates, individual components |
| Integration | Pytest + test containers (Postgres/pgvector, Redis) | Upload → extraction → embedding → classification pipeline end to end |
| Contract / schema | Pydantic validation tests | LLM classification output never reaches the DB unless schema-valid (FR-15) |
| UI / component | React Testing Library | Findings review actions, dashboard rendering, graph interactions |
| End-to-end (manual) | US-22 low-fidelity preview session | QA Engineer walk-through before full deployment |

## 2. Sample Test Cases by Story

| Story | Test case | Expected result |
|---|---|---|
| US-01 | Upload a .exe file renamed to .pdf | Rejected with a specific "unsupported or corrupted file" error (FR-02) |
| US-01 | Upload a file above the configured size limit | Rejected before processing begins |
| US-02 | Upload an SRS with existing REQ-IDs (e.g., REQ-014) | Extracted requirements preserve REQ-014, not a regenerated ID (DR-03) |
| US-05 | Two requirements with same wording, different sections | Classified Duplicate, not Conflicting |
| US-05 | Two requirements with contradictory numeric constraints ("2s" vs "10s") | Classified Conflicting with both requirement IDs cited |
| US-05 | A requirement missing acceptance criteria for a vague term ("fast") | Classified Ambiguous or Incomplete, with the vague term identified |
| US-07 | A finding below the confidence threshold | UI shows "low confidence — recommend manual review" (FR-13) |
| US-18 | A finding involves a requirement marked protected | Auto-merge/duplicate-removal is blocked; routed to manual review (DR-05) |
| US-11 | Edit a requirement referenced by 3 other requirements | All 3 appear in the impact list before the edit is saved (FR-25) |
| US-19 | Call any endpoint except /auth/login without a token | Returns 401 |

## 3. Accuracy Validation (NFR-21, NFR-22)

Classification accuracy is validated with precision/recall/F1 against a labeled benchmark set of requirement pairs, not an arbitrary "80% agreement" target (a deliberate merge decision — see `requirements-spec.md`). The confidence-scoring mechanism is re-validated periodically against user feedback captured via the dismiss/resolve loop (US-15).

- Build a small labeled benchmark set (pairs pre-tagged Conflicting/Duplicate/Ambiguous/Incomplete/Dependent/None) before Sprint 2's integration checkpoint.
- Track precision, recall, and F1 per category, not just an aggregate score — some categories (e.g., Incomplete) are expected to be harder than others.
- Log every dismiss/reclassify action (already required by FR-19, FR-20) as future benchmark-set candidates.

## 4. Bug Tracker Process

- GitHub Issues, labeled by pipeline stage (ingestion / embedding / classification / clarification / frontend / devops) to match the 7-role ownership split.
- Severity labels: blocker (breaks Week 7 or Week 11 checkpoint), major, minor, polish.
- Every bug tied to a specific US-ID or FR-ID where applicable, so fixes stay traceable the same way features are.
- A bug found during the US-22 low-fidelity preview session is logged against the relevant requirement/finding before full implementation continues, per that story's own acceptance criteria.

## 5. Reliability Test Notes (NFR-07, NFR-09)

- Simulate LLM API failures and confirm retry (up to 3x, exponential backoff) before a classification is marked failed.
- Simulate extraction/embedding/vector-search failures and confirm the system surfaces actionable status rather than failing silently.
- Confirm automated backup/recovery covers requirement data and audit logs, not just the primary tables.
