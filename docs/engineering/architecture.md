# System Architecture

**Module Ownership, Pipeline Flow, and Deployment (revision 5)**

| | |
|---|---|
| **Status** | Modular monolith with API and worker processes; tenancy, permissions, upload, extraction and project context are implemented, the rest is planned |
| **Detail** | `system-design.md` and `object-design.md`; changes for the extended scope in [`IT314_RCD_Design_Update_v5.md`](../planning/v5/IT314_RCD_Design_Update_v5.md) |

---

## 1. High-Level Flows

Analysis runs as asynchronous jobs (Celery + Redis) so no HTTP request blocks on it. Since revision 5, **no analysis runs for a project until its context is confirmed** (FR-103, `ContextGate`).

### 1.1 Project setup and document path

```
1. Create project → status = setup                         [FR-47, FR-103]
2. Upload initial SRS (import as baseline or proposals)    [FR-01, FR-02]
3. Extract & segment; keep printed IDs; store sections      [FR-03, FR-04, US-02]
4. LLM drafts the brief from the introduction (AI-drafted)  [FR-104]
5. PM confirms the 4 required fields → status = active      [FR-103]
6. Generate embeddings, store in pgvector                   [FR-07, FR-08]
7. Rank candidate pairs above the project threshold         [FR-09, FR-10]
8. Rule-based cross-checks on extracted attributes          [FR-101]  (regardless of similarity)
9. LLM classification with the context pack                 [FR-11–FR-17, FR-105]
10. Validate structured output; retry up to 3×              [FR-15, NFR-07]
11. Persist finding (source, confidence, severity, context_version)  [FR-13, FR-42, FR-97]
12. Clarification question; AI resolution suggestions (async)        [FR-22, FR-68]
13. Graph delta → live map and written change log           [FR-84, FR-95]
14. Audit entry (IDs and actions, never text)               [FR-36, NFR-13]
```

### 1.2 Collaboration path

```
Composer (EARS, live lint, similar hints, pre-flight)   [FR-81–FR-83]
  → requirement post (Proposed)                         [FR-55]
  → incremental analysis run vs. baseline + proposals   [FR-56, ADR-16]
  → result card in the thread; owners @mentioned        [FR-57]
  → auto conflict issue when two owners are involved    [FR-87]
  → AI suggestions; accept opens a change request       [FR-68]
  → checks: findings delta, impact, risk                [FR-63, FR-99]
  → reviewers from decision rules; merge by agreement   [FR-65, FR-98, FR-100]
  → new version, baseline revision +1, map updated, owners notified
```

### 1.3 Updated SRS

Readiness checklist → draft in ISO/IEC/IEEE 29148 order (requirement sections rendered by the **system**, narrative sections by the **LLM**, one call each) → section review → fidelity check (DR-25) → publish immutable SRS vX.Y → export DOCX, PDF, Markdown with the open-items report (FR-106, FR-107, ADR-29).

See `diagrams.md` for the activity diagram and state machines.

## 2. Module Ownership (Backend)

| Design element | Path | Owner |
|---|---|---|
| Entities, enums, migrations | `backend/app/models/`, `backend/alembic/` | Parth |
| Auth, membership, permissions and roles | `app/core/auth.py`, `app/core/permissions.py`, `app/services/{access,membership,roles}.py` | Parth |
| Join codes and join requests | `app/services/join_codes.py` | Madhav |
| Channels, messages | `app/services/channels.py`, `app/api/channels.py` | Madhav |
| Requirement posts, drafts, ownership, votes, watches, links | `app/intake/` | Bansil |
| Ingestion (extraction, segmentation) | `app/ingestion/` | Bansil |
| Project context, brief drafting, context gate | `app/context/` | Bansil |
| Updated SRS: readiness, generator, fidelity, exporter | `app/export/srs/` | Bansil (Keval: prompts) |
| Real-time gateway, event bus, queues, beat | `app/realtime/`, `app/core/celery_app.py` | Dhavni didi |
| Graph service, deltas, change narrator | `app/graph/` | Dhavni didi |
| Issues and auto conflict issues | `app/services/issues.py` | Dhavni didi |
| Embeddings, candidates, incremental retrieval, similar hints, search | `app/embeddings/`, `app/search/` | Heet |
| Classification, LLM clients, budget guard, context pack, lint catalogue, pre-flight, AI wording | `app/classification/`, `app/lint/` | Keval |
| Clarification, impact, consequence checks, risk, notifications, AI suggestions | `app/clarification/`, `app/consequences/`, `app/suggestions/`, `app/notifications/` | Madhav (Keval: prompts) |
| Change requests, review policy, merge, baselines, audit | `app/services/{change_requests,reviews,baselines}.py` | Parth |

