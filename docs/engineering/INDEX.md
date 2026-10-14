# docs/engineering — Master Index

**AI Requirements Conflict Detector**

| | |
|---|---|
| **Course** | IT314 — Software Engineering, Autumn 2026–27 |
| **Team** | 10 members in three groups: Backend (5), Frontend (3), Testing (2). See [`../sprint-plan.md`](../sprint-plan.md) |
| **Note** | Synced with the code on `main` as of 2026-10-14 (Sprint 0 merged). Each doc says what is implemented and what is planned. When a doc and the code disagree, the code wins. |

---

## 1. Document Index

| File | Covers |
|---|---|
| `project-status.md` | Live project status, sprint burn-down, team/module ownership, risks |
| `overview.md` | Problem, objectives, scope, tech stack, why this project was chosen |
| `requirements-spec.md` | FR-01–FR-42, NFR-01–NFR-23, DR-01–DR-12 (canonical numbering) |
| `feature-catalog.md` | All 23 backlog features — ID, priority, owner, status |
| `roles-and-access.md` | App-level role matrix, elicitation stakeholders, team roles |
| `architecture.md` | Module ownership, pipeline flow, deployment, key decision |
| `diagrams.md` | 4 diagrams (class, sequence, state, activity) as native Mermaid |
| `data-model.md` | ER diagram and all 10 tables, matching `backend/app/models/` |
| `api-reference.md` | Live endpoints (auth, health), planned endpoints, error format |
| `feature-deep-dive.md` | Per-feature deep dive on the 7 MVP-critical/highest-risk stories |
| `task-breakdown.md` | 60 tasks across Sprints 0–6, with owners and a dependency chain |
| `test-plan.md` | Test strategy, sample test cases, accuracy validation, bug-tracker process |
| `devops-guide.md` | Local setup, env config, Docker Compose, CI/CD |
| `decision-log.md` | 7 ADRs (LLM gateway/pipeline, pgvector, taxonomy, auth, ML depth) |
| `history.md` | Changelog by sprint, with PRs and owners |
| `INDEX.md` (this file) | Master index and change-impact matrix |

**Outside `docs/engineering/`:**

| File | Covers |
|---|---|
| `../README.md` | Map of all documentation, by task |
| `../sprint-plan.md` | Who does what each sprint: 10 people, three groups, GitHub handles |
| `../product-backlog.md` | **Source of truth for stories:** all 23 stories with acceptance criteria |
| `../ingestion-design.md` | Role 1 module design |
| `../clarification-impact-design.md` | Role 4 module design (proposal) |
| `../wireframes/` | UI wireframes |
| `../../sample_docs/planted_conflicts/` | Labeled benchmark SRS + labeling guide |

## 2. Change-Impact Matrix

When one of these changes, check the documents in the "Also update" column before considering the change complete.

| If this changes... | Also update |
|---|---|
| A new/changed FR, NFR, or DR | `feature-catalog.md`, `feature-deep-dive.md`, `task-breakdown.md` |
| A backlog story (US-ID) — priority, points, or acceptance criteria | `../product-backlog.md` first, then `feature-catalog.md`, `feature-deep-dive.md` (if covered), `project-status.md`, `task-breakdown.md` |
| The sprint plan (which sprint a story lands in, or who owns it) | `../sprint-plan.md` first, then `project-status.md`, `feature-catalog.md`, `task-breakdown.md`, `.github/CODEOWNERS` |
| The database schema (new Alembic migration) | `data-model.md`, `diagrams.md` (class diagram) |
| An API endpoint (added/changed/removed) | `api-reference.md`, `architecture.md` |
| A module/role ownership change | `../sprint-plan.md`, `.github/CODEOWNERS`, `roles-and-access.md`, `architecture.md`, `project-status.md` |
| A new architecture decision | `decision-log.md`, and any doc whose content the decision overrides |
| The issue taxonomy or a requirements-numbering reconciliation | `requirements-spec.md` (Section 0), and every doc that cites an FR/NFR/DR ID |
| A PR merges | `task-breakdown.md` (Progress table); at sprint end, `history.md` and `project-status.md` |

## 3. Known Open Questions

- **Resolved:** the FR/NFR/DR numbering mismatch and the DR-01 taxonomy wording (see `requirements-spec.md`, Section 0).
- **Open:** severity levels. US-08/FR-42 say Low/Medium/High, but the `Severity` enum also has `critical` (`data-model.md`, Section 4).
- **Open:** clarification cardinality (1:1 now, 1:N proposed) and the impact-links table (`../clarification-impact-design.md`).

## 4. Source Materials

- [`../product-backlog.md`](../product-backlog.md): Markdown copy of `Consolidated_Product_Backlog_v2_tracked.docx` (23 stories, tracked changes accepted)
- IT314 Lab 6 Stakeholders & Requirements: the official Lab 6 submission (stakeholders, FR/NFR/DR, activity diagram)
- [`../sprint-plan.md`](../sprint-plan.md): Markdown copy of `Sprint_Work_Assignment.docx` (per-person tasks for Sprints 0–6)
- Project Context Summary: the planning-conversation summary this document set was first generated from
