# Testing & QA

**Test Plan, Test Cases, and Bug Tracker Process (revision 5)**

| | |
|---|---|
| **Backend** | Pytest against real PostgreSQL + pgvector and Redis (not sqlite or mocks) |
| **Frontend** | Vitest + React Testing Library |
| **E2E, load, security** | Playwright, load tests, permission and join-code abuse tests |
| **Testers** | Abhyudit (accuracy, backend) · Affan (E2E, performance, security). Every developer owns the unit tests for their code (D8) |
| **Status** | Backend suite in CI for Sprint 0–1 code; benchmark v1 merged; Playwright, load and accuracy harness not started |

---

## 1. Test Strategy

| Level | Tooling | Focus | Owner |
|---|---|---|---|
| Unit | Pytest, Vitest | Parsers, segmentation, permission catalogue, lint patterns, risk rules, fidelity checker, components | Each developer |
| Database | Pytest + real Postgres | Schema, `CHECK`s, triggers, migrations up and down, models in sync with migrations | Abhyudit |
| API | Pytest + HTTP client | Every endpoint: happy path, a **404** for another workspace, a **403** for a missing permission | Abhyudit |
| Contract / schema | Pydantic validation tests | LLM output never reaches the DB unless schema-valid (FR-15) | Keval |
| Accuracy | Labelled benchmark + evaluation harness | Precision, recall, F1 per category; recall below the similarity threshold; with and without the context pack | Abhyudit |
| E2E | Playwright | Join with a code → upload → findings; composer → live map; change request → merge | Affan |
| Real-time | WebSocket tests | Delivery, tenant isolation over sockets, socket closed on removal within 5 s (NFR-27) | Affan |
| Load | Load tests | NFR-24, NFR-25, NFR-26, NFR-32, NFR-33 | Affan, Dhavni didi |
| Security | Permission matrix, abuse tests | Permission × default role; join-code expiry, use limit, brute force; rate limits; injection in posts | Affan, Madhav |
| Accessibility | Manual + automated checks | WCAG 2.1 AA on core flows; never colour alone (NFR-29) | Affan |
| Usability | US-22 sessions | Low-fidelity prototypes; onboarding within 5 minutes (NFR-31) | Abhyudit, Affan, Abhijeet |

## 2. Testing Plan by Sprint

| Sprint | Abhyudit (accuracy, backend) | Affan (E2E, performance, security) |
|---|---|---|
| S0 | Benchmark v2 plan | Playwright skeleton, permission matrix |
| S1 | API tests for upload and extraction; labelling | Permission tests; join-code expiry, use limit, brute force; E2E join → upload |
| S2 | First accuracy run; usability sessions | WebSocket tests; custom-role tests; usability sessions |
| S3 | **CP1 accuracy report**, with and without the context pack | **CP1 E2E**; map freshness (NFR-32) |
| S4 | Affected sets; auto-issue owners | Self-approval, merge permission, needs update, compliance sign-off |
| S5 | **CP2 recall report** (AI, rules, missed); **suggestion correctness study** (analysts rate 30 suggestions; compared with acceptance) | **Load test** NFR-24–26, 32, 33; CP2 E2E |
| S6 | Regression; final accuracy; change-log sentences match deltas; SRS fidelity check | Security, accessibility, production smoke (with Madhav) |
| S7 | Demo data validation | Bug bash |

## 3. Sample Test Cases by Story

