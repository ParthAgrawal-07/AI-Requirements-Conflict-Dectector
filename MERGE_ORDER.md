# Sprint 6 — how to apply these zips

Rebuilt for the **feature-wise ownership** in Sprint Plan §2.1: each zip is one owner's features, backend UI and tests together. The code is the same as before; only who ships which file changed. Built on the Sprint 5 end state (`c1d00c6`). Every zip holds **complete files at their repo paths** plus a `README_<name>.md`. Nothing has been committed or pushed.

Testers have a feature zip (merged mid-sprint) and a `-tests` zip (merged last). A `<Name>-2` zip means one person's work has to be split around someone else's (a migration or import order); its README says why.

## Merge order

Open the PRs **in this order** (each one after the previous merged, or rebased on it):

| # | Zip | Depends on | Branch | Stories | What | Lines |
|---|---|---|---|---|---|---|
| 1 | Heet | Sprint 5 end state | `us-55-change-log` | US-55, US-58 | Written change log: change-log tables, migration 0009, change sentences; rule-check recall tuning | 993 |
| 2 | Dhavni | Heet | `us-50-preview-history` | US-50 | Map preview layer, graph revisions and history services | 822 |
| 3 | Affan | Dhavni | `us-53-discussion-votes` | US-53 | Discussion, votes, watch and human links (incl. link edges on the map) — backend and UI | 2,455 |
| 4 | Keval | Affan | `us-15-us-55-ai-feedback` | US-15, US-55, US-61 | Feedback loop and AI feedback view, change-summary paragraph, SRS section prompts | 1,020 |
| 5 | Abhijeet | Keval | `us-18-us-55-compliance-changes-api` | US-18, US-55 | Compliance backend (protection, compliance queue, audit export); the changes API and change-summary route | 1,833 |
| 6 | Dhavni-2 | Abhijeet | `us-18-compliance-ui` | US-18 | Compliance UI: protected badge, protection control, compliance queue and the node-drawer controls (after Abhijeet's backend) | 383 |
| 7 | Abhyudit | Dhavni-2 | `us-42-us-08-us-59-timeline-severity` | US-42, US-08, US-59 | Requirement timeline, severity (with severity sort and feedback tests), open-items report | 2,174 |
| 8 | Bansil | Abhyudit | `us-61-srs-generator` | US-61, US-41 | Updated SRS: generation, readiness, fidelity check, publishing; DOCX, PDF and Markdown exporters | 2,057 |
| 9 | Pranshu | Bansil | `us-61-us-41-srs-export-api` | US-61, US-41, US-15 | SRS API and tests, export API, AI feedback API; excluded-items banner | 1,316 |
| 10 | Keval-2 | Pranshu | `us-61-srs-screen` | US-61 | SRS screen: readiness card, section review, SRS page and its tests (after Pranshu's SRS API) | 943 |
| 11 | Madhav | Keval-2 | `e-s6-security-injection` | S6 testing | Security tests: injection in posts and rate limits (with Affan) | 445 |
| 12 | Heet-2 | Madhav | `us-55-us-50-changes-ui` | US-55, US-50 | Changes panel, map time slider and map page, change-log integration and UI tests | 1,214 |
| 13 | Abhyudit-tests | Heet-2 | `e-s6-final-accuracy` | S6 testing | Final accuracy report and SRS fidelity tests | 125 |
| 14 | Affan-tests | Abhyudit-tests | `e-s6-isolation-a11y` | S6 testing | Tenant isolation sweep, axe accessibility, production smoke | 415 |

**Migrations** (Parth reviews): 0009 (Heet) → 0008a (Affan) → 0009a (Keval) → 0010d (Abhijeet) → 0012a (Bansil) — one head at every step.

## Files shipped by more than one zip

Each zip holds the version of the file as it stands after that zip, so the merge order matters.

| File | Shipped by (in order) |
|---|---|
| `backend/app/api/router.py` | Affan → Keval → Abhijeet → Abhyudit → Bansil → Pranshu |
| `backend/app/graph/deltas.py` | Dhavni → Affan |
| `backend/app/graph/narrator.py` | Affan → Abhijeet |
| `backend/app/intake/concerns.py` | Keval → Abhijeet |
| `backend/app/models/__init__.py` | Heet → Dhavni → Affan → Bansil |
| `backend/app/models/enums.py` | Affan → Keval → Abhijeet → Bansil |
| `backend/app/realtime/events.py` | Affan → Bansil |
| `backend/app/search/rule_checker.py` | Heet → Keval |
| `backend/app/services/change_requests.py` | Affan → Abhijeet |
| `backend/app/services/issues.py` | Affan → Abhijeet |
| `backend/tests/api/test_access_invariants.py` | Dhavni → Affan → Keval |
| `backend/tests/db/test_migrations.py` | Dhavni → Affan → Bansil |
| `backend/tests/permissions/test_matrix.py` | Affan → Abhijeet → Bansil → Pranshu |
| `frontend/src/app/routes.tsx` | Keval → Abhijeet → Dhavni-2 → Pranshu → Keval-2 |
| `frontend/src/app/socket.ts` | Affan → Pranshu |
| `frontend/src/features/map/NodeDrawer.tsx` | Affan → Dhavni-2 → Abhyudit |
| `frontend/src/features/map/api.ts` | Dhavni → Abhijeet |
| `frontend/src/styles/components.css` | Affan → Dhavni-2 → Pranshu |

## Files `main` changed after these zips were built

PR #57 (Sprint 2) and later fixes changed these on `main`. The zips hold complete files, so the person opening the PR merges `main`'s changes in by hand instead of overwriting:

- `backend/app/api/findings.py` (Abhyudit)
- `backend/app/api/requirements.py` (Abhijeet)
- `backend/app/api/router.py` (Affan, Keval, Abhijeet, Abhyudit, Bansil, Pranshu)
- `backend/app/classification/tasks.py` (Abhyudit)
- `backend/app/core/celery_app.py` (Bansil)
- `backend/app/graph/deltas.py` (Dhavni, Affan)
- `backend/app/graph/narrator.py` (Affan, Abhijeet)
- `backend/app/graph/schemas.py` (Affan)
- `backend/app/graph/service.py` (Affan)
- `backend/app/intake/ownership.py` (Abhijeet)
- `backend/app/intake/posts.py` (Abhijeet)
- `backend/app/models/__init__.py` (Heet, Dhavni, Affan, Bansil)
- `backend/app/models/analysis.py` (Abhyudit)
- `backend/app/models/enums.py` (Affan, Keval, Abhijeet, Bansil)
- `backend/app/models/graph.py` (Heet)
- `backend/app/models/project.py` (Keval)
- `backend/app/models/requirement.py` (Abhijeet)
- `backend/app/realtime/events.py` (Affan, Bansil)
- `backend/app/schemas/findings.py` (Abhyudit)
- `backend/app/schemas/requirements.py` (Abhijeet)
- `backend/app/services/findings.py` (Abhyudit)
- `backend/app/services/lifecycle.py` (Abhijeet)
- `backend/app/services/review_state.py` (Abhijeet)
- `backend/tests/api/test_access_invariants.py` (Dhavni, Affan, Keval)
- `backend/tests/classification/test_result_card.py` (Pranshu)
- `backend/tests/db/test_migrations.py` (Dhavni, Affan, Bansil)
- `backend/tests/permissions/test_matrix.py` (Affan, Abhijeet, Bansil, Pranshu)
- `backend/tests/services/test_requirement_runs.py` (Pranshu)
- `frontend/src/app/AppShell.tsx` (Dhavni-2)
- `frontend/src/app/routes.tsx` (Keval, Abhijeet, Dhavni-2, Pranshu, Keval-2)
- `frontend/src/app/socket.ts` (Affan, Pranshu)
- `frontend/src/features/findings/FindingCard.tsx` (Abhyudit)
- `frontend/src/features/findings/FindingDrawer.tsx` (Abhyudit)
- `frontend/src/features/findings/api.ts` (Abhyudit)
- `frontend/src/features/map/GraphCanvas.tsx` (Dhavni)
- `frontend/src/features/map/MapPage.tsx` (Heet-2)
- `frontend/src/features/map/NodeDrawer.tsx` (Affan, Dhavni-2, Abhyudit)
- `frontend/src/features/map/api.ts` (Dhavni, Abhijeet)
- `frontend/src/features/map/useGraphDeltas.ts` (Dhavni)
- `frontend/src/styles/components.css` (Affan, Dhavni-2, Pranshu)

## Verified

- Applying all zips in this order on `c1d00c6` reproduces the Sprint 6 end state byte for byte.
- After **every** step: ruff, ruff format --check, mypy, a single Alembic head, pytest collection and the frontend typecheck pass (rcd-test image, Python 3.11).
