# AGENTS.md — rules for AI coding agents

Applies to every AI assistant working in this repo (Claude Code, Codex, Copilot, Cursor, CodeRabbit…).
Humans: this is also a fair summary of how we work. When this file and a document under `docs/` disagree,
the document wins — fix this file.

**AI Requirements Conflict Detector (RCD)** — IT314 semester project. Upload an SRS; the system extracts
requirements, picks candidate pairs, classifies issues (Conflicting / Duplicate / Ambiguous / Incomplete /
Dependent) with an LLM, and puts every finding in front of a human.

---

## 1. Sources of truth

1. `docs/planning/v5/` — the revision 5 planning documents (requirements, backlog, sprint plan, design).
2. `docs/engineering/` — follows the planning docs. Start at `docs/engineering/INDEX.md`.
3. `docs/contracts/` — interface contracts between owners (e.g. `permissions.md`). Code must match them.
4. `docs/engineering/decision-log.md` — ADRs. Don't contradict an Accepted ADR; propose a new one.

Cite IDs (`US-xx`, `FR-xx`, `NFR-xx`, `DR-xx`, `ADR-xx`) in docstrings, commits and PRs, as existing code does.

## 2. Scope

- Change only what the task needs. No drive-by refactors, reformatting or renames of code you weren't asked to touch.
- Ownership is in `.github/CODEOWNERS`. Ask before editing another owner's module.
- Ask before changing shared config: `docker-compose.yml`, `Makefile`, `.github/workflows/`, `backend/ruff.toml`,
  `backend/mypy.ini`, `backend/pytest.ini`, `requirements*.txt`, `frontend/package.json`, `.env.example`.
- After a change, check the **change-impact matrix** (`docs/engineering/INDEX.md` §3) and update the docs it lists
  in the same PR.

## 3. Layout

```
backend/app/
  api/            FastAPI routes — thin; validate, check access, call a service
  services/       business logic and DB work
  core/           config, auth, permissions, errors, Celery, logging
  models/         SQLAlchemy models        schemas/   Pydantic request/response models
  ingestion/      PDF/DOCX parsing, segmentation          (Bansil)
  embeddings/     embeddings, pgvector, candidate pairs    (Heet)
  classification/ LLM client, prompts, classifier          (Keval)
  clarification/  questions, change-impact analysis        (Madhav)
  context/, intake/  project context/brief, EARS composer
backend/alembic/versions/   migrations
backend/tests/<module>/     tests mirror app/
frontend/src/               React + Vite + TypeScript (Tailwind, shadcn/ui, TanStack Query, React Flow)
```

## 4. Commands

```bash
make up                 # all services via Docker Compose v2
make check              # ruff + mypy + pytest inside Docker — what CI runs
make makemigration m="add x"   # autogenerate an Alembic migration
cd backend && ruff check . && ruff format --check . && mypy app && pytest
cd frontend && npm run lint && npm run typecheck && npm run test:run
```

CI (`.github/workflows/`) runs ruff lint **and** `ruff format --check`, mypy, pytest with `REQUIRE_DB=1`,
a single-Alembic-head check, and Docker builds. Run the same locally before pushing.

## 5. Backend rules

**Access control** (`docs/contracts/permissions.md`, US-27)
- Every `/api/v1` route declares exactly one of `requires("perm")`, `requires_any(...)`, `Authenticated` or
  `PublicRoute` from `app.api.deps`. `tests/api/test_access_invariants.py` fails the build otherwise.
- Use permission **names** from `app/core/permissions.py`. Never compare role names.
- Path tenant parameters are exactly `workspace_id`, `project_id`, `document_id`, `requirement_id`; a new
  resource type registers a scope resolver (`register_scope_resolver`).
- Not a member → **404**, never 403. Member without the permission → **403**.
- Protected-only grants fail closed. `allow_protected_only=True` needs an explicit `ctx.can(..., protected_requirement=...)`
  check and an entry in `PROTECTED_ONLY_OPT_INS`.

