# US-22 — Low-Fidelity Validation Sessions (Sprint 2)

| | |
|---|---|
| **Run by** | Abhyudit and Affan (facilitator and note-taker, alternating) |
| **Prototypes** | Abhijeet — `/prototypes` in the app (findings view, requirement post, consequence report) |
| **Target** | at least 5 sessions with sample users from outside the team (classmates count) |
| **Acceptance** | a reviewer can judge whether a test case could be written from a flagged item; a new contributor finds a channel and posts a requirement within 5 minutes (NFR-31); every gap is logged against a story before it is built |

This is a validation activity, not a product mode (CR-13). Nothing here ships to users.

## 1. Before each session

- [ ] Prototype build running (`npm run dev`, open `/prototypes`); a clean browser profile.
- [ ] Consent read aloud: the session is about the prototype, not the participant; notes are
      anonymous (participant P1…P5); they can stop at any time. No screen recording without a yes.
- [ ] Timer ready for Task 2 (NFR-31).

## 2. Tasks (read exactly; do not help unless stuck for 60 s)

| # | Task | Screen | What we measure |
|---|---|---|---|
| 1 | "This finding says two requirements conflict. Could you write a test case from it? Tell me what you would test." | Findings view (finding card + drawer) | Can they name the conflicting clause, both IDs and what to test? Do they read the confidence and the "low confidence" marker correctly? |
| 2 | "You are new to this project. Find the place to discuss the mobile app and propose this requirement: *when the user is inactive for 5 minutes, log them out*." | Requirement post | Time to post (target < 5 min); wrong turns; do they find the channel from the sidebar? |
| 3 | "Someone proposes changing REQ-014. Who has to agree, and what else might break?" | Consequence report | Do they find the affected requirements and owners? Do they understand "AI" vs. "Rule" labels? |
| 4 | "On a scale of 1–5, how sure are you about your answers?" | — | Self-reported confidence |

## 3. Observation sheet (one per participant)

| Participant | Role they play | Task 1: test case writable? (Y/N, notes) | Task 2: time / success | Task 3: affected set found? | Confidence 1–5 | Quotes |
|---|---|---|---|---|---|---|
| P1 | | | | | | |
| P2 | | | | | | |
| P3 | | | | | | |
| P4 | | | | | | |
| P5 | | | | | | |

## 4. Gap log (fill during the debrief, same day)

Every problem seen by two or more participants, or once if it blocks a task, becomes a row — and a
comment on the story it belongs to, before that story is built.

| # | What happened | Seen by | Severity (blocks / slows / cosmetic) | Story | Proposed change | Owner |
|---|---|---|---|---|---|---|
| | | | | | | |

## 5. Summary for the sprint review

- Sessions held: __ / 5 · Task 2 median time: __ (target < 5 min) · Task 1 "test case writable": __ / __
- Top three gaps and the stories they were logged against: …
