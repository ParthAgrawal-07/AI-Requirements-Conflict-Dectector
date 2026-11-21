# Sprint 5 — how to apply these zips

Rebuilt for the **feature-wise ownership** in Sprint Plan §2.1: each zip is one owner's features, backend UI and tests together. The code is the same as before; only who ships which file changed. Built on the Sprint 4 end state (`d9f1256`). Every zip holds **complete files at their repo paths** plus a `README_<name>.md`. Nothing has been committed or pushed.

Testers have a feature zip (merged mid-sprint) and a `-tests` zip (merged last). A `<Name>-2` zip means one person's work has to be split around someone else's (a migration or import order); its README says why.

## Merge order

Open the PRs **in this order** (each one after the previous merged, or rebased on it):

| # | Zip | Depends on | Branch | Stories | What | Lines |
|---|---|---|---|---|---|---|
| 1 | Keval | Sprint 4 end state | `us-51-us-58-authoring-ai` | US-51, US-58, US-45 | Lint engine and catalogue v2, pre-flight and AI wording logic, attribute extraction, suggestion prompts | 1,351 |
| 2 | Heet | Keval | `us-58-us-06-rule-checks` | US-58, US-06 | Attribute index and rule cross-checks, threshold preview and re-analysis | 1,569 |
| 3 | Madhav | Heet | `us-45-suggestions` | US-45 | AI suggestion service with append-only structured feedback | 1,885 |
| 4 | Abhijeet | Madhav | `us-38-notifications-backend` | US-38, US-14 | Notifications backend (service, hooks, subjects, API); graph service fixes and gateway tests | 1,031 |
| 5 | Parth | Abhijeet | `us-57-decision-rules` | US-57 | Decision rules engine and API | 1,564 |
| 6 | Affan | Parth | `us-57-decision-owners-ui` | US-57, US-06 | Decision owners, rules tab and the project settings page | 490 |
| 7 | Dhavni | Affan | `e-s5-load-test-inbox-ui` | CP2, US-38 | CP2 load test: messages, analysis, checks, the 500-node map; notifications bell and inbox UI | 720 |
| 8 | Pranshu | Dhavni | `us-40-us-51-baselines-authoring-api` | US-40, US-51 | Baseline snapshots and comparison (backend and UI); authoring-aids API: lint, pre-flight and wording routes | 1,460 |
| 9 | Abhyudit | Pranshu | `us-13-us-45-dashboard-panel` | US-13, US-45 | Quality dashboard (aggregation and UI) and the suggestion panel | 1,490 |
| 10 | Bansil | Abhyudit | `us-51-us-45-authoring-panel` | US-51, US-45 | Composer authoring panel; change requests and posts from accepted suggestions | 979 |
| 11 | Abhyudit-tests | Bansil | `e-s5-cp2-recall` | CP2 | Below-threshold set, recall by layer, suggestion rating study, CP2 report | 413 |
| 12 | Affan-tests | Abhyudit-tests | `e-s5-cp2-e2e` | CP2 | CP2 full-loop E2E from rule conflict to snapshot comparison | 242 |

**Migrations** (Parth reviews): 0010b (Heet) → 0008 (Madhav) → 0010c (Parth) — one head at every step.

## Files shipped by more than one zip

Each zip holds the version of the file as it stands after that zip, so the merge order matters.

| File | Shipped by (in order) |
|---|---|
| `backend/app/api/router.py` | Heet → Madhav → Abhijeet → Parth → Pranshu → Abhyudit |
| `backend/app/models/__init__.py` | Heet → Madhav → Abhijeet → Parth → Pranshu |
| `backend/app/models/analysis.py` | Heet → Parth |
| `backend/app/models/change_request.py` | Madhav → Parth |
| `backend/app/services/analysis_orchestrator.py` | Heet → Abhijeet |
| `backend/tests/api/test_access_invariants.py` | Abhijeet → Pranshu |
| `backend/tests/db/test_migrations.py` | Heet → Madhav → Parth |
| `backend/tests/permissions/test_matrix.py` | Heet → Madhav → Pranshu |
| `frontend/src/app/routes.tsx` | Dhavni → Abhyudit |
| `frontend/src/app/socket.ts` | Dhavni → Pranshu |
| `frontend/src/styles/components.css` | Dhavni → Pranshu |

