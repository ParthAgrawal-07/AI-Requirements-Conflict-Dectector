# docs/engineering — Master Index

**AI Requirements Conflict Detector**

| | |
|---|---|
| **Course** | IT314 — Software Engineering, Autumn 2026–27 |
| **Team** | 10 members |
| **Plan** | Revision 5 — planning documents in [`docs/planning/v5/`](../planning/v5/) |
| **Note** | These documents describe both implemented work (Sprint 0–1) and planned work. Implemented parts are marked ✅; everything else is marked as planned rather than described as done |

---

## 1. Document Index (19 documents)

| File | Covers |
|---|---|
| `project-status.md` | Live status, sprint plan, Sprint 1 progress, team ownership, risks |
| `overview.md` | Problem, the extended product, objectives, scope, tech stack, why this project |
| `requirements-spec.md` | FR-01–FR-107, NFR-01–NFR-39, DR-01–DR-25 — mirror of the v5 Requirements Specification |
| `feature-catalog.md` | All 61 stories — priority, points, sprint, epic, owners, trace, status |
| `feature-deep-dive.md` | Story cards for the 10 stories on the protected demo paths |
| `roles-and-access.md` | Permission catalogue, nine default roles, memberships, access tiers |
| `architecture.md` | Flows, module ownership, layers, key decisions |
| `system-design.md` | Architecture views, runtime flows, data, deployment, cross-cutting design |
| `object-design.md` | Domain model, class designs, state machines, object interactions, patterns |
| `diagrams.md` | Class, sequence, activity and state diagrams (Mermaid) |
| `data-model.md` | ER diagram, tables, data dictionary, indexing notes |
| `api-reference.md` | Implemented endpoints (Sprint 0–1) and planned endpoints |
| `task-breakdown.md` | Sprint 0–7 work with owners and dependencies |
| `test-plan.md` | Test strategy, testing plan by sprint, test cases, accuracy validation |
| `devops-guide.md` | Local setup, env config, Docker Compose, CI/CD |
| `migration-runbook.md` | Running and writing Alembic migrations |
| `conflict-detection-strategy.md` | How conflicts are found without losing them to the similarity filter: hybrid candidates, attribute extraction, pre-check notes, recall gates (ADR-30, Sprint 2 and 5) |
| `ai-providers.md` | Gemini (primary) and Groq (backup) LLM providers, failover rules, the bge-small-en-v1.5 embedding model, configuration and open questions (ADR-31) |
| `decision-log.md` | ADR-01–ADR-31 |
| `history.md` | Planning revisions and merged pull requests, with attribution |
| `INDEX.md` (this file) | Master index and change-impact matrix |

Interface contracts agreed in Sprint 0 are in [`docs/contracts/`](../contracts/).

## 2. Source Documents (revision 5)

The planning documents are the source of truth. When they change, update the engineering documents listed against them.

| Planning document | Engineering documents that follow it |
|---|---|
| [`IT314_RCD_Requirements_Spec_v5.md`](../planning/v5/IT314_RCD_Requirements_Spec_v5.md) | `requirements-spec.md` (mirror), `roles-and-access.md` |
| [`IT314_RCD_Product_Backlog_v5.md`](../planning/v5/IT314_RCD_Product_Backlog_v5.md) | `feature-catalog.md`, `feature-deep-dive.md` |
| [`IT314_RCD_Epics_v5.md`](../planning/v5/IT314_RCD_Epics_v5.md) | `feature-catalog.md` (epics, cut order), `project-status.md` (risks, gaps) |
| [`IT314_RCD_Sprint_Plan_v5.md`](../planning/v5/IT314_RCD_Sprint_Plan_v5.md) | `project-status.md`, `task-breakdown.md`, `test-plan.md` |
| [`IT314_RCD_Scope_Extension_v5.md`](../planning/v5/IT314_RCD_Scope_Extension_v5.md) | `overview.md`, `decision-log.md` (ADR-14–ADR-29) |
| [`IT314_RCD_Design_Update_v5.md`](../planning/v5/IT314_RCD_Design_Update_v5.md) | `system-design.md`, `object-design.md`, `data-model.md`, `api-reference.md`, `architecture.md`, `diagrams.md` |
| [`IT314_RCD_Interface_Design_v5.md`](../planning/v5/IT314_RCD_Interface_Design_v5.md) | Wireframes in [`docs/wireframes/`](../wireframes/) |

## 3. Change-Impact Matrix

When one of these changes, check the documents in the "Also update" column before considering the change complete.

| If this changes... | Also update |
|---|---|
| A new/changed FR, NFR, or DR | The v5 Requirements Spec **and** `requirements-spec.md` in the same PR; then `feature-catalog.md`, `feature-deep-dive.md` |
| A backlog story (US-ID) — priority, points, or acceptance criteria | The v5 Backlog, `feature-catalog.md`, `feature-deep-dive.md` (if on a demo path), `task-breakdown.md`, `project-status.md` |
| The sprint plan (which sprint a story lands in, owners) | The v5 Sprint Plan and Epics §4, `project-status.md`, `feature-catalog.md`, `task-breakdown.md`, `test-plan.md` |
| A story's delivery status | `feature-catalog.md`, `project-status.md`, `history.md` |
| The database schema | `data-model.md`, `object-design.md` §2, `migration-runbook.md` if the procedure changes |
| An API endpoint (added/changed/removed) | `api-reference.md`, `architecture.md`, the matching contract in `docs/contracts/` |
| A permission or default role | `roles-and-access.md`, `docs/contracts/permissions.md`, `requirements-spec.md` §1.22 |
| A module/ownership change | `architecture.md`, `project-status.md`, `object-design.md` §10 |
| A new architecture decision | `decision-log.md`, and any doc whose content the decision overrides |
| The issue taxonomy or requirement numbering | `requirements-spec.md` §0, and every doc that cites an FR/NFR/DR ID |
| Anything merged in a given week | `history.md` |

## 4. Known Cross-Document Inconsistencies

The Lab 6 numbering mismatch and the 4-vs-5-category DR-01 issue are **closed** (CR-21, CR-01). Remaining items, all inside the v5 planning documents:

| Where | Inconsistency | Treated as |
|---|---|---|
| Sprint Plan §3 headings | Sprint 1 is headed "34 points" and Sprint 6 "35 points", but their story tables, the calendar and the Epics sum to 37 each | 37 (calendar and tables) |
| Epics §3, EP-04 note | Says US-08 moved to Sprint 4; the EP-04 table, backlog and sprint plan put it in Sprint 6 (rev. 4 move) | Sprint 6 |
| Scope Extension §3 | Module table still lists US-48 (work-item links) in M3; rev. 5 deferred it (SX-33) | Deferred |

These should be fixed in the planning documents; the engineering documents follow the treatment above until then.
