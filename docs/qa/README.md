# QA - Frontend / E2E

- `QA_Checklist_Template.md` - copy per story into `stories/US-XX.md` when the story enters a sprint.
- `stories/` - filled-in checklists (US-01 and US-04 prepared for Sprint 1).
- Automated tests live in `frontend/tests/` (Vitest + React Testing Library). Run `npm run test:run` inside `frontend/`.
  Shared helpers: `tests/test-utils.tsx` (`renderWithProviders`), `tests/fixtures.ts`, `tests/setup.ts`.
- Acceptance criteria must be pasted from the Product Backlog into each checklist.
