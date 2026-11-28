# Changelog

**Planning and Implementation Changes, With Developer Attribution**

> Week 0 entries are planning milestones. From Sprint 0 on, entries come from merged pull requests; authors are given by GitHub handle.

---

## Week 0 — Project Selection & Planning

| Date/Milestone | Change | Owner(s) |
|---|---|---|
| Project selection | Ranked 100+ candidate SE project ideas by placement value, feasibility, and extensibility; merged rankings across all 7 members; selected AI Requirements Conflict Detector | Whole team |
| Tech stack lock | Finalized frontend (React/Vite/TS), backend (FastAPI/Celery/Redis), AI/NLP (Sentence-Transformers/pgvector/LLM API), and infra (Docker/Railway-Render/Vercel/GitHub Actions) stack | Whole team |
| Team structure | Split into 7 role-based ownership areas (ingestion, embedding, classification, clarification/impact, backend API, frontend core, frontend viz/DevOps) | Whole team |
| 14-week plan | Locked Week 7 and Week 11 integration checkpoints and the scope-reduction plan (cut impact analysis/graph first, protect detection) | Whole team |
| Stakeholder elicitation | Identified 10 stakeholder groups, matched each to an elicitation technique, completed elicitation for 8 of 10 groups | Whole team |
| Requirements drafting | 7 independent FR/NFR/DR + user-story drafts authored in parallel | Whole team (individual drafts) |
| Requirements consolidation | Merged 7 drafts into a Consolidated Requirements Baseline and a 23-story Consolidated Product Backlog, with source-draft tagging for traceability | Whole team |
| Taxonomy decision | Standardized on the 5-category issue taxonomy (adding Incomplete) over the 4-category framing used in 3 of 7 drafts | Whole team |
| Metric decision | Standardized accuracy measurement on precision/recall/F1 over an arbitrary "80% agreement" target | Whole team |
| Lab Assignment 6 submission | Submitted stakeholder/elicitation + FR-01–41/NFR-01–23/DR-01–12 + hand-drawn activity diagram | Whole team |
| Sprint plan | Mapped the 23-story backlog into 6 sprints aligned to the Week 7/11 checkpoints, with US-23 excluded as outcome-only | Whole team |
| Engineering docs (this set) | Generated the docs/engineering document set — status, overview, requirements, features, roles, architecture, diagrams, data model, API, feature deep-dive, tasks, testing, deployment, decisions, changelog, index | Whole team |

## Steps 6 and 7 — Conflict Review and Scope Extension (planning)

| Milestone | Change | Owner(s) |
|---|---|---|
| Step 6 conflict review | Six review passes over requirements and backlog; CR-01–CR-23, SC-x, G-x. DR-01 corrected to five categories (CR-01); one canonical FR/NFR/DR numbering (CR-21); severity defined (FR-42, CR-15) | Whole team |
| Step 7 scope extension, rev. 1 | Widened into a collaborative requirements workspace for a 10-member team: workspaces, projects, channels, requirement posts, change requests, notifications, baselines; 48 stories | Whole team |
| Rev. 2 | Join codes instead of email invitations; 9 default roles plus custom roles; live requirements map; GitHub-style issues and PR-style change requests; EARS composer, lint, pre-flight | Whole team |
| Rev. 3 | AI resolution suggestions for every finding with human feedback (US-45 → Must); written change log and summaries (US-55) | Whole team |
| Rev. 4 (trust review) | Human-raised concerns, agreement rules, findings delta, decision rules, rule-based cross-checks, open-items report (US-56–US-59); US-16, US-32, US-44 deferred | Whole team |
| Rev. 5 | Compulsory project context (US-60) and LLM-generated updated SRS (US-61); US-48 deferred. 61 stories, 284 points, 224 scheduled | Whole team |

## Sprint 0–1 — Implementation (merged pull requests)

