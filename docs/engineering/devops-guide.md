# Deployment & DevOps

**Local Setup, Environment Config, and CI/CD**

| | |
|---|---|
| **Local** | Docker Compose |
| **Backend deploy** | Railway / Render |
| **Frontend deploy** | Vercel |
| **CI/CD** | GitHub Actions |
| **Status** | Planned — docker-compose.yml, .env.example, and CI workflows not yet created |

---

## 1. Local Development Setup (Planned)

```bash
git clone <repo>
cd ai-requirements-conflict-detector
cp .env.example .env          # fill in DB creds, LLM API key
docker compose up --build

# Services started:
#   backend   -> FastAPI on :8000
#   frontend  -> Vite dev server on :5173
#   db        -> Postgres + pgvector on :5432
#   redis     -> Redis on :6379
#   worker    -> Celery worker (consumes Redis queue)
```

## 2. Environment Configuration

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Postgres connection string (pgvector-enabled instance) |
| `REDIS_URL` | Celery broker/result backend |
| `JWT_SECRET` | Signing key for auth tokens (FR-37) — never committed (NFR-12) |
| `LLM_API_KEY` | Anthropic Claude API / OpenAI API key — never exposed client-side (NFR-12) |
| `SIMILARITY_THRESHOLD_DEFAULT` | Default embedding pre-filter threshold (FR-10), overridable per workspace |
| `CORS_ALLOWED_ORIGINS` | Frontend origin(s) allowed to call the API |

*`.env.example` is referenced in the repo plan but not yet created — a Sprint 0 task (see `task-breakdown.md`, T01).*

## 3. Docker Compose Topology (Planned)

```yaml
services:
  backend:   builds ./backend, depends_on [db, redis]
  worker:    builds ./backend, runs "celery -A app worker", depends_on [db, redis]
  frontend:  builds ./frontend, depends_on [backend]
  db:        image: pgvector/pgvector:pg16
  redis:     image: redis:7
```

NFR-23 requires the system to run identically in local development and production via this same Docker Compose / containerized definition.

## 4. CI/CD Pipeline (GitHub Actions, Planned)

- On every pull request: run Pytest (backend) and Vitest (frontend), lint, and build both images.
- On merge to main: run the full test suite, then deploy backend to Railway/Render and frontend to Vercel.
- Alembic migrations run automatically against the target environment as a deploy step, not manually.
- Integration-checkpoint builds (Week 7, Week 11) are tagged releases so the team can point graders/reviewers at a known-good deployed state.

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
  app/core/            # Role 5
  alembic/             # migrations — not yet created
frontend/
  src/components/      # Role 6 (core), Role 7 (graph/)
docs/
  engineering/         # this document set
.env.example           # not yet created
docker-compose.yml
```
