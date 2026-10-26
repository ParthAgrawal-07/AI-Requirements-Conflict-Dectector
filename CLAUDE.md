# CLAUDE.md

@AGENTS.md

## Claude Code notes

- This repo is the **AI Requirements Conflict Detector** (FastAPI + React/Vite). Rules from any parent or
  user-level `CLAUDE.md` that describe another project (Next.js, pnpm, the Anthropic SDK…) do not apply here.
- Do not add the Anthropic SDK or Claude models to the product. The app uses Gemini and Groq only (ADR-31).
- Before saying a backend change is done, run `ruff check .`, `ruff format --check .` and `mypy app` in `backend/`,
  plus the relevant `pytest` path. Say so if Postgres was unavailable and integration tests were skipped.
- For schema changes, generate the migration (`make makemigration m="..."`) and read it before committing.
  Autogenerate misses pgvector indexes and server defaults.
