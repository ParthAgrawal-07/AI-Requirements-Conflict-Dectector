# Changelog

**Changes by Sprint, With Developer Attribution**

> Newest first. Add an entry when a sprint closes, listing the merged PRs.

---

## Sprint 0 — Setup (merged by 2026-10-14)

| Change | PR | Owner |
|---|---|---|
| Repo structure, docs set, CI with lint/type-check/Docker build | #1, #2, #3 | Parth Agrawal |
| Ingestion module scaffold: `Parser` base, PDF (PyMuPDF) and DOCX (python-docx) parsers, basic segmentation | #4 | Bansil Bhanderi |
| DB schema (10 tables) + Alembic migration 0001, JWT auth + roles, error format, Docker Compose (db/redis/migrate/backend/worker/frontend), Makefile, CI with Postgres/Redis services | #6 | Parth Agrawal |
| Clarification & change-impact design document (Role 4) | #9 | Madhav Bhatt |
| Upload-screen wireframe (Figma + PDF) | #11, #14, #15 | Pranshu Chovatiya |
| Pytest markers, placeholder test packages, sample-SRS fixture | #13 | Abhyudit (abhyudits) |
| Planted-conflicts benchmark: `srs_v1`, labels, labeling guide | #16 | Abhyudit (abhyudits) |

**Carried into Sprint 1 (open PRs):** #7 upload endpoint (US-01), #8 extraction and segmentation (US-02), #17 frontend test harness, #12 wireframe docs, #5 foundation fixes.

**Resolved from Week 0's open items:** the FR/NFR/DR numbering is reconciled (Lab 6 numbering is canonical, CR-21), DR-01 is amended to 5 categories, and `.env.example` and the Alembic migrations now exist.

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

## Open Items Carried Into Sprint 0 (Week 0 snapshot)

- Numbering mismatch between the Consolidated Requirements Baseline and the Lab 6 submission's FR/NFR/DR numbering — not yet reconciled.
- DR-01 in the Lab 6 submission still states the 4-category taxonomy rather than the adopted 5-category one — needs correction.
- Advanced ML/DL depth decision (fine-tuned embedding model) pending team commitment.
- `.env.example`, `alembic/` migrations, and this Markdown document set are the first artifacts created for GitHub rendering.

## Next Entry

*Sprint 1 (Weeks 3–4): upload, extraction, requirements list.*
