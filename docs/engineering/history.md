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

## Open Items Status

| Item (carried from Week 0) | Status |
|---|---|
| Numbering mismatch between the Consolidated Requirements Baseline and Lab 6 | **Closed** — one canonical numbering (CR-21), `requirements-spec.md` |
| DR-01 states 4 categories instead of 5 | **Closed** — corrected in CR-01 |
| Advanced ML/DL depth (fine-tuned embedding model) | **Open** — gap D6, extension 6 in the scope extension §12 |

## Next Entry

*The next entry is expected at the end of Sprint 1 (Week 3): join-code management, the setup wizard and login UI, and the Sprint 1 exit demo.*
