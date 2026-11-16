# Sprint 3 — how to apply these zips

Rebuilt for the **feature-wise ownership** in Sprint Plan §2.1: each zip is one owner's features, backend UI and tests together. The code is the same as before; only who ships which file changed. Built on the Sprint 2 end state (`68984d0`). Every zip holds **complete files at their repo paths** plus a `README_<name>.md`. Nothing has been committed or pushed.

Testers have a feature zip (merged mid-sprint) and a `-tests` zip (merged last). A `<Name>-2` zip means one person's work has to be split around someone else's (a migration or import order); its README says why.

## Merge order

Open the PRs **in this order** (each one after the previous merged, or rebased on it):

| # | Zip | Depends on | Branch | Stories | What | Lines |
|---|---|---|---|---|---|---|
| 1 | Heet | Sprint 2 end state | `us-31-retrieval-hints` | US-31 | Incremental retrieval and similar-requirement hints | 617 |
| 2 | Dhavni | Heet | `us-14-graph-deltas` | US-14 | Graph revisions, deltas, narrator, node positions, analysis cards in the thread | 1,630 |
| 3 | Abhyudit | Dhavni | `us-31-requirement-runs` | US-31 | Requirement runs: queue a posted requirement through retrieval and classification | 470 |
| 4 | Parth | Abhyudit | `us-37-lifecycle` | US-37 | Requirement lifecycle states and the review/lifecycle migration | 1,187 |
| 5 | Bansil | Parth | `us-36-ownership` | US-36 | Owners, stakeholder groups and ownership requests — backend and UI | 871 |
| 6 | Pranshu | Bansil | `us-30-composer` | US-30 | Requirement composer with EARS templates — backend and UI | 1,694 |
| 7 | Affan | Pranshu | `us-10-finding-review` | US-10 | Human review of findings with the protected guard — review state, API and UI | 1,231 |
| 8 | Keval | Affan | `us-31-classify-budget-card` | US-31 | Live classification, Redis budget guard, model provenance, result card — backend and UI | 1,319 |
| 9 | Madhav | Keval | `us-09-clarifications` | US-09 | Clarification questions, thread posts and answers | 1,157 |
| 10 | Abhijeet | Madhav | `us-14-map-ui` | US-14 | Live map UI: canvas, node drawer, table view, changes feed, live updates | 1,288 |
| 11 | Abhyudit-tests | Abhijeet | `e-s3-cp1-accuracy` | CP1 | CP1 accuracy report: post-style benchmark set, runner styles, with/without context pack | 331 |
| 12 | Affan-tests | Abhyudit-tests | `e-s3-cp1-e2e` | CP1 | CP1 end-to-end flow, map freshness load test, tenant isolation | 477 |

**Migrations** (Parth reviews): 0006d (Dhavni) → 0006e (Parth) → 0006f (Bansil) → 0006g (Keval) → 0006h (Madhav) — one head at every step.

## Files shipped by more than one zip

Each zip holds the version of the file as it stands after that zip, so the merge order matters.

| File | Shipped by (in order) |
|---|---|
| `backend/app/api/requirements.py` | Parth → Bansil |
| `backend/app/api/router.py` | Heet → Bansil → Pranshu → Keval → Madhav |
| `backend/app/core/config.py` | Heet → Keval |
| `backend/app/models/__init__.py` | Dhavni → Parth → Bansil → Affan |
| `backend/app/models/analysis.py` | Parth → Keval → Madhav |
| `backend/app/models/enums.py` | Parth → Bansil → Madhav |
| `backend/app/schemas/findings.py` | Affan → Keval → Madhav |
| `backend/app/schemas/requirements.py` | Parth → Bansil |
| `backend/app/services/analysis_orchestrator.py` | Abhyudit → Keval → Madhav |
| `backend/tests/permissions/test_matrix.py` | Heet → Dhavni → Parth → Bansil → Keval → Madhav |
| `frontend/src/app/routes.tsx` | Pranshu → Abhijeet |
| `frontend/src/app/socket.ts` | Pranshu → Abhijeet |
| `frontend/src/features/channels/MessageItem.tsx` | Dhavni → Keval |
| `frontend/src/styles/components.css` | Pranshu → Abhijeet |

## Files `main` changed after these zips were built

PR #57 (Sprint 2) and later fixes changed these on `main`. The zips hold complete files, so the person opening the PR merges `main`'s changes in by hand instead of overwriting:

- `.env.example` (Keval)
- `backend/app/classification/budget.py` (Keval)
- `backend/app/classification/llm_client.py` (Keval)
- `backend/app/classification/tasks.py` (Keval)
- `backend/app/core/config.py` (Heet, Keval)
- `backend/app/embeddings/candidates.py` (Heet)
- `backend/app/embeddings/store.py` (Heet)
- `backend/app/intake/posts.py` (Pranshu)
- `backend/tests/api/test_access_invariants.py` (Affan)
- `backend/tests/api/test_drafts.py` (Pranshu)
- `backend/tests/permissions/test_matrix.py` (Heet, Dhavni, Parth, Bansil, Keval, Madhav)
- `backend/tests/services/test_processing.py` (Bansil)
- `docs/contracts/realtime.md` (Dhavni)
- `eval/reports/s2.md` (Abhyudit-tests)
- `eval/run_benchmark.py` (Abhyudit-tests)
- `frontend/src/app/routes.tsx` (Pranshu, Abhijeet)
- `frontend/src/app/socket.ts` (Pranshu, Abhijeet)
- `frontend/src/features/findings/FindingCard.tsx` (Affan)
- `frontend/src/features/findings/FindingDrawer.tsx` (Affan)
- `frontend/src/features/findings/FindingsPage.tsx` (Affan)
- `frontend/src/features/findings/api.ts` (Affan)
- `frontend/src/features/requirements/RequirementsTable.tsx` (Bansil)
- `frontend/src/styles/components.css` (Pranshu, Abhijeet)

## Verified

- Applying all zips in this order on `68984d0` reproduces the Sprint 3 end state byte for byte.
- After **every** step: ruff, ruff format --check, mypy, a single Alembic head, pytest collection and the frontend typecheck pass (rcd-test image, Python 3.11).
