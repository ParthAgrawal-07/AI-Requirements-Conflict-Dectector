# Sprint 2 — how to apply these zips

Built on the **Sprint 1 end state**: `main` at `daf4f18` plus every Sprint 0–1 zip applied in its own merge order (and
the four branches its `MERGE_ORDER.md` lists). **Merge all Sprint 0–1 PRs first.** Every zip holds **complete files at
their repo paths** plus a `README_<name>.md`, from the Detailed Sprint Guide in `docs/planning/v5/`. Nothing has been
committed or pushed to GitHub.

## Merge order

Each zip contains *that person's* version of the files shared with earlier zips, so **open the PRs in this order** (or
rebase onto the previous one):

| # | Zip | Depends on | Branch to open | Stories |
|---|---|---|---|---|
| 1 | Madhav | Sprint 1 end state | `us-28-channels` | US-28; clarification prompt draft |
| 2 | Parth-1 | Madhav | `us-26-us-49-members-roles` | US-26, US-49; G1 |
| 3 | Dhavni | Parth-1 | `us-29-messages` | US-29; graph API v0 |
| 4 | Bansil | Dhavni | `e-s2-drafts-posts-g3` | drafts, requirement posts, G3 |
| 5 | Heet | Bansil | `us-05-candidates` | US-05 (candidates) |
| 6 | Keval | Heet | `us-05-us-07-classification` | US-05 (5a–5c), US-07 |
| 7 | Parth-2 | Keval | `e-s2-analysis-orchestrator` | orchestration |
| 8 | Abhyudit | Parth-2 | `e-s2-benchmark-run` | US-05 accuracy, US-22 kit |
| 9 | Affan | Abhyudit | `e-s2-ws-custom-role-tests` | WebSocket and custom-role tests |
| 10 | Pranshu | backend #1–#3 | `us-28-us-29-channels-ui` | US-28, US-29 UI |
| 11 | Abhijeet | Pranshu, backend #6 | `us-07-us-26-us-49-ui` | US-07, US-26, US-49 UI; US-22 prototype |

**Migrations** (Parth reviews): `0011 → 0005 → 0005b (Madhav) → 0006 (Parth-1) → 0006b (Bansil) → 0006c (Keval)` —
one head at every step, up and down tested.

## Files shared between zips

| File | Changed by (in order) |
|---|---|
| `backend/tests/permissions/test_matrix.py` | Madhav → Parth-1 → Dhavni → Bansil → Keval → Affan (each adds the `Case`s for its routes) |
| `backend/tests/api/test_access_invariants.py` | Madhav → Parth-1 → Bansil |
| `backend/tests/db/test_migrations.py` | Madhav → Bansil |
| `backend/app/api/router.py` | Madhav → Parth-1 → Dhavni → Bansil → Keval |
| `backend/app/realtime/events.py` | Madhav → Parth-1 → Dhavni → Parth-2 |
| `backend/app/models/__init__.py`, `enums.py` | Madhav → Parth-1 → Bansil |
| `backend/app/models/analysis.py` | Parth-1 → Keval |
| `backend/app/models/requirement.py` | Bansil → Keval |
| `backend/app/core/config.py` | Dhavni → Heet → Keval |
| `frontend/src/app/AppShell.tsx`, `routes.tsx`, `styles/components.css` | Pranshu → Abhijeet |

Small edits in files owned by someone else (please review): `app/services/projects.py` (Madhav: `#general` on project
creation), `app/context/service.py` (Keval: open findings by project), `app/api/context.py` (Parth-2: analyse on
activation), `app/services/processing.py` (Bansil: G3).

## Applying a zip

1. `git switch main && git pull && git switch -c <branch>` (after the earlier PRs merged).
2. Unzip at the repo root, overwriting. Delete the files listed under **Delete** in the README, if any (only Heet's).
3. Backend: `cd backend && ruff check . && ruff format --check . && mypy app && pytest`.
   Frontend: `cd frontend && npm install && npm run typecheck && npm run lint && npm run test:run`.
4. Open the PR with the README's summary as the description.

`frontend/package-lock.json` is deliberately not included (regenerated on install).

## Verification done before handing over

* Backend, at **every** stage in the order above, on Python 3.11 + PostgreSQL 16/pgvector + Redis 7: ruff, ruff
  format, mypy and the full pytest suite. Final state: **1,786 passed**, no expected failures left.
* Frontend at Pranshu's stage (**46** tests) and at the final stage (**56** tests): `tsc`, ESLint, Vitest and
  `vite build`.
* The benchmark's candidate stage with the real embedding model (numbers in `eval/reports/s2.md`).
* **Not done:** a classification run with a real LLM (no API key was used), the usability sessions, and a browser
  run of the full stack — do these in the sprint review rehearsal.

## Sprint 2 exit criteria

| Criterion | Where |
|---|---|
| Findings with confidence on the planted SRS | engine and UI ready (Keval, Parth-2, Abhijeet); needs `LLM_API_KEY` for real findings |
| First precision/recall numbers | candidate recall measured; per-category table waits for the LLM run (`eval/reports/s2.md`) |
| Two browsers chat in real time | `tests/realtime/test_gateway_channels.py::test_two_members_chat_live` + Pranshu's UI |
| A custom role "Client reviewer" can review but not propose | `tests/api/test_roles.py`, `tests/permissions/test_matrix.py` |

## Corrections after the Sprint 0–5 review

* `Parth-2.zip` now also ships `backend/tests/core/test_tasks.py` (without it the PR fails CI on main).
* `Bansil.zip` ships a merged `backend/tests/integration/test_upload_extract.py` (it no longer
  reverts main's reviewed version).

Details in each README. No other file changed.