| Story | Test case | Expected result |
|---|---|---|
| US-01 | Upload a `.exe` renamed to `.pdf` | Rejected with a specific error; nothing stored (FR-02, CR-16) |
| US-01 | Upload a file above the configured size limit (default 25 MB) | Rejected before processing begins |
| US-01 | A member without `baseline.manage` uploads "as baseline" | 403; uploading "as proposals" with `doc.upload` succeeds |
| US-02 | Upload an SRS with printed IDs (e.g. REQ-014, REQ-001-A) | IDs preserved verbatim; items without a printed ID stored without one (DR-03) |
| US-02 | A segment the extractor is unsure about | Kept and marked `needs_review` with reasons, never dropped |
| US-60 | Start analysis on a project in `setup` | Refused with `409 project_in_setup`, naming the missing context fields |
| US-60 | Confirm the last required brief field | Project becomes `active`; AI-drafted fields stay labelled until confirmed |
| US-19 | Sign up without a valid join code | Rejected with one generic message (NFR-35) |
| US-27 | Any route, for every permission × default role | Allowed exactly when the catalogue grants it; another workspace's resource is 404 (ADR-12) |
| US-25 | Join code that is expired, used up or revoked | Rejected with one generic message; attempts limited to 5/min per IP and account |
| US-05 | Two requirements with contradictory numeric constraints ("2 s" vs "10 s") | Conflicting, both IDs cited |
| US-05 | Same wording in different sections | Duplicate, not Conflicting |
| US-05 | A requirement using a vague term ("fast") | Ambiguous with the vague term identified, from the pattern catalogue (DR-07) |
| US-58 | Conflicting numeric limits worded too differently for the similarity filter | Caught by a rule check, source **Rule**, not dropped if the LLM disagrees |
| US-31 | Clean live-analysis result | Reads "No issues detected by analysis — analysis can miss conflicts" with **Raise a concern** (DR-21) |
| US-14 | A requirement posted while two browsers show the map | Both show the new node and edge within 2 s without reload (NFR-32) |
| US-35 | Proposer approves their own change request | Approval does not count (SX-13) |
| US-35 | Proposal edited after approval | Earlier approvals dismissed; merge blocked until re-approved (FR-98) |
| US-35 | Competing merge on the same requirement | The other request shows **needs update** (FR-89) |
| US-18 | A finding or change involves a protected requirement | Never auto-resolved or merged without compliance sign-off (FR-21) |
| US-61 | Publish an SRS where a baseline requirement is missing or reworded | Fidelity check fails and blocks publishing (DR-25) |
| US-61 | Narrative section contains a "shall" sentence not in the baseline | Fidelity check fails |

## 4. Accuracy Validation (NFR-21, NFR-22, NFR-37, NFR-39)

Accuracy is measured as precision, recall and F1 **per category** on a labelled benchmark, not an aggregate "agreement" figure (ADR-05).

- **Benchmark v2:** the planted-conflict SRS, 40 post-style requirements and 10 scripted change requests with known affected sets and owners; document-style and post-style items reported separately.
- **Recall is the headline number** (US-05), including planted conflicts worded differently enough to fall **below the similarity threshold**; the report shows how many each layer caught (similarity + AI, rule checks) and how many were missed (NFR-37).
- **Context ablation:** each category with and without the context pack at CP1 and in the final report (NFR-39).
- **Suggestions:** distribution of the six structured outcomes per category, plus an expert-rated correctness score on at least 30 suggestions, because acceptance is not correctness (NFR-36).
- In use, the share of human-raised findings that AI and rules had not flagged ("AI misses") is tracked per category.

## 5. Definition of Done (testing items)

- Unit tests for new logic; an API test per new endpoint, including a 404 test for another workspace and a 403 test for a missing permission.
- CI green: ruff, mypy, pytest, Vitest, Playwright smoke, migration up/down.
- No requirement or message text in audit rows or notification payloads (CR-04).
- AI content labelled; statuses use icon or text as well as colour (NFR-29).

## 6. Bug Tracker Process

- GitHub Issues, labelled by area (ingestion, context, embeddings, classification, clarification/consequences, real-time/graph, auth/permissions, frontend, devops) to match the ownership split in `architecture.md`.
- Severity labels: blocker (breaks a checkpoint or the final demo), major, minor, polish.
- Every bug tied to a US-ID or FR-ID where applicable.
- Bugs found in US-22 usability sessions are logged against the relevant story before implementation continues.

## 7. Reliability Test Notes (NFR-07, NFR-09)

- Simulate LLM API failures: retry up to 3 times with exponential backoff, then record the pair or run as failed (gap G1), never drop it.
- Budget exhausted: the run shows "waiting for budget" and resumes later (NFR-28).
- WebSocket disconnect: the client re-syncs by REST from its `since` cursor or `graph_revision`.
- Backups cover requirement data, messages and audit logs; the restore procedure is documented.
