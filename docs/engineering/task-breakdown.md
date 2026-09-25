# Development Tasks

**60 Tasks Across Sprints 0–6, With Owners & Dependencies**

| | |
|---|---|
| **Status** | All tasks below are planned — none started yet |
| **Source** | Derived from the team's Sprint Plan and Consolidated Product Backlog acceptance criteria |

---

## 1. Full Task List

| # | Task | Sprint | Owner | Depends on |
|---|---|---|---|---|
| T01 | Scaffold monorepo (backend/, frontend/, docs/) | Sprint 0 | Role 5 | — |
| T02 | Design initial DB schema (7 tables) + alembic setup | Sprint 0 | Role 2 | — |
| T03 | Docker Compose (Postgres+pgvector, Redis, backend, frontend) | Sprint 0 | Role 7 | T01 |
| T04 | Low-fidelity wireframes (upload, findings, dashboard) | Sprint 0 | Role 6 | — |
| T05 | Upload endpoint (POST /documents) | Sprint 1 | Role 1 / Role 5 | T01, T02 |
| T06 | File format & size validation (FR-02) | Sprint 1 | Role 1 | T05 |
| T07 | Upload progress/status UI | Sprint 1 | Role 6 | T05 |
| T08 | PDF text extraction (PyMuPDF) | Sprint 1 | Role 1 | T05 |
| T09 | DOCX text extraction (python-docx) | Sprint 1 | Role 1 | T05 |
| T10 | Sentence segmentation (spaCy) + REQ-ID preservation | Sprint 1 | Role 1 | T08, T09 |
| T11 | Requirements-list API (GET .../requirements) | Sprint 1 | Role 1 / Role 5 | T10 |
| T12 | Requirements-list UI (US-04) | Sprint 1 | Role 6 | T11 |
| T13 | JWT auth backend (login, token issuance) | Sprint 2 | Role 5 | T01 |
| T14 | Login UI + protected-route handling | Sprint 2 | Role 6 | T13 |
| T15 | Workspace scoping on all endpoints (FR-38) | Sprint 2 | Role 5 | T13 |
| T16 | Async job status API (US-03) | Sprint 2 | Role 5 | T05 |
| T17 | Job progress UI polling/websocket | Sprint 2 | Role 6 | T16 |
| T18 | Embedding generation (Sentence-Transformers) | Sprint 2 | Role 2 | T10 |
| T19 | pgvector storage + candidate-pair ranking | Sprint 2 | Role 2 | T18 |
| T20 | Classification prompt design (5-category taxonomy) | Sprint 2 | Role 3 | T19 |
| T21 | Classification pipeline wiring (Celery task) | Sprint 2 | Role 3 | T20 |
| T22 | Structured-output schema validation + retry (NFR-07) | Sprint 2 | Role 3 | T21 |
| T23 | Confidence scoring + rationale attachment (US-07) | Sprint 2 | Role 3 | T22 |
| T24 | Findings list UI with confidence badges | Sprint 2 | Role 6 | T23 |
| T25 | Clarification-question prompt design | Sprint 3 | Role 4 | T22 |
| T26 | Clarification API (generate + mark answered) | Sprint 3 | Role 4 | T25 |
| T27 | Clarification UI | Sprint 3 | Role 6 | T26 |
| T28 | Review-action API: confirm/dismiss/merge (US-10) | Sprint 3 | Role 5 | T22 |
| T29 | Reclassify logic (preserve original AI output — FR-20) | Sprint 3 | Role 3 / Role 4 | T28 |
| T30 | Findings review UI (confirm/dismiss/merge/reclassify) | Sprint 3 | Role 6 | T28, T29 |
| T31 | Change-impact analysis engine (US-11) | Sprint 3 | Role 4 | T22 |
| T32 | Impacted-requirements API | Sprint 3 | Role 5 | T31 |
| T33 | Impact-preview UI (shown before save) | Sprint 3 | Role 6 | T32 |
| T34 | Requirement version-history schema + API (US-12) | Sprint 3 | Role 4 | T02 |
| T35 | Version-history UI | Sprint 3 | Role 6 | T34 |
| T36 | Dashboard aggregation API (counts by category) | Sprint 4 | Role 7 | T22 |
| T37 | Quality dashboard UI (US-13) | Sprint 4 | Role 7 | T36 |
| T38 | Drill-down navigation (summary → findings list) | Sprint 4 | Role 6 | T36 |
| T39 | Relationship-graph data API (US-14) | Sprint 4 | Role 7 | T22 |
| T40 | React Flow graph component | Sprint 4 | Role 7 | T39 |
| T41 | Graph interaction (zoom, filter by category) | Sprint 4 | Role 7 | T40 |
| T42 | Threshold-tuning config API (US-06) | Sprint 4 | Role 2 | T19 |
| T43 | Threshold-tuning UI with preview cases | Sprint 4 | Role 6 | T42 |
| T44 | Severity field + API (US-08) | Sprint 4 | Role 5 | T22 |
| T45 | Severity badge UI | Sprint 4 | Role 6 | T44 |
| T46 | Dismiss/resolve feedback-loop API (US-15) | Sprint 5 | Role 5 | T28 |
| T47 | Feedback-loop UI | Sprint 5 | Role 6 | T46 |
| T48 | PDF/CSV report export (US-16) | Sprint 5 | Role 7 | T36 |
| T49 | Scheduled email digest job | Sprint 5 | Role 7 | T48 |
| T50 | Report-delivery UI (channel selection) | Sprint 5 | Role 7 | T48 |
| T51 | Protected-requirement flag + enforcement (US-18) | Sprint 5 | Role 5 | T15 |
| T52 | Manual-review routing for protected requirements | Sprint 5 | Role 5 | T51 |
| T53 | Audit logging for protected-requirement access (NFR-13) | Sprint 5 | Role 5 | T52 |
| T54 | Low-fidelity preview mode (US-22) | Sprint 5 | Role 6 | T29 |
| T55 | QA validation session on preview output | Sprint 5 | QA Engineer (team-wide) | T54 |
| T56 | Pytest suite for backend (see `test-plan.md`) | Sprint 5 | All backend roles | T05–T53 |
| T57 | Vitest + RTL suite for frontend | Sprint 5 | All frontend roles | T07–T55 |
| T58 | End-to-end demo script + fixture SRS document | Sprint 6 | All | T56, T57 |
| T59 | Final polish pass (UI copy, empty/error states) | Sprint 6 | Role 6 / Role 7 | T58 |
| T60 | README + demo recording for submission | Sprint 6 | Role 7 | T59 |

## 2. Dependency Notes

- Sprint 1 is pure plumbing (upload → extraction → list) — every later sprint's tasks block on it.
- US-05's classification tasks (T18–T23) are split into embedding, prompt design, pipeline wiring, and validation sub-tasks per the sprint plan's own risk note, rather than left as one 13-point block.
- Frontend tasks in Sprints 3–4 (review UI, impact UI, dashboard, graph) all depend on the Sprint 2 classification pipeline producing real findings to render.
- Protected-requirement enforcement (T51–T53) depends on the JWT/workspace auth work from Sprint 2 (T15) rather than being buildable standalone.