**Errors and responses**
- Raise subclasses of `AppError` from `app/core/errors.py` (`NotFoundError`, `ForbiddenError`, `ConflictError`…).
  Don't build ad-hoc `HTTPException` bodies; the error envelope is documented in `api-reference.md`.
- Never echo submitted values or secrets in errors or logs.

**Database**
- Any model change ships with an Alembic migration in the same PR. Exactly one head (CI checks).
- Don't edit a migration that is already on `main`; add a new one. Follow `docs/engineering/migration-runbook.md`.
- Every query is tenant-scoped (workspace/project). Cross-tenant reads are a security bug.

**Style and typing**
- Python 3.11, ruff (`backend/ruff.toml`), line length 100.
- `app.core`, `app.api`, `app.models`, `app.schemas`, `app.services` and `app.cli` are strictly typed in mypy.
  Fully type new code elsewhere too. No bare `# type: ignore`.
- Module docstrings name the owner and the story/requirement IDs, as existing modules do.
- Comment the *why*, not the *what*.

**Tests** (`backend/pytest.ini`)
- Markers: `unit`, `integration` (needs Postgres+pgvector and Redis), `llm` (real API, excluded by default), `slow`.
- Default and CI runs never call a real LLM. Mock the transport.
- New routes get a happy-path test, a 403 test and a 404-for-non-member test.

## 6. AI / LLM rules (ADR-31, `docs/engineering/ai-providers.md`)

- Providers: **Google Gemini** (primary) and **Groq** (backup). No Anthropic or OpenAI code or dependencies.
- All LLM calls go through `LLMClient` and its transports in `app/classification/`. No provider SDK calls anywhere else.
- Fail over to Groq only when Gemini is *unavailable* (rate limit, 5xx, timeout, network). Never fail over on a
  refusal or on invalid output.
- Validate every LLM reply against its Pydantic schema. Record the provider and model on every stored AI result.
- Prompts live in `prompts/` folders as versioned files, not inline strings.
- Never log prompt text, requirement text or API keys.
- Embeddings: `BAAI/bge-small-en-v1.5`, run locally (384 dims). A model change means re-embedding by `model_version`.
- Candidate generation follows ADR-30 (`conflict-detection-strategy.md`): similarity is a retrieval signal, not proof.

## 7. Domain rules — never break these

- **Human in the loop** (ADR-06, DR-04/DR-05): nothing deletes, merges or rewrites a requirement without an
  explicit, audited human action.
- **Protected / compliance-critical requirements** are never auto-resolved and need manual sign-off.
- **Similarity ≠ conflict** (DR-10): a high score alone never creates a finding.
- **AI output stays distinguishable** from human-approved content (NFR-17), in the API and in the UI.
- **Audit trail**: every finding decision, override and sign-off writes an audit record.

## 8. Frontend rules

- React + Vite + TypeScript, `strict`. No `any`. Tailwind + shadcn/ui; TanStack Query for server state.
- API calls go through `src/lib/api-client.ts`. Keep auth tokens out of `localStorage`.
- Accessible by default: semantic elements, labels, keyboard navigation.
- Tests: Vitest + React Testing Library in `frontend/tests/`.

## 9. Git and PRs

- Branch from `main`: `<area>/<name>-<topic>` (e.g. `backend/heet`, `feat/madhav-sprint1-join-codes`, `docs/...`).
- Conventional Commits: `feat(embeddings): …`, `fix(api): …`, `docs: …`. Subject ≤ 72 chars; a `fix` body explains the root cause.
- PRs target `main` and fill in `.github/pull_request_template.md`: link the story, how to test, the checklist.
- Never commit secrets. New config goes in `.env.example` with a comment. GitGuardian scans every push.
- Don't commit `package-lock.json` churn from Windows unless the dependency change is intended.
