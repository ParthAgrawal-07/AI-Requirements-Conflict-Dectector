# Sprint 4 — how to apply these zips

Rebuilt for the **feature-wise ownership** in Sprint Plan §2.1: each zip is one owner's features, backend UI and tests together. The code is the same as before; only who ships which file changed. Built on the Sprint 3 end state (`bc4e851`). Every zip holds **complete files at their repo paths** plus a `README_<name>.md`. Nothing has been committed or pushed.

Testers have a feature zip (merged mid-sprint) and a `-tests` zip (merged last). A `<Name>-2` zip means one person's work has to be split around someone else's (a migration or import order); its README says why.

## Merge order

Open the PRs **in this order** (each one after the previous merged, or rebased on it):

| # | Zip | Depends on | Branch | Stories | What | Lines |
|---|---|---|---|---|---|---|
| 1 | Dhavni | Sprint 3 end state | `us-52-auto-issues` | US-52 | Requirement issues and automatic conflict issues for two owners; issues client | 1,493 |
| 2 | Heet | Dhavni | `us-11-impact-relations` | US-11, US-33 | Impact analysis with one- and two-hop relationship queries; change-request API client | 958 |
| 3 | Bansil | Heet | `us-33-change-editor` | US-33 | Change-request intake with base version, change editor and diff view | 1,561 |
| 4 | Abhyudit | Bansil | `us-56-raise-concern` | US-56 | Raise a concern (human-raised findings), AI-miss flag — backend and UI | 752 |
| 5 | Madhav | Abhyudit | `us-34-consequence-checks` | US-34 | Consequence checks, findings delta, risk, reports and the Checks tab | 1,681 |
| 6 | Keval | Madhav | `us-34-narrative` | US-34 | AI narrative of the consequence report, held to the checks; result-card source badges | 455 |
| 7 | Heet-2 | Keval | `us-35-reviews` | US-35 | Reviews and review requests, the reviews migration and the Reviews tab | 766 |
| 8 | Parth | Heet-2 | `us-35-merge` | US-35 | Merge, needs-update and the agreement guard | 1,340 |
| 9 | Affan | Parth | `us-12-us-35-history-merge-box` | US-12, US-35 | Version history (backend and UI) and the merge box | 434 |
| 10 | Abhijeet | Affan | `us-52-issue-pages` | US-52 | Issue API, list, page and comments | 1,363 |
| 11 | Pranshu | Abhijeet | `us-33-change-request-page` | US-33 | Change-request list and page | 813 |
| 12 | Abhyudit-tests | Pranshu | `e-s4-affected-sets` | S4 testing | Scripted change requests: affected sets, findings delta, auto-issue owners | 394 |
| 13 | Affan-tests | Abhyudit-tests | `e-s4-merge-rules` | S4 testing | Merge-rule security tests and the change-request E2E | 664 |

**Migrations** (Parth reviews): 0007 (Dhavni) → 0007a (Bansil) → 0010a (Abhyudit) → 0007b (Madhav) → 0007c (Heet) — one head at every step.

## Files shipped by more than one zip

Each zip holds the version of the file as it stands after that zip, so the merge order matters.

| File | Shipped by (in order) |
|---|---|
| `backend/app/api/change_requests.py` | Bansil → Parth |
| `backend/app/api/router.py` | Bansil → Abhyudit → Madhav → Abhijeet |
| `backend/app/consequences/tasks.py` | Madhav → Keval |
| `backend/app/graph/narrator.py` | Dhavni → Bansil → Parth |
| `backend/app/graph/schemas.py` | Dhavni → Abhyudit |
| `backend/app/graph/service.py` | Dhavni → Abhyudit |
| `backend/app/intake/change_intake.py` | Bansil → Madhav → Parth |
| `backend/app/models/__init__.py` | Dhavni → Bansil → Madhav → Heet-2 → Parth |
| `backend/app/models/enums.py` | Dhavni → Bansil → Heet-2 |
| `backend/app/realtime/events.py` | Dhavni → Bansil → Madhav → Parth |
| `backend/tests/api/test_review_merge.py` | Parth → Affan-tests |
| `backend/tests/consequences/test_consequences.py` | Madhav → Keval |
| `backend/tests/db/test_migrations.py` | Dhavni → Bansil → Madhav → Parth |
| `backend/tests/permissions/test_matrix.py` | Dhavni → Bansil → Madhav → Parth |
| `frontend/src/app/routes.tsx` | Bansil → Abhijeet → Pranshu |
| `frontend/src/app/socket.ts` | Abhijeet → Pranshu |
| `frontend/src/styles/components.css` | Abhijeet → Pranshu |

## Files `main` changed after these zips were built

PR #57 (Sprint 2) and later fixes changed these on `main`. The zips hold complete files, so the person opening the PR merges `main`'s changes in by hand instead of overwriting:

- `backend/app/classification/tasks.py` (Abhyudit)
- `backend/tests/db/test_migrations.py` (Dhavni, Bansil, Madhav, Parth)
- `backend/tests/permissions/test_matrix.py` (Dhavni, Bansil, Madhav, Parth)
- `docs/contracts/realtime.md` (Dhavni)
- `eval/benchmark_v2/schema.json` (Abhyudit-tests)
- `frontend/src/api/client.ts` (Affan)
- `frontend/src/app/routes.tsx` (Bansil, Abhijeet, Pranshu)
- `frontend/src/app/socket.ts` (Abhijeet, Pranshu)
- `frontend/src/features/findings/api.ts` (Abhyudit)
- `frontend/src/features/requirements/RequirementsTable.tsx` (Affan)
- `frontend/src/styles/components.css` (Abhijeet, Pranshu)
- `frontend/tests/api-client.test.ts` (Pranshu)

## Verified

- Applying all zips in this order on `bc4e851` reproduces the Sprint 4 end state byte for byte.
- After **every** step: ruff, ruff format --check, mypy, a single Alembic head, pytest collection and the frontend typecheck pass (rcd-test image, Python 3.11).
