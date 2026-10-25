# Sprint 0–1 catch-up — how to apply these zips

Prepared against `main` at `daf4f18` (24 Oct 2026), from the Sprint Work Assignment and the Detailed Sprint Guide in
`docs/planning/v5/`. Every zip holds **complete files at their repo paths** plus a `README_<name>.md`. Nothing has been
committed or pushed to GitHub.

## Merge order

Some files are touched by more than one person (listed below). Each zip contains *that person's* version of them, built
on top of everyone earlier in this list, so **open the PRs in this order** (or rebase onto the previous one):

| # | Zip | Depends on | Branch to open (guide convention) |
|---|---|---|---|
| 0 | Bansil | — (report only, no files to change) | — |
| 1 | Parth | `main` | `e-s1-roles-list` |
| 2 | Madhav | Parth | `us-25-join-codes` |
| 3 | Dhavni | Madhav | `us-03-progress-realtime` |
| 4 | Heet | Dhavni | `e-s1-embedding-stage` |
| 5 | Keval | Heet | `e-s1-llm-client-context-pack` |
| 6 | Abhyudit | Keval | `e-s1-benchmark-v2` |
| 7 | Affan (backend part) | Abhyudit | `us-27-permission-tests` |
| 8 | Pranshu | `main` (frontend only) | `us-19-us-04-frontend` |
| 9 | Abhijeet | Pranshu | `us-24-us-25-us-60-ui` |
| 10 | Affan (E2E part) | everything above | `e-s1-e2e` |

Before #2, these unmerged branches must be **closed, not merged** — their work is in the zips, ported to `main`:
`feat/madhav-sprint1-join-codes` (conflicts with `main` in 8 files; see Madhav's README). These were merged into the
base the zips were built on and still need their own PRs first, as they are: `feat/keval-sprint0-classification-prompts`,
`sprint-0-frontend-testing` (Affan), `eval/abhyudit-sprint0-benchmark-v2-plan`, `eval/abhyudit-sprint0-srs-v1-review`.
They merge into `main` cleanly.

## Files shared between zips

| File | Changed by (in order) |
|---|---|
| `backend/app/core/config.py` | Madhav → Dhavni → Keval |
| `backend/app/core/celery_app.py` | Madhav → Dhavni |
| `backend/app/core/tasks.py` | Madhav → Heet |
| `.env.example` | Madhav → Keval |
| `frontend/src/app/routes.tsx`, `frontend/package.json` | Pranshu → Abhijeet |

## Applying a zip

1. `git switch main && git pull && git switch -c <branch>` (after the earlier PRs merged).
2. Unzip at the repo root, overwriting. Delete the files listed under **Delete** in the README, if any.
3. Backend: `cd backend && ruff check . && ruff format --check . && mypy app && pytest`.
   Frontend: `cd frontend && npm install && npm run typecheck && npm run lint && npm run test:run`.
4. Open the PR with the README's summary as the description.

`frontend/package-lock.json` is deliberately not included (it is regenerated on install; CI deletes it anyway).

## Verification done before handing over

* Backend, every stage in the order above, on Python 3.11 + PostgreSQL 16/pgvector + Redis 7: ruff, ruff format,
  mypy and the full pytest suite. Final state: **1,233 passed, 1 expected failure** (a Sprint 2 tracker, see Abhyudit).
* Frontend at Pranshu's stage and at the final stage: `tsc`, ESLint and Vitest (27 and 36 tests), plus `vite build`.
* Full Docker stack (PostgreSQL, Redis, API, Celery worker, Vite): migrations `0001`→`0005` on an empty database,
  `seed-demo`, then the Sprint 1 exit flow both over the API and in a browser — Playwright **5/5 passed**: PM creates
  a code → a new user signs up with it as Developer → uploads the planted SRS → extraction and embedding run in the
  worker → REQ-014 is listed → the code shows 1 use.