## Files `main` changed after these zips were built

PR #57 (Sprint 2) and later fixes changed these on `main`. The zips hold complete files, so the person opening the PR merges `main`'s changes in by hand instead of overwriting:

- `backend/app/api/analysis_runs.py` (Keval)
- `backend/app/api/findings.py` (Parth)
- `backend/app/api/intake.py` (Bansil)
- `backend/app/api/requirements_compose.py` (Bansil)
- `backend/app/api/router.py` (Heet, Madhav, Abhijeet, Parth, Pranshu, Abhyudit)
- `backend/app/classification/result_card.py` (Keval)
- `backend/app/classification/tasks.py` (Heet)
- `backend/app/core/celery_app.py` (Madhav)
- `backend/app/core/config.py` (Pranshu)
- `backend/app/embeddings/candidates.py` (Heet)
- `backend/app/graph/api.py` (Abhijeet)
- `backend/app/graph/deltas.py` (Abhijeet)
- `backend/app/graph/service.py` (Abhijeet)
- `backend/app/intake/posts.py` (Bansil)
- `backend/app/lint/catalogue.json` (Keval)
- `backend/app/main.py` (Parth)
- `backend/app/models/__init__.py` (Heet, Madhav, Abhijeet, Parth, Pranshu)
- `backend/app/models/analysis.py` (Heet, Parth)
- `backend/app/models/enums.py` (Parth)
- `backend/app/models/project.py` (Madhav)
- `backend/app/realtime/events.py` (Madhav)
- `backend/app/realtime/gateway.py` (Madhav)
- `backend/app/schemas/findings.py` (Heet)
- `backend/app/services/analysis_orchestrator.py` (Heet, Abhijeet)
- `backend/app/services/findings.py` (Parth)
- `backend/app/services/lifecycle.py` (Parth)
- `backend/app/services/messages.py` (Abhijeet)
- `backend/app/services/review_state.py` (Parth)
- `backend/app/services/signup.py` (Abhijeet)
- `backend/tests/api/test_access_invariants.py` (Abhijeet, Pranshu)
- `backend/tests/api/test_auth.py` (Parth)
- `backend/tests/classification/test_lint_catalogue.py` (Pranshu)
- `backend/tests/core/test_tasks.py` (Abhyudit)
- `backend/tests/db/test_migrations.py` (Heet, Madhav, Parth)
- `backend/tests/embeddings/test_candidates.py` (Heet)
- `backend/tests/integration/test_upload_extract.py` (Abhyudit)
- `backend/tests/permissions/test_matrix.py` (Heet, Madhav, Pranshu)
- `backend/tests/realtime/test_gateway.py` (Abhijeet)
- `frontend/src/app/AppShell.tsx` (Dhavni)
- `frontend/src/app/routes.tsx` (Dhavni, Abhyudit)
- `frontend/src/app/socket.ts` (Dhavni, Pranshu)
- `frontend/src/features/composer/ComposerPage.tsx` (Bansil)
- `frontend/src/features/composer/PreviewPane.tsx` (Bansil)
- `frontend/src/features/composer/api.ts` (Bansil)
- `frontend/src/features/findings/FindingDrawer.tsx` (Abhyudit)
- `frontend/src/features/findings/FindingsPage.tsx` (Abhyudit)
- `frontend/src/features/findings/api.ts` (Abhyudit)
- `frontend/src/features/requirements/RequirementsTable.tsx` (Pranshu)
- `frontend/src/styles/components.css` (Dhavni, Pranshu)

## Verified

- Applying all zips in this order on `d9f1256` reproduces the Sprint 5 end state byte for byte.
- After **every** step: ruff, ruff format --check, mypy, a single Alembic head, pytest collection and the frontend typecheck pass (rcd-test image, Python 3.11).
