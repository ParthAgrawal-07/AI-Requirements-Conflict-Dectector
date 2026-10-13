# Per-Story QA Checklist — Template

Copy this file to `docs/qa/stories/US-XX.md` when a story enters a sprint. Fill the
**Acceptance Criteria** section by pasting the criteria from the Product Backlog verbatim,
so every check below traces back to a criterion.

| Field | Value |
|---|---|
| Story ID / title | US-XX — |
| Sprint | |
| Dev owner | |
| QA owner (Frontend/E2E) | |
| Status | ☐ Not started ☐ In QA ☐ Failed ☐ Passed |
| Build / commit tested | |
| Date tested | |

## 1. Acceptance Criteria Trace

| # | Acceptance criterion (verbatim from backlog) | Automated test (file › test name) | Manual check | Result |
|---|---|---|---|---|
| AC-1 | | | ☐ | ☐ Pass ☐ Fail |
| AC-2 | | | ☐ | ☐ Pass ☐ Fail |

Rule: every criterion needs at least one automated test **or** a written manual step. No criterion left blank.

## 2. Functional Checks
- [ ] Happy path works end to end
- [ ] Each acceptance criterion verified (Section 1)
- [ ] Empty state shown when there is no data
- [ ] Loading state shown during async calls
- [ ] Error state shown with a clear message when the API fails (4xx / 5xx / network down)
- [ ] Invalid input rejected with a helpful message (wrong type, too large, empty)
- [ ] Repeat / double-submit does not create duplicates
- [ ] Browser refresh and back button behave sensibly

## 3. Project Domain Rules (apply when the story touches findings or requirement text)
- [ ] Original requirement text is never silently altered, deleted or merged — human approval is required
- [ ] AI-generated content is visually distinguishable from human-approved content
- [ ] Compliance-critical requirements are not auto-resolved and are routed to manual review
- [ ] Findings show category (Conflicting / Duplicate / Ambiguous / Incomplete / Dependent), and confidence + rationale where the story requires them

## 4. UI / UX
- [ ] Layout correct at desktop (≥1280px) and tablet (~768px)
- [ ] Keyboard navigable; visible focus; logical tab order
- [ ] Controls have accessible names (labels / aria-label); colour is not the only signal
- [ ] No console errors or warnings during the flow
- [ ] Text/labels match wireframes (docs/wireframes) or deviations are noted

## 5. Automated Tests (Vitest + React Testing Library)
- [ ] Component tests added under `frontend/tests/*.test.tsx`
- [ ] Tests query by role / label / text (not CSS classes)
- [ ] API calls mocked; no real network in unit tests
- [ ] `npm run test:run` passes locally and in CI
- [ ] Coverage for the story's components reviewed (`npm run test:coverage`)

## 6. Defects Found

| ID | Description | Steps to reproduce | Severity (Blocker/Major/Minor) | Status |
|---|---|---|---|---|
| | | | | |

## 7. Sign-off
- QA verdict: ☐ Pass ☐ Pass with known issues ☐ Fail
- Notes:
- Signed off by / date:

**Definition of Done (QA part):** all Section 1 criteria pass, no open Blocker/Major defects, automated tests merged and green in CI.
