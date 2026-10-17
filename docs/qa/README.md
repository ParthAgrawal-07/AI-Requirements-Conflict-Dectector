# QA - Frontend / E2E

- `QA_Checklist_Template.md` - generic checks for every story. Copy it to `stories/US-XX.md` only when a story needs its own file.
- `stories/` - per-story checklists with the acceptance criteria and story-specific checks (US-01 and US-04 for Sprint 1). They link to the template for the generic checks, so a template fix applies to every story.
- Automated tests live in `frontend/tests/` (Vitest + React Testing Library). Run `npm run test:run` inside `frontend/`.
  Shared helpers: `tests/test-utils.tsx` (`renderWithProviders`), `tests/fixtures.ts`, `tests/setup.ts`. Shared types: `frontend/src/types.ts`.
- Coverage: `npm run test:coverage` writes an HTML report to `frontend/coverage/` (git-ignored).
