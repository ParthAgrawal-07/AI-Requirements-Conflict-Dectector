# Project Documentation

A map of every document in the repo. If you only read three, read the
[product backlog](product-backlog.md), the [architecture](engineering/architecture.md)
and the [devops guide](engineering/devops-guide.md).

## Where to start

| I want to… | Read |
|---|---|
| Run the project locally | [`engineering/devops-guide.md`](engineering/devops-guide.md) |
| Know what a story must do (acceptance criteria) | [`product-backlog.md`](product-backlog.md) |
| Find the requirement behind a story (FR/NFR/DR) | [`engineering/requirements-spec.md`](engineering/requirements-spec.md) |
| See what is built and what's next | [`engineering/project-status.md`](engineering/project-status.md) |
| Find my task this sprint | [`sprint-plan.md`](sprint-plan.md), then [`engineering/task-breakdown.md`](engineering/task-breakdown.md) |
| Understand a design decision | [`engineering/decision-log.md`](engineering/decision-log.md) |
| Add a table or endpoint | [`engineering/data-model.md`](engineering/data-model.md), [`engineering/api-reference.md`](engineering/api-reference.md) |

## Product & requirements

| Document | Covers |
|---|---|
| [`product-backlog.md`](product-backlog.md) | 23 user stories (US-01–US-23): story, acceptance criteria, FR trace, merge decisions. **Source of truth for stories.** |
| [`engineering/requirements-spec.md`](engineering/requirements-spec.md) | FR-01–FR-42, NFR-01–NFR-23, DR-01–DR-12, stakeholder elicitation summary |
| [`engineering/feature-catalog.md`](engineering/feature-catalog.md) | One-line index of all 23 stories with owner and sprint |
| [`engineering/feature-deep-dive.md`](engineering/feature-deep-dive.md) | The 7 MVP-critical stories in detail |
| [`engineering/overview.md`](engineering/overview.md) | Problem, objectives, scope, why this project |
| [`engineering/roles-and-access.md`](engineering/roles-and-access.md) | App roles (RBAC), stakeholders, team roles |

## Design

| Document | Covers |
|---|---|
| [`engineering/architecture.md`](engineering/architecture.md) | Pipeline flow, module ownership, layers |
| [`engineering/diagrams.md`](engineering/diagrams.md) | Class, sequence, state and activity diagrams (Mermaid) |
| [`engineering/data-model.md`](engineering/data-model.md) | ER diagram and every table, matching `backend/app/models/` |
| [`engineering/api-reference.md`](engineering/api-reference.md) | Implemented and planned endpoints, error format |
| [`engineering/decision-log.md`](engineering/decision-log.md) | Architecture Decision Records (ADR-01–ADR-07) |
| [`ingestion-design.md`](ingestion-design.md) | Role 1: parsers, segmentation rules, schemas |
| [`clarification-impact-design.md`](clarification-impact-design.md) | Role 4: clarification and change-impact data model (proposal) |
| [`wireframes/`](wireframes/) | UI wireframes (Figma links + PDF exports) |

## Process & quality

| Document | Covers |
|---|---|
| [`sprint-plan.md`](sprint-plan.md) | **Who does what each sprint.** Team roster with GitHub handles |
| [`engineering/project-status.md`](engineering/project-status.md) | Sprint status, ownership, risks |
| [`engineering/task-breakdown.md`](engineering/task-breakdown.md) | 60 tasks (T01–T60) with owners and dependencies |
| [`engineering/test-plan.md`](engineering/test-plan.md) | Test strategy, sample cases, accuracy validation |
| [`../sample_docs/planted_conflicts/LABELING_GUIDE.md`](../sample_docs/planted_conflicts/LABELING_GUIDE.md) | How the benchmark SRS (`srs_v1`) is labeled |
| [`engineering/devops-guide.md`](engineering/devops-guide.md) | Local setup, environment, Docker Compose, CI |
| [`engineering/history.md`](engineering/history.md) | Changelog by sprint |
| [`engineering/INDEX.md`](engineering/INDEX.md) | Change-impact matrix: which docs to update when something changes |

## Conventions

- Write docs in Markdown; GitHub renders `.md` (and Mermaid diagrams) inline but not `.docx`.
- When code and a doc disagree, the code wins. Fix the doc in the same PR.
- Cite IDs (US-xx, FR-xx, ADR-xx) so changes can be traced across documents.
