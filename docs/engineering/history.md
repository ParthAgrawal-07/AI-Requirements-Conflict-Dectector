# Changelog

**Planning-Phase Changes, With Developer Attribution**

> Note: No code has been written yet. All entries below are planning/documentation milestones (Week 0, pre-Sprint 0).

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

## Known Open Items Carried Into Sprint 0

- Numbering mismatch between the Consolidated Requirements Baseline and the Lab 6 submission's FR/NFR/DR numbering — not yet reconciled.
- DR-01 in the Lab 6 submission still states the 4-category taxonomy rather than the adopted 5-category one — needs correction.
- Advanced ML/DL depth decision (fine-tuned embedding model) pending team commitment.
- `.env.example`, `alembic/` migrations, and this Markdown document set are the first artifacts created for GitHub rendering.

## Next Entry

*The next changelog entry is expected at the end of Sprint 0 (Week 2), covering repo scaffolding, DB schema creation, Docker Compose setup, and wireframes.*