Directories that exist on `main` today: `api`, `clarification`, `classification`, `context`, `core`, `embeddings`, `ingestion`, `intake`, `models`, `schemas`, `services`. The rest are created by their owners when their sprint starts.

### Module Ownership (Frontend)

| Area | Path | Owner |
|---|---|---|
| Shell, channels, composer, requirements, issues, dashboard, baselines, analytics, map preview, updated SRS | `frontend/src/features/{channels,composer,requirements,issues,dashboard,baselines,analytics,srs}` | Pranshu |
| Members and roles, project setup wizard, findings, review, live map, change requests, inbox, compliance | `frontend/src/features/{members,setup,findings,review,map,changes,notifications,compliance}` | Abhijeet |

### Test Ownership

| Area | Path | Owner |
|---|---|---|
| Accuracy benchmark, API and database tests | `backend/tests/`, `eval/` | Abhyudit |
| E2E, load and security tests | `e2e/`, `load/` | Affan |

## 3. Architectural Layers

- **Frontend** — React (Vite) + TypeScript, Tailwind + shadcn/ui, TanStack Query for server state, a graph store fed by `graph.delta` events for the live map.
- **Backend API** — FastAPI with Pydantic schemas and SQLAlchemy; every route declares the permission it needs; services own transactions (ADR-09).
- **Real-time** — WebSocket in the API process, fan-out via Redis pub/sub; events are published after commit; REST is the only write path; clients re-sync by REST on reconnect (ADR-15).
- **Async processing** — Celery workers run extraction, analysis runs, consequence reports, suggestions and SRS drafting; tasks are idempotent per run ID (ADR-13).
- **AI/NLP** — Sentence-Transformers (all-MiniLM-L6-v2) for embeddings; an `LLMClient` adapter for classification, clarification, suggestions, brief drafting and SRS narrative; every project-scoped call carries the context pack (ADR-28); a `BudgetGuard` enforces the per-project LLM budget (NFR-28).
- **Data** — PostgreSQL with pgvector for relational data and vector search (ADR-03); see `data-model.md`.
- **Deployment** — Docker Compose for local dev and CI; Railway/Render for the backend, Vercel for the frontend, GitHub Actions for CI/CD (see `devops-guide.md`).

## 4. Key Architecture Decisions

- **Embedding pre-filter (ADR-01)** — only pairs above a configurable similarity threshold go to the LLM (NFR-05); similarity is a filter, never proof (DR-10).
- **Rule-based cross-checks outside the filter (ADR-27)** — deterministic checks on extracted attributes catch differently worded conflicts the filter misses; recall is measured below the threshold (NFR-37).
- **Incremental analysis runs (ADR-16)** — each new or changed requirement is checked against its top-*k* neighbours, not the whole project.
- **Changes only through change requests (ADR-17, ADR-22)** — approved requirements are never edited in place (DR-14).
- **Permission-based RBAC (ADR-20)** — code checks permissions, never role names.
- **Graph deltas (ADR-21)** — the live map is rebuilt from stored results, never by re-analysing.
- **Context first, updated SRS last (ADR-28, ADR-29)** — compulsory context and a bounded context pack; the LLM never writes requirement text.

Full list in `decision-log.md`.

## 5. Non-Functional Drivers on the Architecture

- NFR-19 requires ingestion, embedding, classification, consequence analysis, real-time delivery and presentation as separate modules with narrow interfaces — reflected in the module split above.
- NFR-01, NFR-04, NFR-25, NFR-26 (analysis time and concurrency) drive the async job queue, with live analysis on a separate high-priority queue.
- NFR-24 and NFR-32 (messages within 1 s, map deltas within 2 s at p95) drive WebSocket push with Redis pub/sub and 250 ms delta batching.
- NFR-11, NFR-27, NFR-35 (membership-checked access on every request and subscription, socket closure on removal, hashed rate-limited join codes) keep authorisation inside `app/core/` and `app/services/access.py`.
- NFR-28 and NFR-38 (LLM budget, SRS generation cost) drive the `BudgetGuard`, the result cache and one LLM call per narrative section.
