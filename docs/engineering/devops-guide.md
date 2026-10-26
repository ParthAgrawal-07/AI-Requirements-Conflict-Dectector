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

No account exists after a fresh `docker compose up` — there is deliberately no open sign-up
(IT/DevOps stakeholder requirement: nobody can register without a join code). Create the first
**platform administrator** (the only thing the CLI creates in production), who then creates a
workspace and issues join codes:

```bash
make create-admin email=you@example.com name="Your Name"   # prompts for the password
# development only — a demo workspace with one member per default role, prints the password:
make seed-demo
```

By default only platform administrators can create workspaces; set `ALLOW_USER_WORKSPACE_CREATION=true`
to let any signed-in user do so. Join-code sign-up is limited to `SIGNUP_ATTEMPTS_PER_MINUTE` (default 5)
attempts per IP address and per e-mail address; behind a reverse proxy set **`TRUSTED_PROXY_HOPS`**
to the number of proxies in front of the API (Render: `1`), otherwise every client shares one address and sign-up
is limited to that many attempts per minute *globally*. The limit is kept in Redis; if Redis is unreachable it
degrades to a per-process counter (and logs a warning) rather than blocking sign-up. `make seed-demo` only runs when
`ENVIRONMENT` is `development` or `test` — never in staging or production, where its accounts would have a published
password. Before deploying a migration that changes data (such as `0004`), rehearse it on a copy of the real
database: see [`migration-runbook.md`](migration-runbook.md).

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
| `LLM_PROVIDER` / `LLM_FALLBACK_PROVIDER` | `gemini` / `groq` (ADR-31, [`ai-providers.md`](ai-providers.md) §5) |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | Google Gemini API key and model — never exposed client-side (NFR-12) |
| `GROQ_API_KEY`, `GROQ_MODEL` | Groq API key and model, used only when Gemini is unavailable |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` (local; downloaded once per container) |
| `SIMILARITY_THRESHOLD_DEFAULT` | Default embedding pre-filter threshold (FR-10), overridable per workspace |
| `CORS_ALLOWED_ORIGINS` | Comma-separated frontend origin(s) allowed to call the API |
| `MAX_UPLOAD_SIZE_MB` | Upload size cap enforced at the API (FR-02), default 25 |

See [`.env.example`](../../.env.example) for the complete, commented list.

## 3. Docker Compose Topology (Planned)

See [`docker-compose.yml`](../../docker-compose.yml) for the actual, implemented topology
(six services: `db`, `redis`, `migrate`, `backend`, `worker`, `frontend`).

NFR-23 requires the system to run identically in local development and production via this same Docker Compose / containerized definition.

### Uploaded files and the shared volume

`POST /projects/{p}/documents` saves the file under `UPLOAD_DIR` (`/data/uploads`) and the **Celery worker reads it from
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

Owners follow [`IT314_RCD_Sprint_Plan_v5.md` §2](../planning/v5/IT314_RCD_Sprint_Plan_v5.md#2-team-and-areas-of-ownership); `.github/CODEOWNERS` enforces review.

```
backend/
  app/ingestion/       # Bansil — parsing and segmentation (implemented)
  app/context/         # Bansil — project context, brief drafter, context gate (implemented)
  app/intake/          # Bansil — EARS templates, composer schemas; posts and drafts later
  app/embeddings/      # Heet
  app/classification/  # Keval
  app/clarification/   # Madhav
  app/core/            # Parth — settings, db, security, auth, permissions, celery, errors, middleware
  app/api/             # Parth — routes; each area's routes are reviewed by its owner
  app/models/          # Parth — SQLAlchemy models for every table
  app/schemas/         # Parth — Pydantic request/response schemas
  app/services/        # Parth — business logic (routes stay thin)
  alembic/             # Parth — migrations 0001–0004a, 0011 implemented
  tests/               # Every owner adds tests for their package; Abhyudit owns integration tests
frontend/
  src/                 # Pranshu (shell, composer, requirements, …), Abhijeet (members, setup, findings, map, …)
docs/
  engineering/         # this document set
  planning/v5/         # revision 5 planning documents (source of truth)
  contracts/           # Sprint 0 interface contracts
  wireframes/          # screen wireframes
sample_docs/           # planted-conflict benchmark SRS and labels
.env.example           # implemented
docker-compose.yml     # implemented — db, redis, migrate, backend, worker, frontend
Makefile               # implemented — `make help` for day-to-day commands
```

Planned directories (`app/realtime/`, `app/graph/`, `app/lint/`, `app/consequences/`, `app/suggestions/`, `app/notifications/`, `app/export/`, `app/search/`, `eval/`, `e2e/`, `load/`) are created by their owners when their sprint starts; see `architecture.md` §2.
