# System Architecture

**Module Ownership, Pipeline Flow, and Deployment**

> Status: Planned — architecture is locked, no code written yet

---

## 1. High-Level Pipeline Flow

The core value proposition is the conflict-detection pipeline. It runs as an asynchronous job (Celery + Redis) once a document is uploaded, so the user can track progress (US-03) rather than blocking on a long-running request.

```
1. Upload SRS document (PDF / DOCX / plain text)  [FR-01, FR-02]
2. Validate file (format, size, integrity)         [FR-02]
3. Extract & segment into requirement statements   [FR-03, FR-04]
4. Generate embeddings (Sentence-Transformers)      [FR-07]
5. Store embeddings in pgvector                    [FR-08]
6. Rank candidate pairs by similarity threshold     [FR-09, FR-10]
7. Protected-requirement check (skip auto-merge)    [DR-05, FR-21]
8. LLM classification (5-category taxonomy)         [FR-11-FR-17]
9. Validate structured output (schema check)        [FR-15]
10. Persist finding + confidence + rationale         [FR-13, FR-14, FR-19]
11. Generate clarification question if flagged       [FR-22]
12. Update dependency/conflict graph                 [FR-29]
13. Write audit-trail entry                          [FR-36, NFR-13]
14. Surface to analyst via dashboard / findings UI    [FR-27, FR-28]
```

This is the same workflow the team's hand-drawn Lab 6 activity diagram models; see `diagrams.md` for a Mermaid-source rendering of the equivalent flow.

## 2. Module Ownership (Backend)

| Module (planned path) | Owning role | Responsibility |
|---|---|---|
| `backend/app/ingestion/` | Role 1 | PDF/Word parsing (PyMuPDF, python-docx), sentence segmentation (spaCy) |
| `backend/app/embeddings/` | Role 2 | Sentence-Transformers embedding generation, pgvector similarity search, threshold config |
| `backend/app/classification/` | Role 3 | LLM prompt design, classification calls, structured/schema output validation |
| `backend/app/clarification/` | Role 4 | Clarification-question generation, change-impact analysis |
| `backend/app/core/` | Role 5 | FastAPI app, Celery/Redis wiring, JWT auth, cross-cutting orchestration |

### Module Ownership (Frontend)

| Module (planned path) | Owning role | Responsibility |
|---|---|---|
| `frontend/src/components/upload/` | Role 6 | Upload flow, requirements list, findings review UI |
| `frontend/src/components/graph/` | Role 7 | React Flow dependency/conflict graph, dashboard, CI/CD, deployment config |

## 3. Architectural Layers

- **Frontend** — React (Vite) + TypeScript, Tailwind + shadcn/ui components, TanStack Query for server state, React Flow for the relationship graph.
- **Backend API** — FastAPI with Pydantic schemas; SQLAlchemy/SQLModel for the ORM layer.
- **Async processing** — Celery workers backed by Redis handle the long-running pipeline (embedding → classification) so the API stays responsive (NFR-01, NFR-02).
- **AI/NLP layer** — Sentence-Transformers (all-MiniLM-L6-v2) for embeddings; Anthropic Claude API / OpenAI API for classification and clarification generation.
- **Data layer** — PostgreSQL with the pgvector extension for vector similarity search, alongside standard relational tables (see `data-model.md`).
- **Deployment** — Docker Compose for local dev and CI; Railway/Render for the backend, Vercel for the frontend, GitHub Actions for CI/CD (see `devops-guide.md`).

## 4. Key Architecture Decision: Embedding Pre-Filter

An explicit, deliberate team decision (not a framework default): candidate requirement pairs are pre-filtered by embedding similarity (pgvector) before any LLM call, rather than running brute-force all-pairs LLM comparison. This is expected to reduce LLM calls by 70%+ and is encoded as both a performance requirement (NFR-05) and a domain rule (DR-10 — similarity is a filter, not itself proof of conflict/duplication). Full rationale in `decision-log.md`.

## 5. Non-Functional Drivers on the Architecture

- NFR-19 requires ingestion, embedding, classification, and presentation to be independently deployable modules/services — reflected in the module split above.
- NFR-04 (≥50 concurrent analysis jobs) and NFR-01 (5-minute target for a ~150–300-requirement document) drive the choice of an async job queue rather than synchronous processing.
- NFR-11/NFR-12/NFR-13 (RBAC, credential protection, audit logging) drive keeping auth and secrets handling inside `backend/app/core/` rather than scattered across modules.
