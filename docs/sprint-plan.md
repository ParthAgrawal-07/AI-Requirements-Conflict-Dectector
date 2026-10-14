<!-- Source: Sprint_Work_Assignment.docx. Edit this file, not the .docx; when a story moves sprint, follow the change-impact matrix in engineering/INDEX.md. -->

# Sprint Work Assignment

Code review routing follows this table (`.github/CODEOWNERS`). Live progress: `engineering/project-status.md`.

*AI Requirements Conflict Detector — Mapped to Frontend / Backend / Testing Pods*

*IT314 — Software Engineering | Built on the 6-Sprint Plan*

## 1. Team Roster & Standing Ownership

Each Backend member owns one pipeline stage for the whole project (matching the original 7-role breakdown); Frontend members split by UI surface; Testing is a dedicated function across every sprint rather than folded into dev work.

| Pod | Name | GitHub | Standing Ownership |
|---|---|---|---|
| Backend | Bansil | @Bansil08 | Document Ingestion & Extraction (parsing, segmentation) |
| Backend | Heet | @the-heet-shah | Embedding & Similarity Search (pgvector, candidate-pair filtering) |
| Backend | Keval | @kevaldarji6126 | LLM Classification Pipeline (prompts, structured output) |
| Backend | Madhav | @PrimeNotFound | Clarification & Impact Analysis |
| Backend | Parth | @ParthAgrawal-07 | Backend API, Auth & Orchestration (FastAPI, Celery/Redis, JWT) |
| Frontend | Pranshu | @pranshu-chovatiya | Upload & Requirements List UI |
| Frontend | Abhijeet | @aprk05 | Findings, Review & Clarification UI |
| Frontend | Dhvani | @DC-01051 | Dashboard, Graph Visualization & DevOps/CI-CD |
| Testing | Abhyudit | @abhyudits | Backend/Pipeline Testing (pytest, classification accuracy benchmarking) |
| Testing | Affan | @Affan689 | Frontend/E2E Testing (Vitest, manual QA against acceptance criteria) |

Parth also owns repo scaffolding, Docker Compose, and CI setup from Sprint 0 — that continues into his Sprint 0/5 tasks below.

## 2. Sprint 0 — Setup (Weeks 1–2)

No user stories delivered this sprint — architecture and scaffolding only.

| Name | Task |
|---|---|
| Bansil | Scaffold ingestion module structure; finalize PDF/DOCX parsing library choices |
| Heet | Set up pgvector extension; select and benchmark embedding model |
| Keval | Draft initial LLM classification prompts; define Pydantic output schemas |
| Madhav | Review clarification/impact requirements; design data model for questions & impact links |
| Parth | Repo scaffolding, Docker Compose, DB schema, auth skeleton, base CI workflows |
| Pranshu | Wireframes for upload & requirements-list UI |
| Abhijeet | Wireframes for findings/review UI |
| Dhvani | Wireframes for dashboard/graph; initial CI workflow review |
| Abhyudit | Set up pytest structure; plan test data (start building planted-conflict test SRS) |
| Affan | Set up Vitest structure; define per-story QA checklist template |

## 3. Sprint 1 — Foundation (Weeks 3–4)

**Stories: US-01 (Upload), US-02 (Extraction), US-04 (View Requirements List) — 13 points**

| Name | Task |
|---|---|
| Bansil | US-02: build extraction & segmentation pipeline (primary owner) |
| Parth | US-01: upload endpoint, file validation, size/format checks |
| Heet | Begin embedding pipeline groundwork (prep for Sprint 2) |
| Keval | Continue classification prompt design & testing against sample requirements |
| Madhav | Define clarification data model; support extraction edge-case handling |
| Pranshu | US-01 upload UI + US-04 requirements list UI (primary owner) |
| Abhijeet | Support UI component library setup (shared with Pranshu) |
| Dhvani | CI pipeline refinement; Docker Compose validation end-to-end |
| Abhyudit | pytest tests for US-02 extraction; validate against sample SRS documents |
| Affan | Vitest tests for US-01/US-04; manual QA of upload flow |

## 4. Sprint 2 — Core Detection (Weeks 5–7) — Integration Checkpoint 1

**Stories: US-19 (Auth), US-03 (Progress Tracking), US-05 (Detect Issues — 13pt core epic), US-07 (Explain/Confidence) — 26 points. This is the heaviest sprint; watch velocity closely (see Section 9).**

