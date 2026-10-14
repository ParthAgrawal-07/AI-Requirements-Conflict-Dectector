# Deployment & DevOps

**Local Setup, Environment Config, and CI/CD**

| | |
|---|---|
| **Local** | Docker Compose v2 (`docker compose`, not legacy `docker-compose`) |
| **CI** | GitHub Actions: `backend-ci.yml`, `frontend-ci.yml` |
| **Backend deploy** | Railway / Render (planned, Sprint 5) |
| **Frontend deploy** | Vercel (planned, Sprint 5) |
| **Status** | Local setup and CI are live. Deployment is not set up yet |

---

## 1. Local Development Setup

```bash
git clone https://github.com/ParthAgrawal-07/AI-Requirements-Conflict-Dectector.git
cd AI-Requirements-Conflict-Dectector
cp .env.example .env          # fill in POSTGRES_PASSWORD, JWT_SECRET; LLM_API_KEY can wait until Sprint 2
make up                       # = docker compose up --build -d
make seed-demo                # one demo user per role (dev only), prints the password
```

Then open:
- Frontend: http://localhost:5173
- API docs (Swagger): http://localhost:8000/docs. Click **Authorize** and log in with a demo user.
- Readiness: http://localhost:8000/health/ready (checks Postgres and Redis)

`make help` lists every command. The most used:

| Command | What it does |
|---|---|
| `make up` / `make down` | Start everything in the background / stop it (data is kept) |
| `make logs` | Follow logs of every service |
| `make test` | Backend tests inside Docker, against the real db/redis |
| `make check` | Lint + typecheck + tests, the same as CI |
| `make makemigration m="add x"` | Autogenerate an Alembic migration from model changes |
| `make migrate` | Apply migrations to the running dev database |
| `make create-user email=… name="…" role=…` | Create a user (roles: analyst, admin, compliance_reviewer, read_only, service) |
| `make clean` | ⚠ Stop and **delete** volumes (db, redis, uploads) |

Optional: install the git hooks once with `pip install pre-commit && pre-commit install`. They run ruff (backend), YAML checks and private-key detection before every commit.

## 2. Docker Compose Topology

| Service | Image / build | Port | Notes |
|---|---|---|---|
| `db` | `pgvector/pgvector:pg16` | 5432 | Healthcheck-gated. Volume `pgdata` |
| `redis` | `redis:7-alpine` | 6379 | Celery broker/result backend. Volume `redisdata` |
| `migrate` | `./backend` | — | One-shot: `entrypoint.sh` waits for the db, runs `alembic upgrade head`, exits 0 |
| `backend` | `./backend` | 8000 | `uvicorn --reload`. Starts only after `migrate` succeeds |
| `worker` | `./backend` | — | `celery -A app.core.celery_app worker`. Shares the `uploads` volume with `backend` |
| `frontend` | `./frontend` | 5173 | Vite dev server |

Each port can be overridden in `.env` (`POSTGRES_PORT`, `REDIS_PORT`, `BACKEND_PORT`, `FRONTEND_PORT`) if it clashes with something already running on your machine.

## 3. Environment Configuration

`.env.example` is the commented, complete list; `backend/app/core/config.py` validates it at startup. Key variables:

| Variable | Purpose |
|---|---|
| `ENVIRONMENT` | `development` / `test` / `staging` / `production`. Staging and production refuse to start with a weak `JWT_SECRET` or a wildcard CORS origin |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | Used by the `db` container. Never committed (GitGuardian secret scanning is configured in `.gitguardian.yaml`) |
| `DATABASE_URL` / `REDIS_URL` | Connection strings for the app and worker |
| `JWT_SECRET` / `ACCESS_TOKEN_EXPIRE_MINUTES` | Token signing key (FR-37, NFR-12) / lifetime, default 60 |
| `CORS_ALLOWED_ORIGINS` | Frontend origins allowed to call the API |
| `MAX_UPLOAD_SIZE_MB` / `UPLOAD_DIR` | Upload cap, default 25 (CR-16) / where uploads are stored |
| `SIMILARITY_THRESHOLD_DEFAULT` | Default pre-filter threshold (FR-10). Each workspace can override it in the database |
| `LLM_PROVIDER` / `LLM_API_KEY` | `anthropic` or `openai`. The key stays server-side (NFR-12) |
| `VITE_API_BASE_URL` | API base URL the frontend calls |

## 4. CI (GitHub Actions)

Each workflow runs only when its own folder changes, on pushes and pull requests.

**Backend** (`backend/**`): `lint-and-typecheck` (ruff check, ruff format --check, mypy) → `test` (pytest + coverage against pgvector and Redis service containers, plus a check that there is exactly one Alembic head). In parallel: `security-audit` (pip-audit, which warns but doesn't fail the build) and `docker-build`.

**Frontend** (`frontend/**`): `lint-and-typecheck` (eslint, tsc) → `test` (vitest). In parallel: `docker-build`.

Known gotchas:
- CI and the frontend Dockerfile delete `package-lock.json` before `npm install`, because the committed lockfile was generated on Windows (npm/cli#4828). Dependency ranges are therefore re-resolved on every build, so keep them tight.
- CI runs Node 18 and the frontend Dockerfile uses Node 20. Any dev dependency whose `engines` requires a newer Node will still install, but it is unsupported (see the PR #17 review).

## 5. Deployment (Planned, Sprint 5)

- On merge to `main`: run the full suite, then deploy the backend to Railway/Render and the frontend to Vercel.
- Migrations run automatically as a deploy step (the same `entrypoint.sh` used locally).
- Integration checkpoints (Week 7, Week 11) are tagged releases, so reviewers can be pointed at a known-good state.
- NFR-23: production uses the same container images as local development.

## 6. Production Considerations (NFR-08, NFR-09, NFR-14)

- Target uptime 99.5% (NFR-08).
- Automated backup and recovery for requirement data and audit logs (NFR-09). Not implemented yet; recommended before Sprint 5 hardening.
- Data residency and GDPR/HIPAA-style compliance (NFR-14) are acknowledged in the requirements, but are not needed for the semester deployment.
