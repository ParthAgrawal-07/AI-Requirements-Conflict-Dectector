## What & why

<!-- One or two sentences. Link the story/task: US-xx, Txx, FR-xx. -->

Closes / relates to:

## How to test

<!-- Commands or steps a reviewer can run, e.g. `make test`, or a curl against /docs. -->

## Checklist

- [ ] Tests added or updated, and `make check` (backend) / `npm run test` (frontend) passes locally
- [ ] Schema changes come with an Alembic migration (one head only)
- [ ] No secrets committed; new config is added to `.env.example`
- [ ] Docs updated where this change affects them (see the change-impact matrix in `docs/engineering/INDEX.md`)