| Name | Task |
|---|---|
| Parth | US-19: JWT auth end-to-end (primary owner) |
| Heet | US-05: embedding + candidate-pair pre-filter (primary owner) |
| Keval | US-05: LLM classification (5-category) + US-07: confidence scoring (primary owner) |
| Madhav | Support US-07 rationale/context structure feeding into clarification model |
| Bansil | Support extraction edge cases surfaced by classification testing |
| Pranshu | US-03: progress-tracking UI (job status polling/display) |
| Abhijeet | US-05/US-07 findings UI: side-by-side comparison, confidence badges (primary owner) |
| Dhvani | Celery/Redis async job queue DevOps setup supporting US-03 |
| Abhyudit | Critical: backend classification accuracy tests (precision/recall) against planted-conflict test SRS |
| Affan | E2E test of upload → detect → display flow; UI test for progress tracking |

## 5. Sprint 3 — Review & Impact (Weeks 8–9)

**Stories: US-09 (Clarification Questions), US-10 (Human Review), US-11 (Impact Analysis), US-12 (Version History) — 21 points**

| Name | Task |
|---|---|
| Madhav | US-09: clarification question generation + US-11: impact analysis (primary owner) |
| Parth | US-10: review-state API (accept/reject/dismiss/merge) + US-12: version history backend |
| Bansil | Support version-history data model tie-in with ingestion metadata |
| Heet | Support impact-analysis relationship queries (reusing embedding infrastructure) |
| Keval | Refine classification output to support reclassify/override actions |
| Pranshu | US-12: version history UI |
| Abhijeet | US-09 clarification UI + US-10 review/resolve UI (primary owner) |
| Dhvani | US-11: impact analysis UI (affected-requirements list) |
| Abhyudit | Backend tests for impact analysis & review-state transitions |
| Affan | E2E test of clarification + human-review workflow |

## 6. Sprint 4 — Dashboard & Tuning (Weeks 10–11) — Integration Checkpoint 2

**Stories: US-13 (Dashboard), US-14 (Graph), US-06 (Threshold Tuning), US-08 (Severity) — 18 points**

| Name | Task |
|---|---|
| Parth | Backend support for dashboard aggregation queries (US-13) |
| Keval | US-06: classification threshold configuration backend |
| Heet | US-06: similarity threshold tuning backend |
| Madhav | US-08: severity assignment logic |
| Bansil | Support filtering/search backend for US-13 |
| Dhvani | US-14: dependency/conflict graph visualization — React Flow (primary owner) |
| Pranshu | US-13: dashboard UI (primary owner) |
| Abhijeet | US-08 severity UI + US-06 threshold configuration UI |
| Abhyudit | Backend tests for threshold tuning and severity logic |
| Affan | Full E2E test of dashboard, graph, and severity display — checkpoint validation |

## 7. Sprint 5 — Harden & Ship (Weeks 12–13)

**Stories: US-15 (Feedback Loop), US-16 (Multi-Channel Reports), US-18 (Compliance Protection — conditional), US-22 (Preview Validation) — 16 points**

| Name | Task |
|---|---|
| Parth | US-18: compliance protection backend (if in scope); production deployment (Railway/Render) |
| Madhav | US-15: false-positive feedback loop backend |
| Keval | Support feedback tie-in to classification model/rules |
| Heet | Support feedback tie-in to similarity threshold auto-adjustment |
| Bansil | Final ingestion edge-case hardening |
| Dhvani | Frontend deployment (Vercel); final CI/CD polish; US-16 report delivery infra |
| Pranshu | US-15: dismiss/resolve UI polish |
| Abhijeet | US-16: report UI/export |
| Abhyudit | Full backend regression pass |
| Affan | US-22: low-fidelity preview validation with sample users; full frontend regression pass |

## 8. Sprint 6 — Demo Prep (Week 14)

No new stories — polish, bug fixes, and rehearsal only.

| Name | Task |
|---|---|
| Everyone | Final bug fixes from Sprint 5 regression testing |
| Abhyudit & Affan | Final full test pass (backend + frontend); demo script validation |
| Dhvani | Deployment stability check on both frontend and backend |
| Parth | Backend stability check; prepare demo data/environment |
| Everyone | Rehearse presentation and demo walkthrough |

## 9. Load Check & Risk Note

Sprint 2 carries 26 points across 3 weeks — the heaviest sprint by a clear margin — and lands on three people simultaneously: Heet and Keval both own core pieces of US-05, while Parth independently delivers US-19. Watch this sprint's velocity closely. If it's trending behind by the midpoint of Week 6, the safest cut is US-07 (confidence/explanation) into Sprint 3 — US-05 without US-07 still produces a usable, if less polished, result, and it doesn't block Abhijeet's findings UI from at least showing raw classifications.

Also worth noting: Testing (Abhyudit, Affan) is only 2 people covering both backend and frontend validation across all 6 sprints. Their heaviest load lands in Sprint 2 (classification accuracy is the hardest thing to test well) and Sprint 4/5 (two checkpoints + full regression). If either sprint slips, consider temporarily pulling a Backend or Frontend member into testing support for that sprint only, rather than letting QA silently fall behind the dev pods.