| Date | PR | Change | Author |
|---|---|---|---|
| 2026-09-23 | #1 | CI workflows | ParthAgrawal-07 |
| 2026-09-25 | #2 | Project documents (this document set) merged into `main` | ParthAgrawal-07 |
| 2026-09-25 | #3 | Linting (ruff, eslint), type-checking (mypy, tsc) and Docker build in CI | ParthAgrawal-07 |
| 2026-09-27 | #4 | Ingestion module scaffold | Bansil08 |
| 2026-09-29 | #6 | DB schema, auth skeleton, Docker Compose, CI/CD, dev tooling | ParthAgrawal-07 |
| 2026-10-13 | #9 | Sprint 0 clarification and impact design | PrimeNotFound |
| 2026-10-13 | #11, #14 | Sprint 0 wireframes | pranshu-chovatiya |
| 2026-10-13 | #15 | README | pranshu-chovatiya |
| 2026-10-14 | #13 | pytest structure (markers, packages, sample path fixture) | abhyudits |
| 2026-10-14 | #16 | Planted-conflicts benchmark (labelling guide, SRS v1, labels) | abhyudits |
| 2026-10-14 | #18 | Repo structure tidy-up, CODEOWNERS, sample SRS fixture fix | Bansil08 |
| 2026-10-14 | #20 | Similarity-threshold env test isolated from the container environment | abhyudits |
| 2026-10-15 | #22 | Requirements conflict detector wireframes | aprk05 |
| 2026-10-18 | #7 | US-01 document upload endpoint, validation, storage and extraction task | ParthAgrawal-07 |
| 2026-10-20 | #26 | US-19/24/27/01/04: tenancy, permission-based roles, sign-up with a code, projects (migrations `0003`, `0004`) | ParthAgrawal-07 |
| 2026-10-22 | #8 | US-02 requirement extraction and segmentation, printed IDs and sections | Bansil08 |
| 2026-10-22 | #27 | US-60 project context, AI-drafted brief, EARS templates, composer schema (migration `0011`) | Bansil08 |

## Sprints 1–6 — Implementation (merged pull requests #28 onward)

