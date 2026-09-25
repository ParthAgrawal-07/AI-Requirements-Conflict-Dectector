# docs/engineering — Master Index

**AI Requirements Conflict Detector**

| | |
|---|---|
| **Course** | IT314 — Software Engineering, Autumn 2026–27 |
| **Team** | 7 members |
| **Note** | This document set reflects the planning stage — no source code exists yet. All stubs, TODOs, and unimplemented features are marked accurately rather than described as done. |

---

## 1. Document Index (16 documents)

| File | Covers |
|---|---|
| `project-status.md` | Live project status, sprint burn-down, team/module ownership, risks |
| `overview.md` | Problem, objectives, scope, tech stack, why this project was chosen |
| `requirements-spec.md` | FR-01–FR-41, NFR-01–NFR-23, DR-01–DR-12, with status and numbering caveats |
| `feature-catalog.md` | All 23 backlog features — ID, priority, owner, status |
| `roles-and-access.md` | App-level role matrix, elicitation stakeholders, team roles |
| `architecture.md` | Module ownership, pipeline flow, deployment, key decision |
| `diagrams.md` | 4 diagrams (class, sequence, state, activity) as native Mermaid |
| `data-model.md` | ER diagram, 7 core tables, data dictionary, indexing notes |
| `api-reference.md` | 10 planned endpoints with schemas and error codes |
| `feature-deep-dive.md` | Per-feature deep dive on the 7 MVP-critical/highest-risk stories |
| `task-breakdown.md` | 60 tasks across Sprints 0–6, with owners and a dependency chain |
| `test-plan.md` | Test strategy, sample test cases, accuracy validation, bug-tracker process |
| `devops-guide.md` | Local setup, env config, Docker Compose, CI/CD |
| `decision-log.md` | 7 ADRs (LLM gateway/pipeline, pgvector, taxonomy, auth, ML depth) |
| `history.md` | Week 0 planning-phase changes with team attribution |
| `INDEX.md` (this file) | Master index and change-impact matrix |

## 2. Change-Impact Matrix

When one of these changes, check the documents in the "Also update" column before considering the change complete.

| If this changes... | Also update |
|---|---|
| A new/changed FR, NFR, or DR | `feature-catalog.md`, `feature-deep-dive.md`, `task-breakdown.md` |
| A backlog story (US-ID) — priority, points, or acceptance criteria | `project-status.md`, `feature-catalog.md`, `task-breakdown.md`, Sprint Plan source doc |
| The sprint plan (which sprint a story lands in) | `project-status.md`, `feature-catalog.md`, `task-breakdown.md` |
| The database schema | `data-model.md`, `diagrams.md` (class + ER diagrams) |
| An API endpoint (added/changed/removed) | `api-reference.md`, `architecture.md` |
| A module/role ownership change | `roles-and-access.md`, `architecture.md`, `project-status.md` |
| A new architecture decision | `decision-log.md`, and any doc whose content the decision overrides |
| The issue taxonomy or a requirements-numbering reconciliation | `requirements-spec.md` (Section 0), and every doc that cites an FR/NFR/DR ID |
| Anything shipped in a given week | `history.md` |

## 3. Known Cross-Document Inconsistency

`requirements-spec.md` documents an unresolved numbering mismatch between the Consolidated Requirements Baseline and the official Lab 6 submission, plus a taxonomy inconsistency in the Lab 6 DR-01 text (4 vs. 5 categories). This index does not resolve it — it is flagged here and in `project-status.md` so it is not lost, and should be closed out before Sprint 1 development begins.

## 4. Source Materials

- Consolidated Product Backlog — 23 user stories, front/back card format
- IT314 Lab 6 Stakeholders & Requirements — official Lab 6 submission (stakeholders, FR/NFR/DR, activity diagram)
- Sprint Plan — 6-sprint mapping of the backlog to the 14-week plan
- Project Context Summary — full planning-conversation summary this document set was generated from
