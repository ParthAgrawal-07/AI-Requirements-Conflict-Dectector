# AI Requirements Conflict Detector

> Automatically detects **conflicting**, **duplicate**, **ambiguous**, **incomplete**, and **dependent** requirements in an SRS document — flagging issues before they cost weeks of rework.

Built as a semester project for **IT314 — Software Engineering** (Autumn 2026–27), designed to double as a placement-ready, resume-worthy engineering artifact rather than a toy CRUD app.

---

## Table of Contents

- [Overview](#overview)
- [Core Features](#core-features)
- [Tech Stack](#tech-stack)
- [Architecture](#architecture)
- [Repository Structure](#repository-structure)
- [Getting Started](#getting-started)
- [Environment Variables](#environment-variables)
- [Team & Roles](#team--roles)
- [Project Status](#project-status)
- [Documentation](#documentation)
- [License](#license)

---

## Overview

Requirements documents (SRS) are typically written by multiple stakeholders over time, which introduces recurring, well-known problems in requirements engineering:

- **Conflicting** — two requirements contradict each other
- **Duplicate** — the same requirement restated in different words
- **Ambiguous** — a statement vague enough to be interpreted multiple ways
- **Incomplete** — a requirement missing information needed to implement or verify it
- **Dependent** — one requirement secretly relies on another

Finding these manually doesn't scale past a few dozen requirements. This project automates the process: upload an SRS document, and the system extracts individual requirements, filters candidate pairs using vector similarity, classifies issues with an LLM, generates clarification questions, and surfaces everything on a dashboard with full traceability back to the source document.

This isn't just an LLM wrapper — the system encodes real requirements-engineering discipline (see the Domain Requirements, DR-01–DR-12, in [`docs/engineering/requirements-spec.md`](docs/engineering/requirements-spec.md#3-domain-requirements-dr)): human review always takes precedence over AI suggestions, compliance-critical requirements are protected from auto-resolution, and semantic similarity is treated as a retrieval signal, never as proof of conflict on its own.

---

## Core Features

This is the target feature set for the semester. See [Project Status](#project-status) for what is built today.

- 📄 **Document ingestion** — born-digital PDF and DOCX (plain text and ReqIF are post-MVP; decision CR-16 in the backlog)
- 🔍 **Vector similarity pre-filter** — pgvector + Sentence-Transformers reduce LLM calls by ~70% vs. brute-force all-pairs comparison
- 🤖 **LLM-based classification** — 5-category issue detection with confidence scoring and natural-language rationale
- 💬 **Auto-generated clarification questions** — for every ambiguous, incomplete, or conflicting requirement
- 🔄 **Change-impact analysis** — see what breaks when a requirement is edited, before you save
- 📊 **Dashboard & relationship graph** — drill down from summary counts to individual flagged requirements
- 🔐 **Compliance-critical protection** — tagged requirements are never auto-merged or removed without manual sign-off
- 🧾 **Full audit trail** — every finding, override, and sign-off is logged and traceable

Full feature list: [`docs/engineering/requirements-spec.md`](docs/engineering/requirements-spec.md) (FR-01–FR-42, NFR-01–NFR-23, DR-01–DR-12) and [`docs/product-backlog.md`](docs/product-backlog.md) (user stories US-01–US-23).

---

## Tech Stack

**Frontend**
- React (Vite) + TypeScript
- Tailwind CSS + shadcn/ui
- React Flow — requirement dependency/conflict graph
- TanStack Query (React Query)

**Backend**
- FastAPI (Python)
- Pydantic — request/response validation & structured LLM output
- SQLAlchemy 2.x — ORM, Alembic — migrations
- Celery + Redis — background job queue for async document processing

**AI / NLP Core**
- Anthropic Claude API / OpenAI API — classification, clarification generation
- Sentence-Transformers (`all-MiniLM-L6-v2`) — requirement embeddings
- pgvector (PostgreSQL extension) — vector similarity search / candidate-pair pre-filtering

**Document Ingestion**
- PyMuPDF (`fitz`) — PDF text extraction
- python-docx — Word document extraction
- spaCy — sentence segmentation & NLP preprocessing

**Database & Infra**
- PostgreSQL (+ pgvector)
- Redis
- Docker Compose (local dev)
- Railway / Render (backend + DB deployment) · Vercel (frontend deployment)
- GitHub Actions (CI/CD)

**Testing**
- Pytest (backend)
- Vitest + React Testing Library (frontend)

---

## Architecture

```
                     ┌─────────────────┐
   SRS Document ───▶ │  Ingestion &     │
   (PDF/DOCX/ReqIF)  │  Extraction      │
                     └────────┬─────────┘
                              ▼
                     ┌─────────────────┐
                     │  Embedding &     │  ← Sentence-Transformers + pgvector
                     │  Similarity      │     (candidate pair pre-filter)
                     │  Pre-Filter      │
                     └────────┬─────────┘
                              ▼
                     ┌─────────────────┐
                     │  LLM             │  ← Conflicting / Duplicate /
                     │  Classification  │     Ambiguous / Incomplete / Dependent
                     └────────┬─────────┘
                              ▼
              ┌───────────────┴───────────────┐
              ▼                                ▼
     ┌─────────────────┐            ┌─────────────────────┐
     │  Clarification & │            │  Dashboard, Graph &  │
     │  Impact Analysis │            │  Reporting            │
     └─────────────────┘            └─────────────────────┘
```

Each stage runs as an independently maintainable module (ingestion, embedding, classification, presentation), connected via an async job queue so large documents don't block the API.

---

## Repository Structure

Folders marked *(stub)* exist but hold only placeholders so far. See [Project Status](#project-status).

```
.
├── .github/workflows/
│   ├── backend-ci.yml             # ruff, mypy, pytest (+ Postgres/Redis services), pip-audit, Docker build
│   └── frontend-ci.yml            # eslint, tsc, vitest, Docker build
├── backend/
│   ├── app/
│   │   ├── api/                   # FastAPI routers: auth, health (live); documents, requirements, findings, reports (stub)
│   │   ├── core/                  # Role 5 — config, database, JWT auth, errors, logging, Celery app
│   │   ├── models/                # SQLAlchemy 2.x models: 10 tables + shared enums
│   │   ├── schemas/               # Pydantic request/response models
│   │   ├── services/              # Business logic (user provisioning)
│   │   ├── ingestion/             # Role 1 — PDF/DOCX parsers + requirement segmentation
│   │   ├── embeddings/            # Role 2 — (stub)
│   │   ├── classification/        # Role 3 — (stub) prompts/ will hold versioned prompts
│   │   ├── clarification/         # Role 4 — (stub) see docs/clarification-impact-design.md
│   │   ├── cli.py                 # `make seed-demo` / `make create-user`
│   │   └── main.py
│   ├── alembic/versions/          # DB migrations (0001_initial_schema)
│   ├── tests/                     # pytest — unit / integration / llm / slow markers
│   ├── requirements.txt, requirements-dev.txt
│   └── Dockerfile, entrypoint.sh  # entrypoint runs `alembic upgrade head`
├── frontend/
│   ├── src/                       # Role 6 / Role 7 — (stub) App.tsx, lib/api-client.ts
│   ├── tests/
│   └── package.json, Dockerfile
├── docs/
│   ├── README.md                  # Start here: map of all documentation
│   ├── product-backlog.md         # 23 user stories with acceptance criteria
│   ├── engineering/               # Requirements, architecture, data model, API, ADRs, plans
│   ├── ingestion-design.md        # Role 1 module design
│   ├── clarification-impact-design.md  # Role 4 module design
│   └── wireframes/                # UI wireframes (Figma links + PDF exports)
├── sample_docs/
│   └── planted_conflicts/         # Labeled benchmark SRS (srs_v1) + labeling guide
├── docker-compose.yml             # db, redis, migrate, backend, worker, frontend
├── Makefile                       # `make help` lists every dev command
└── .env.example
```

---

## Getting Started

### Prerequisites
- Docker & Docker Compose
- Node.js 18+ (for local frontend dev outside Docker)
- Python 3.11+ (for local backend dev outside Docker)
- An Anthropic or OpenAI API key

### Quick Start (Docker Compose)

Requires **Docker Compose v2** (the `docker compose` plugin bundled with current Docker
Desktop / Docker Engine — not the legacy standalone `docker-compose` v1 binary).

```bash
# Clone the repo
git clone https://github.com/ParthAgrawal-07/AI-Requirements-Conflict-Dectector.git
cd AI-Requirements-Conflict-Dectector

# Copy and fill in environment variables
cp .env.example .env

# Start every service: Postgres+pgvector, Redis, a one-shot migration step,
# the FastAPI backend, the Celery worker, and the frontend dev server.
docker compose up --build
# (equivalently: `make up`, then `make logs` to follow output — see `make help`)
```

- Frontend: `http://localhost:5173`
- Backend API docs (Swagger): `http://localhost:8000/docs`
- Backend health check: `http://localhost:8000/health/ready`

There's no public sign-up endpoint by design (accounts are provisioned, not
self-registered — an IT/DevOps stakeholder requirement). Create your first user:

```bash
make seed-demo        # one demo user per role (analyst/admin/compliance_reviewer/
                       # read_only/service), dev-only, prints the shared password
# or
make create-user email=you@example.com name="Your Name" role=admin
```

Then log in at `POST /api/v1/auth/login` (Swagger's "Authorize" button works directly,
since it's a standard OAuth2 password-flow form) to get a bearer token for `/api/v1/auth/me`
and every other `/api/v1/*` route.

### Running Tests

```bash
# Backend — spins up nothing itself; needs the db/redis containers running (`make up` first)
cd backend && pytest
# or, fully inside Docker:
make test

# Frontend
cd frontend && npm run test
```

Backend tests that touch the database are marked `integration` and auto-skip (rather than
fail) if Postgres isn't reachable — set `REQUIRE_DB=1` (CI does) to make that a hard failure
instead. See `backend/tests/conftest.py`.

---

## Environment Variables

See [`.env.example`](.env.example) for the full, commented list. Key variables:

| Variable | Description |
|---|---|
| `ENVIRONMENT` | `development` / `test` / `staging` / `production` — the latter two enforce a strong `JWT_SECRET` and an explicit CORS origin list at startup |
| `DATABASE_URL` | PostgreSQL connection string (with pgvector extension enabled) |
| `REDIS_URL` | Redis connection string for Celery job queue |
| `LLM_API_KEY` | Anthropic or OpenAI API key |
| `LLM_PROVIDER` | `anthropic` or `openai` |
| `JWT_SECRET` | Secret for signing auth tokens |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | JWT lifetime in minutes (default 60) |
| `MAX_UPLOAD_SIZE_MB` | Upload size cap enforced by the API (default 25) |
| `SIMILARITY_THRESHOLD_DEFAULT` | Default cosine similarity threshold for candidate-pair filtering (per-workspace override lives in the database, not here) |

---

## Team & Roles

| Group | Member | Owns |
|---|---|---|
| Backend | Bansil ([@Bansil08](https://github.com/Bansil08)) | Document ingestion & extraction |
| Backend | Heet ([@the-heet-shah](https://github.com/the-heet-shah)) | Embeddings & similarity search |
| Backend | Keval ([@kevaldarji6126](https://github.com/kevaldarji6126)) | LLM classification pipeline |
| Backend | Madhav ([@PrimeNotFound](https://github.com/PrimeNotFound)) | Clarification & change-impact analysis |
| Backend | Parth ([@ParthAgrawal-07](https://github.com/ParthAgrawal-07)) | Backend API, auth & orchestration |
| Frontend | Pranshu ([@pranshu-chovatiya](https://github.com/pranshu-chovatiya)) | Upload & requirements-list UI |
| Frontend | Abhijeet ([@aprk05](https://github.com/aprk05)) | Findings, review & clarification UI |
| Frontend | Dhvani ([@DC-01051](https://github.com/DC-01051)) | Dashboard, graph & DevOps |
| Testing | Abhyudit ([@abhyudits](https://github.com/abhyudits)) | Backend & pipeline testing |
| Testing | Affan ([@Affan689](https://github.com/Affan689)) | Frontend & E2E testing |

Per-sprint assignments: [`docs/sprint-plan.md`](docs/sprint-plan.md). Full role breakdown: [`docs/engineering/roles-and-access.md`](docs/engineering/roles-and-access.md). Sprint plan and task list: [`docs/engineering/project-status.md`](docs/engineering/project-status.md) and [`docs/engineering/task-breakdown.md`](docs/engineering/task-breakdown.md).

---

## Project Status

🚧 **In development.** Sprint 0 (setup) is merged; Sprint 1 (upload and extraction) is in review.

**Sprint 0 — done (on `main`)**
- [x] Requirements, backlog (23 stories) and sprint plan
- [x] DB schema (10 tables) + first Alembic migration, pgvector enabled
- [x] JWT login (`POST /api/v1/auth/login`, `GET /api/v1/auth/me`), role model, demo-user CLI
- [x] Docker Compose (db, redis, migrate, backend, worker, frontend), Makefile, CI for backend and frontend
- [x] Ingestion scaffold: PDF and DOCX parsers
- [x] Design docs for clarification/impact analysis, upload-screen wireframe, labeled planted-conflicts benchmark (`srs_v1`)

**Sprint 1 — in review (open PRs)**
- [ ] US-01 document upload endpoint, validation and storage (#7)
- [ ] US-02 requirement extraction and segmentation (#8)
- [ ] Frontend test harness + per-story QA checklists (#17)

**Later**
- [ ] Embedding pipeline and LLM classification (Sprint 2, Integration Checkpoint 1 — Week 7)
- [ ] Review workflow, clarifications, impact analysis (Sprint 3)
- [ ] Dashboard and graph (Sprint 4, Integration Checkpoint 2 — Week 11)
- [ ] Hardening and deployment (Sprint 5, Week 13) · Demo (Week 14)

Live status and risks: [`docs/engineering/project-status.md`](docs/engineering/project-status.md).

---

## Documentation

Start at [`docs/README.md`](docs/README.md), which maps every document. Most-used:

- [Product Backlog (user stories + acceptance criteria)](docs/product-backlog.md)
- [Requirements Specification (FR / NFR / DR)](docs/engineering/requirements-spec.md)
- [Architecture](docs/engineering/architecture.md) · [Data Model](docs/engineering/data-model.md) · [API Reference](docs/engineering/api-reference.md)
- [Architecture Decision Records](docs/engineering/decision-log.md)
- [DevOps Guide (local setup, CI)](docs/engineering/devops-guide.md)

---

## License

This project is developed for academic purposes as part of IT314 — Software Engineering coursework. License to be finalized by the team (MIT recommended for a portfolio-facing project).
