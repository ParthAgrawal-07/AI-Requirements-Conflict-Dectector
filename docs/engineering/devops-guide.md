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
| `REFRESH_TOKEN_EXPIRE_DAYS` | How long a session may stay idle before signing in again (rotating refresh cookie, US-19), default 14 |
| `REFRESH_COOKIE_SAMESITE` | `lax` (default: SPA and API on one site, e.g. localhost) or `none` when they are on different sites (e.g. Vercel + Render); `none` requires `Secure` |
| `REFRESH_COOKIE_SECURE` | Unset = `Secure` everywhere except development/test |
| `LLM_PROVIDER` / `LLM_FALLBACK_PROVIDER` | `gemini` / `groq` (ADR-31, [`ai-providers.md`](ai-providers.md) §5) |
| `LLM_OUTPUT_RETRIES` | Re-asks after a reply fails schema validation before the pair is marked failed (US-05), default 3 |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | Google Gemini API key and model — never exposed client-side (NFR-12) |
| `GROQ_API_KEY`, `GROQ_MODEL` | Groq API key and model, used only when Gemini is unavailable |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` (local; downloaded once per container) |
| `SIMILARITY_THRESHOLD_DEFAULT` | Default embedding pre-filter threshold (FR-10), overridable per workspace |
| `CANDIDATE_TOP_K` | Nearest neighbours per requirement kept as candidate pairs (US-05), default 10, range 1–50 |
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

### Single-host production (Azure VM)

`docker-compose.prod.yml` layers over `docker-compose.yml` for one host. It builds the backend without dev tools, drops the
source bind mounts and `--reload`, stops publishing Postgres and Redis, and replaces the Vite dev server with the built
SPA served by **Caddy** (`frontend/Dockerfile` target `prod`, config in `Caddyfile`). Caddy gets the Let's Encrypt
certificate and proxies `/api/*`, `/ws` and `/health` to `backend:8000`, so the SPA and the API share one origin and
the refresh cookie stays `SameSite=lax`. All services share one disk, so the `uploads` volume works unchanged.

1. Create an Ubuntu VM (`Standard_B2ms`, 8 GB, which leaves room for PyTorch, the embedding model and Postgres) with a
   public DNS label, and open ports 80 and 443. Install Docker (Compose >= 2.24.4).
2. Clone the repo and write `.env` with `ENVIRONMENT=production`, a fresh `JWT_SECRET` and `JOIN_CODE_PEPPER`, a strong
   `POSTGRES_PASSWORD` (also in `DATABASE_URL`), `SITE_ADDRESS=<host>`, `VITE_API_BASE_URL=https://<host>`,
   `CORS_ALLOWED_ORIGINS=https://<host>`, `TRUSTED_PROXY_HOPS=1` (Caddy) and the Gemini/Groq keys.
3. `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build`. The `migrate` service applies
   migrations first, as in development.
4. Create the first administrator:
   `docker compose -f docker-compose.yml -f docker-compose.prod.yml exec backend python -m app.cli create-admin --email … --name …`.

**Continuous deployment.** `.github/workflows/deploy-azure.yml` deploys every push to `main` (and runs on demand via
*Run workflow*). It connects to the VM over SSH, resets `~/rcd` (a clone of this repo) to the pushed commit, and runs the
same `up -d --build`. It then waits for `/health/ready`. It needs the repository secrets `VM_HOST`, `VM_USER`,
`VM_SSH_KEY` and `VM_KNOWN_HOSTS` (see the workflow header). `.env` and the Docker volumes live only on the VM.

`VITE_API_BASE_URL` is compiled into the bundle, so changing the host means rebuilding `frontend`. Back up with
`pg_dump` or a disk snapshot. Postgres lives on the VM's disk, so nothing else backs it up.

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
