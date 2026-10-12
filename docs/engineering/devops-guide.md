# Deployment & DevOps

**Local Setup, Environment Config, and CI/CD**

| | |
|---|---|
| **Local** | Docker Compose |
| **Backend deploy** | Railway / Render |
| **Frontend deploy** | Vercel |
| **CI/CD** | GitHub Actions |
| **Status** | Sprint 0 (Parth): docker-compose.yml, both Dockerfiles, .env.example, DB schema + migrations, auth skeleton, and backend-ci.yml are implemented and passing. Frontend build/deploy steps are still Sprint 5 (Dhavni didi). |

---

## 1. Local Development Setup

```bash
git clone <repo>
cd ai-requirements-conflict-detector
cp .env.example .env          # fill in DB creds, LLM API key
docker compose up --build

# Services started:
#   db        -> Postgres + pgvector on :5432
#   redis     -> Redis on :6379
#   migrate   -> runs `alembic upgrade head` once, then exits 0
#   backend   -> FastAPI on :8000 (waits for migrate to finish)
#   worker    -> Celery worker consuming the Redis queue (waits for migrate to finish)
#   frontend  -> Vite dev server on :5173
```

Requires **Docker Compose v2** (the `docker compose` plugin bundled with current Docker
Desktop / Docker Engine) — the legacy standalone `docker-compose` v1 binary doesn't support
the `condition: service_completed_successfully` dependency used by the `migrate` service.

No superuser account exists yet after a fresh `docker compose up` — there is deliberately no
public sign-up endpoint (IT/DevOps stakeholder requirement: accounts are provisioned, not
self-registered). Create one:

```bash
make seed-demo                      # one demo user per role, dev-only, prints the password
# or
make create-user email=you@example.com name="Your Name" role=admin
```

See the root `Makefile` (`make help`) for the rest of the day-to-day commands (logs, test,
lint, typecheck, migrations).

## 2. Environment Configuration

| Variable | Purpose |
|---|---|
| `ENVIRONMENT` | `development` / `test` / `staging` / `production` — staging/production enforce a strong `JWT_SECRET` and an explicit CORS list at startup |
| `DATABASE_URL` | Postgres connection string (pgvector-enabled instance) |
| `REDIS_URL` | Celery broker/result backend |
| `JWT_SECRET` | Signing key for auth tokens (FR-37) — never committed (NFR-12) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | JWT lifetime, default 60 |
| `LLM_API_KEY` | Anthropic Claude API / OpenAI API key — never exposed client-side (NFR-12) |
| `SIMILARITY_THRESHOLD_DEFAULT` | Default embedding pre-filter threshold (FR-10), overridable per workspace |
| `CORS_ALLOWED_ORIGINS` | Comma-separated frontend origin(s) allowed to call the API |
| `MAX_UPLOAD_SIZE_MB` | Upload size cap enforced at the API (FR-02), default 25 |

See [`.env.example`](../../.env.example) for the complete, commented list.

## 3. Docker Compose Topology (Planned)

See [`docker-compose.yml`](../../docker-compose.yml) for the actual, implemented topology
(six services: `db`, `redis`, `migrate`, `backend`, `worker`, `frontend`).

NFR-23 requires the system to run identically in local development and production via this same Docker Compose / containerized definition.

### Uploaded files and the shared volume

`POST /documents` saves the file under `UPLOAD_DIR` (`/data/uploads`) and the **Celery worker reads it from
there**, so `backend` and `worker` must see the same directory — in Compose that is the shared `uploads`
volume. If they don't, documents end `failed` with a `[storage]` message saying so. On Railway/Render, where
container disks are private and ephemeral, deploying API and worker as separate services needs either one
shared volume or S3-compatible object storage; `app/services/storage.py` is the single place to swap
(Sprint 5 deployment task).

## 4. CI/CD Pipeline (GitHub Actions)

- **Implemented (`backend-ci.yml`)**, on every push/PR touching `backend/`: ruff (lint +
  format check), mypy, pytest against real Postgres+pgvector and Redis service containers
  (not mocks — see `tests/conftest.py`), a check that Alembic has exactly one migration head,
  a `pip-audit` dependency scan (report-only for now), and a Docker build check.
- **Not yet implemented:** `frontend-ci.yml` currently runs against the Sprint 0 frontend
  stub only; deploy-on-merge to Railway/Render (backend) and Vercel (frontend) is Sprint 5
  (Dhavni didi / Parth, see `Sprint_Work_Assignment`).
- Alembic migrations run automatically as a deploy step (the `migrate` service / container
  entrypoint), never applied by hand against a shared environment.
- Integration-checkpoint builds (Week 7, Week 11) are tagged releases so the team can point
  graders/reviewers at a known-good deployed state.

## 5. Production Considerations (NFR-08, NFR-09, NFR-23)

- Target uptime: 99.5%, consistent with IT/DevOps support expectations (NFR-08).
- Automated backup and recovery for requirement data and audit logs (NFR-09) — not yet implemented; recommended before Sprint 5 hardening.
- Data residency / regulatory compliance (NFR-14, GDPR/HIPAA-style) is acknowledged in requirements but not required for the semester deployment target — flagged for the industry-extension picture only.

## 6. Repo Structure Reference

```
backend/
  app/ingestion/       # Role 1
  app/embeddings/      # Role 2
  app/classification/  # Role 3
  app/clarification/   # Role 4
  app/core/            # Role 5 — settings, db, security, auth, celery, errors, middleware
  app/api/             # Role 5 — routes (auth implemented; documents/requirements/
                       #   findings/reports are Sprint 1+ stubs owned by their roles)
  app/models/          # Role 5 — SQLAlchemy models for every table
  app/schemas/         # Role 5 — Pydantic request/response schemas
  app/services/        # Role 5 — business logic (routes stay thin)
  alembic/             # migrations — implemented (0001_initial_schema)
  tests/               # Role 5's own tests; each role adds tests alongside its own package
frontend/
  src/components/      # Role 6 (core), Role 7 (graph/)
docs/
  engineering/         # this document set
.env.example           # implemented
docker-compose.yml     # implemented — db, redis, migrate, backend, worker, frontend
Makefile               # implemented — `make help` for day-to-day commands
```

> **Note on role numbering:** this file and `task-breakdown.md` use the original 7-role
> split (T02 "DB schema" → Role 2, T03 "Docker Compose" → Role 7). The team's later
> `Sprint_Work_Assignment` reassigns Sprint 0 infra (DB schema, Docker Compose, CI, auth
> skeleton) to Parth under Role 5, which is what was actually built here. This is the same
> kind of numbering drift already tracked for FR/NFR/DR in `requirements-spec.md` — not yet
> reconciled into one canonical assignment, flagged here rather than silently overwritten.