Generated from GitHub on 28 Nov 2026. Dates are merge dates, so some sprint work lands after its sprint's
calendar weeks; each title carries the story IDs. Work for Sprints 3–6 was split by feature, not layer
(PR #75), so one PR usually holds a feature's backend, UI and tests.

| Merged | PR | Change | Author |
|---|---|---|---|
| 2026-10-22 | #28 | docs: add RCD v5 planning documents | Bansil08 |
| 2026-10-22 | #29 | docs: sync docs/engineering with the RCD v5 planning documents | Bansil08 |
| 2026-10-26 | #32 | feat(embeddings): Sprint 0-1 embedding stage, pgvector store, and hint latency spike | the-heet-shah |
| 2026-10-26 | #33 | docs: add ADR-30 detection strategy and ADR-31 AI providers | ParthAgrawal-07 |
| 2026-10-26 | #34 | chore(repo): add AGENTS.md, CLAUDE.md and CodeRabbit config | ParthAgrawal-07 |
| 2026-10-26 | #35 | feat(classification): LLM client, context pack, and classifier skelet… | kevaldarji6126 |
| 2026-10-30 | #30 | E-S0/S1: benchmark v2 plan, srs_v1 review, planted SRS, labels, and upload/extraction tests | abhyudits |
| 2026-11-02 | #38 | test(permissions): US-27 permission matrix and join-code security tests | Affan689 |
| 2026-11-02 | #40 | feat(auth): implement join codes lifecycle and consequences schemas (… | PrimeNotFound |
| 2026-11-02 | #41 | feat(auth): list a workspace's assignable roles | ParthAgrawal-07 |
| 2026-11-03 | #36 | Implement sprint0 real-time graph foundation | DC-01051 |
| 2026-11-03 | #37 | feat(frontend): app shell, component kit, auth, upload, requirements list | pranshu-chovatiya |
| 2026-11-03 | #43 | feat(processing): US-03 analysis progress and realtime updates | DC-01051 |
| 2026-11-03 | #44 | refactor(auth): remove the TEST1234 development join-code stub | ParthAgrawal-07 |
| 2026-11-04 | #39 | Feature/sprint 1 UI foundation | aprk05 |
| 2026-11-04 | #45 | feat(auth): silent re-login with a rotating refresh cookie (US-19) | ParthAgrawal-07 |
| 2026-11-07 | #47 | feat(auth): members, custom roles and project roles (US-26, US-49) | ParthAgrawal-07 |
| 2026-11-07 | #48 | docs: G3 plan for filtering headings and prose from extraction (Bansil, S0) | Bansil08 |
| 2026-11-07 | #50 | feat(channels): implement project channels lifecycle and unread counts (US-28) | PrimeNotFound |
| 2026-11-07 | #51 | feat: add channel messages and project graph API | DC-01051 |
| 2026-11-08 | #49 | feat(intake): drafts, requirement posts and G3 cleanup (Bansil, S2) | Bansil08 |
| 2026-11-13 | #42 | feat(classification): US-05 classification, US-07 findings API (Sprint 2) | kevaldarji6126 |
| 2026-11-13 | #46 | feat(embeddings): US-05 candidate pair generation and cosine pre-filter | the-heet-shah |
| 2026-11-13 | #52 | feat(analysis): orchestrate embed, candidates and classification (US-05) | ParthAgrawal-07 |
| 2026-11-13 | #53 | Sprint 2 – Channels UI implementation (us‑28‑us‑29) & temporary repo snapshot | pranshu-chovatiya |
| 2026-11-13 | #55 | test(e2e): Playwright smoke and Sprint 1 create-code, join, upload flow | Affan689 |
| 2026-11-13 | #56 | feat(eval): benchmark runner and first accuracy report (US-05, US-22) | abhyudits |
| 2026-11-13 | #57 | feat(frontend): implement Sprint 2 channels and messaging (US-28, US-29) | pranshu-chovatiya |
| 2026-11-13 | #58 | feat(embeddings): US-05 candidate pair generation and cosine pre-filter | the-heet-shah |
| 2026-11-14 | #59 | feat(frontend): findings, members and roles UI (US-07, US-26, US-49) | ParthAgrawal-07 |
| 2026-11-15 | #61 | feat(graph): add live graph revisions and deltas | DC-01051 |
| 2026-11-15 | #62 | feat(embeddings): incremental retrieval and similar-requirement hints (US-31, FR-83) | the-heet-shah |
| 2026-11-15 | #64 | Us 31 retrieval hints | the-heet-shah |
| 2026-11-18 | #60 | feat(clarifications): questions, thread posts and answers (US-09) | PrimeNotFound |
| 2026-11-18 | #63 | feat(frontend): map, review actions and graph deltas UI (US-14, US-10) | aprk05 |
| 2026-11-18 | #65 | feat(classification): live classification, Redis budget guard, model provenance, result card (US-31) | kevaldarji6126 |
| 2026-11-18 | #66 | feat(lifecycle): requirement lifecycle states and sign-off (US-37) | ParthAgrawal-07 |
| 2026-11-18 | #67 | feat(ownership): owners, stakeholder groups and ownership requests (US-36) | Bansil08 |
| 2026-11-18 | #68 | feat: requirement composer with EARS templates — backend and UI (US-30) | pranshu-chovatiya |
| 2026-11-18 | #69 | feat(review): US-10 human review of findings with the protected guard | Affan689 |
| 2026-11-18 | #70 | feat(analysis): requirement runs for posted requirements (US-31) | ParthAgrawal-07 |
| 2026-11-18 | #78 | feat: add automatic conflict issues (US-52) | DC-01051 |
| 2026-11-18 | #80 | feat(search): impact analysis, relationship queries and change-request API client (US-11, US-33) | the-heet-shah |
| 2026-11-18 | #82 | Us 11 impact relations | the-heet-shah |
| 2026-11-19 | #71 | feat(frontend): issue pages, map UI and review actions (US-52, US-14,… | aprk05 |
| 2026-11-19 | #72 | feat(change-requests): merge, needs-update and agreement guard (US-35) | ParthAgrawal-07 |
| 2026-11-19 | #73 | feat(US-34): AI narrative of consequence report and result-card source badges | kevaldarji6126 |
| 2026-11-19 | #74 | feat(history): US-12 version history and US-35 merge box | Affan689 |
| 2026-11-19 | #75 | docs: rebalance Sprint 3-6 ownership by feature | ParthAgrawal-07 |
| 2026-11-19 | #76 | feat(change-requests): change-request intake, editor and diff view (US-33) | Bansil08 |
| 2026-11-19 | #77 | feat(consequences): consequence checks, delta, risk and Checks tab (US-34) | PrimeNotFound |
| 2026-11-19 | #79 | feat(change-requests): change-request list and page (US-33) | pranshu-chovatiya |
| 2026-11-19 | #81 | feat(reviews): review policy, reviews migration 0007c and ReviewsTab UI (US-35) | the-heet-shah |
| 2026-11-19 | #83 | Us 35 reviews | the-heet-shah |
| 2026-11-19 | #84 | US-56: raise a concern (human-raised findings) with an AI-miss flag | abhyudits |
| 2026-11-19 | #85 | E-S4: scripted change requests, affected sets, findings delta and auto-issue owners | abhyudits |
| 2026-11-19 | #86 | feat(issues): issues API client for the frontend (US-52, US-56) | Bansil08 |
| 2026-11-19 | #88 | feat(change-requests): review and merge routes for US-35 | Bansil08 |
| 2026-11-19 | #93 | E-S3: CP1 post-style benchmark, runner options and accuracy report | abhyudits |
| 2026-11-21 | #100 | feat(notifications): notifications backend and graph optimizations (U… | aprk05 |
| 2026-11-21 | #101 | feat(search, db): attribute index, rule cross-checks, threshold preview and re-analysis (US-58, US-06) | the-heet-shah |
| 2026-11-21 | #102 | Us 58 us 06 rule checks | the-heet-shah |
| 2026-11-21 | #103 | Sprint 5 step 2: rule checks and threshold tuning (US-58, US-06) | ParthAgrawal-07 |
| 2026-11-21 | #87 | feat(notifications): add inbox UI and CP2 load tests | DC-01051 |
| 2026-11-21 | #89 | feat(baselines): baseline snapshots, comparison and authoring-aids API (US-40, US-51) | pranshu-chovatiya |
| 2026-11-21 | #90 | US-13, US-45: quality dashboard and AI suggestion panel | abhyudits |
| 2026-11-21 | #91 | feat(decision-rules): decision rules engine and API (US-57) | ParthAgrawal-07 |
| 2026-11-21 | #92 | E-S5: CP2 below-threshold set, recall by layer, suggestion rating study and report | abhyudits |
| 2026-11-21 | #95 | feat(suggestions): AI suggestion service with append-only feedback (US-45) | PrimeNotFound |
| 2026-11-21 | #96 | feat(authoring): authoring panel and changes from accepted suggestions (US-51, US-45) | Bansil08 |
| 2026-11-21 | #97 | feat(US-51, US-58, US-45): lint engine v2, pre-flight, AI wording, at… | kevaldarji6126 |
| 2026-11-21 | #98 | feat(decisions): US-57 decision owners, rules tab and project settings | Affan689 |
| 2026-11-21 | #99 | test(e2e): CP2 full loop from rule conflict to snapshot comparison | Affan689 |
| 2026-11-23 | #119 | feat(infra): single-VM production stack and deploy on push to main | ParthAgrawal-07 |
| 2026-11-23 | #120 | fix(frontend): send a first-run admin to create a workspace | ParthAgrawal-07 |
| 2026-11-23 | #121 | docs: add bug and feature issue forms | ParthAgrawal-07 |
| 2026-11-24 | #110 | feat(graph): written change log, migration 0009 and rule recall tuning (US-55, US-58) | the-heet-shah |
| 2026-11-24 | #113 | Us 55 change log | the-heet-shah |
| 2026-11-24 | #114 | feat: integrate sprint 6 graph history and preview | DC-01051 |
| 2026-11-24 | #122 | feat(discussion): US-53 comments, votes, watch and human links | Affan689 |
| 2026-11-28 | #124 | fix(ingestion): rebuild borderless PDF tables from line positions (US-02, FR-03) | Bansil08 |
| 2026-11-28 | #125 | fix(auth): rate-limit login attempts per e-mail and per address | ParthAgrawal-07 |

### Open at the time of writing (not on `main`)

| PR | Change | Stories |
|---|---|---|
| #105 | Final accuracy report and SRS fidelity tests | S6 testing |
| #106 | Requirement timeline, finding severity, open-items report | US-42, US-08, US-59 |
| #107 | SRS API, export API, AI feedback API | US-61, US-41, US-15 |
| #108 | Updated SRS generation, readiness, fidelity, exporters | US-61, US-41 |
| #109 | Injection and rate-limit security tests | S6 testing |
| #111, #112 | Changes panel, map time slider and map page | US-55, US-50 |
| #116 | Compliance backend, protection, changes API | US-18, US-55 |
| #118 | Compliance UI | US-18 |
| #94, #104 | Docker runtime fixes | Infra |

## Open Items Status

| Item (carried from Week 0) | Status |
|---|---|
| Numbering mismatch between the Consolidated Requirements Baseline and Lab 6 | **Closed** — one canonical numbering (CR-21), `requirements-spec.md` |
| DR-01 states 4 categories instead of 5 | **Closed** — corrected in CR-01 |
| Advanced ML/DL depth (fine-tuned embedding model) | **Open** — gap D6, extension 6 in the scope extension §12 |

## Next Entry

*Sprint 7 (release week): merge the open Sprint 6 PRs in the order of the Sprint 6 `MERGE_ORDER.md`, then
the bug bash and the final demo. Submission deadline 3 Dec 2026; no commits after it.*
