# Contributing

Thank you for your interest in the AI Requirements Conflict Detector! This guide helps you
get started with contributions.

## Getting Started

```bash
# Clone and set up
git clone https://github.com/ParthAgrawal-07/AI-Requirements-Conflict-Dectector.git
cd AI-Requirements-Conflict-Dectector
cp .env.example .env    # fill in your API keys

# Start all services
make up                 # Docker Compose: Postgres+pgvector, Redis, backend, worker, frontend
make logs               # follow output
```

## Development Workflow

1. **Create a branch** from `main` with a descriptive name:
   - `feat/us-XX-short-description` for features
   - `fix/us-XX-short-description` for bug fixes
   - `docs/topic` for documentation
   - `test/topic` for test-only changes

2. **Follow the existing code style**:
   - Backend: `ruff check . && ruff format --check . && mypy app` (enforced by CI)
   - Frontend: `npm run lint && npm run typecheck`

3. **Write tests** for any new functionality:
   - Backend: `pytest` (integration tests auto-skip without Postgres; CI uses `REQUIRE_DB=1`)
   - Frontend: `npm run test:run`

4. **Run the full check before pushing**:
   ```bash
   make check    # runs ruff, mypy, pytest inside Docker — same as CI
   cd frontend && npm run lint && npm run typecheck && npm run test:run
   ```

5. **Open a PR** against `main` with:
   - A clear title referencing the user story (`US-XX: ...`)
   - A description of what changed and why
   - Links to relevant docs or ADRs

## Code Organization

See [`AGENTS.md`](AGENTS.md) §3 for the full layout. Key rules:

- **Routes are thin**: validate, check access, call a service. Business logic lives in
  `app/services/`.
- **Cite IDs**: reference `US-xx`, `FR-xx`, `NFR-xx`, `DR-xx`, `ADR-xx` in docstrings,
  commits, and PRs.
- **Change-impact matrix**: after a change, check `docs/engineering/INDEX.md` §3 and update
  the docs it lists in the same PR.
- **Ownership**: see `.github/CODEOWNERS`. Ask before editing another owner's module.
- **Shared config**: ask before changing `docker-compose.yml`, `Makefile`, CI workflows,
  `requirements*.txt`, or `frontend/package.json`.

## Sources of Truth

1. `docs/planning/v5/` — revision 5 planning documents
2. `docs/engineering/` — start at `docs/engineering/INDEX.md`
3. `docs/contracts/` — interface contracts between owners
4. `docs/engineering/decision-log.md` — ADRs (don't contradict an Accepted ADR)

## Questions?

Open an issue or reach out to the team. For security issues, see [`SECURITY.md`](SECURITY.md).
