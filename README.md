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

This isn't just an LLM wrapper — the system encodes real requirements-engineering discipline (see [`docs/domain-requirements.md`](docs/domain-requirements.md)): human review always takes precedence over AI suggestions, compliance-critical requirements are protected from auto-resolution, and semantic similarity is treated as a retrieval signal, never as proof of conflict on its own.

---

## Core Features

- 📄 **Multi-format ingestion** — PDF, DOCX, plain text, ReqIF
- 🔍 **Vector similarity pre-filter** — pgvector + Sentence-Transformers reduce LLM calls by ~70% vs. brute-force all-pairs comparison
- 🤖 **LLM-based classification** — 5-category issue detection with confidence scoring and natural-language rationale
- 💬 **Auto-generated clarification questions** — for every ambiguous, incomplete, or conflicting requirement
- 🔄 **Change-impact analysis** — see what breaks when a requirement is edited, before you save
- 📊 **Dashboard & relationship graph** — drill down from summary counts to individual flagged requirements
- 🔐 **Compliance-critical protection** — tagged requirements are never auto-merged or removed without manual sign-off
- 🧾 **Full audit trail** — every finding, override, and sign-off is logged and traceable

Full feature list: [`docs/requirements-baseline.md`](docs/requirements-baseline.md) (FR-01–FR-34) and [`docs/product-backlog.md`](docs/product-backlog.md) (user stories US-01–US-23).

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
- SQLAlchemy / SQLModel — ORM
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

```
ai-requirements-conflict-detector/
├── .github/
│   └── workflows/
│       ├── backend-ci.yml
│       └── frontend-ci.yml
├── backend/
│   ├── app/
│   │   ├── api/                  # FastAPI route handlers
│   │   │   ├── auth.py
│   │   │   ├── documents.py
│   │   │   ├── requirements.py
│   │   │   ├── findings.py
│   │   │   └── reports.py
│   │   ├── ingestion/             # Role 1 — document parsing & extraction
│   │   │   ├── pdf_parser.py
│   │   │   ├── docx_parser.py
│   │   │   └── segmenter.py
│   │   ├── embeddings/            # Role 2 — embedding & similarity search
│   │   │   ├── embed.py
│   │   │   ├── vector_store.py
│   │   │   └── candidate_filter.py
│   │   ├── classification/        # Role 3 — LLM classification pipeline
│   │   │   ├── prompts/
│   │   │   ├── classifier.py
│   │   │   └── schemas.py         # Pydantic models for structured LLM output
│   │   ├── clarification/         # Role 4 — clarification & impact analysis
│   │   │   ├── question_gen.py
│   │   │   └── impact_analysis.py
│   │   ├── core/                  # Role 5 — orchestration, auth, config
│   │   │   ├── auth.py
│   │   │   ├── config.py
│   │   │   ├── celery_app.py
│   │   │   └── database.py
│   │   ├── models/                # SQLAlchemy / SQLModel ORM models
│   │   └── main.py
│   ├── tests/
│   ├── alembic/                   # DB migrations
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── upload/            # Role 6 — core UI
│   │   │   ├── requirements-list/
│   │   │   ├── findings-panel/
│   │   │   └── graph/             # Role 7 — React Flow visualization
│   │   ├── pages/
│   │   ├── hooks/
│   │   ├── lib/                   # API client, React Query setup
│   │   └── App.tsx
│   ├── tests/
│   ├── package.json
│   └── Dockerfile
├── docs/
│   ├── project-plan.md            # 14-week execution plan
│   ├── stakeholder-elicitation.md
│   ├── requirements-baseline.md   # Consolidated FR / NFR / Domain Requirements
│   ├── product-backlog.md         # Consolidated user stories
│   ├── domain-requirements.md
│   └── architecture-diagrams/
│       └── activity-diagram.png
├── sample-data/
│   └── test-srs-with-planted-conflicts.pdf
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
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
git clone https://github.com/<org>/ai-requirements-conflict-detector.git
cd ai-requirements-conflict-detector

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

| Role | Responsibility |
|---|---|
| Document Ingestion | PDF/Word parsing, sentence segmentation |
| Embedding & Similarity Search | Vector embeddings, pgvector, candidate-pair filtering |
| LLM Classification Pipeline | Prompt design, classification, structured output validation |
| Clarification & Impact Analysis | Clarification questions, change-impact analysis |
| Backend API & Orchestration | FastAPI, Celery/Redis, auth, end-to-end wiring |
| Frontend — Core UI | Upload flow, requirements list, findings UI |
| Frontend — Visualization + DevOps | Dependency graph (React Flow), Docker, CI/CD, deployment |

Full role breakdown and 14-week execution plan: [`docs/project-plan.md`](docs/project-plan.md).

---

## Project Status

🚧 **In development** — semester project, IT314 Autumn 2026–27.

- [x] Stakeholder identification & elicitation
- [x] Functional / Non-Functional / Domain requirements baseline
- [x] User story backlog
- [ ] Ingestion pipeline (Week 3)
- [ ] Embedding pipeline (Week 4)
- [ ] LLM classification pipeline (Week 6)
- [ ] Integration Checkpoint 1 (Week 7)
- [ ] Frontend v1 (Week 8)
- [ ] Integration Checkpoint 2 (Week 11)
- [ ] Deployment (Week 13)
- [ ] Demo (Week 14)

---

## Documentation

- [Stakeholder Identification & Elicitation Plan](docs/stakeholder-elicitation.md)
- [Consolidated Requirements Baseline (FR / NFR / Domain)](docs/requirements-baseline.md)
- [Consolidated Product Backlog (User Stories)](docs/product-backlog.md)
- [Project Plan & Timeline](docs/project-plan.md)

---

## License

This project is developed for academic purposes as part of IT314 — Software Engineering coursework. License to be finalized by the team (MIT recommended for a portfolio-facing project).
