# Project Overview

**AI Requirements Conflict Detector — a collaborative requirements workspace**

| | |
|---|---|
| **Course** | IT314 — Software Engineering, Autumn 2026–27 |
| **Team** | 10 members |
| **Scope** | Revision 5 — [`IT314_RCD_Scope_Extension_v5.md`](../planning/v5/IT314_RCD_Scope_Extension_v5.md) |
| **Status** | Sprint 1 in progress (see `project-status.md`) |

---

## 1. Problem Statement

Requirements are written by many stakeholders over time. They accumulate recurring, hard-to-catch problems in a 5-category taxonomy (ADR-02):

- **Conflicting** — two or more requirements cannot reasonably be satisfied together under the same stated context.
- **Duplicate** — near-identical requirements restated in different words.
- **Ambiguous** — vague quantifiers or missing acceptance criteria (e.g. "fast", "user-friendly").
- **Incomplete** — a requirement missing information needed to implement or verify it.
- **Dependent** — one requirement's satisfaction relies on another.

Manually cross-checking every pair does not scale (an O(n²) problem). Worse, real requirements work is not one document analysed once: requirements arrive one at a time in meetings and chats, change after sign-off, and belong to different people. Late changes that nobody affected was told about cause the most expensive defects.

## 2. The Product

The original scope was *upload one SRS, extract requirements, classify conflicts, review findings*. Step 7 widened it into a **collaborative requirements workspace**:

- A project manager creates a **workspace** and **projects**; others **join with a code** and get a **role** (nine defaults plus custom roles) that decides which actions they can take.
- Every project starts with **compulsory context**: an initial SRS, a brief, or both, confirmed by the PM. Every LLM prompt carries a bounded context pack.
- Requirements are written in an **EARS composer** with live lint and a pre-flight check, and every add or change is **analysed incrementally** against the agreed baseline.
- The **live requirements map** updates for everyone within 2 seconds, with every change also written as a sentence.
- When a problem involves two people's requirements, the system works like GitHub: a **requirement issue** assigned to both, **AI-suggested solutions** that people accept, edit or reject, and a **pull-request-style change request** with diff, checks, reviews and merge.
- The **trust layer**: human-raised concerns beside AI and rule findings, exact agreement rules, a findings delta on every change, decision owners per issue type, and rule-based cross-checks for conflicts the similarity filter misses.
- Every project ends with an **LLM-written, human-approved updated SRS**: requirement text inserted verbatim by the system, narrative by the LLM, a fidelity check before publishing, exported as DOCX, PDF or Markdown.

**Positioning (rev. 4):** collaborative creation and resolution is the main story; importing an existing SRS is the onboarding path.

## 3. Objectives

- Detect conflicting, duplicate, ambiguous, incomplete and dependent requirements, with confidence, severity and rationale, at upload time **and** at the moment a requirement is written or changed.
- Keep humans in charge: the AI never deletes, merges or alters requirement text (DR-04, DR-14); approved requirements change only through a reviewed change request.
- Tell the right people: affected owners are named, reviewers are requested by decision rules, and every change is visible on the map and in writing.
- Be honest about limits: "no issue detected" never reads as "verified" (DR-21); recall is measured, including conflicts below the similarity threshold (NFR-37).
- Deliver in 14 weeks with 10 people: Sprint 0, six 2-week sprints, a release week; 224 scheduled points.

## 4. Scope

### In scope for the semester MVP

Scheduled stories by module (full list in `feature-catalog.md`):

| Module | Stories |
|---|---|
| Foundation, ingestion and context | US-19, US-01–US-04, US-60 |
| Workspace, joining and roles | US-24–US-29, US-49 |
| Detection engine | US-05, US-07, US-06, US-58 |
| Review and triage | US-09, US-10, US-56, US-08, US-15 |
| Authoring and actions | US-30, US-31, US-36, US-37, US-51, US-53 |
| Issues, suggestions and change requests | US-52, US-33, US-34, US-35, US-45, US-57, US-11, US-12 |
| Live map | US-14, US-50, US-55 |
| Notifications, dashboard, baselines | US-38, US-42, US-13, US-40 |
| Updated SRS and compliance | US-61, US-41, US-59, US-18 |
| Validation | US-22 |

### Out of scope for the semester MVP

- SSO/LDAP, Jira/Confluence/GitHub sync, a public REST API, executive ROI reports (EP-09).
- Email digests and email invitations (joining uses codes and links; no SMTP).
- Report export (US-16), chat detection (US-32), extra analytics (US-44) — deferred in rev. 4.
- Work-item links (US-48) — deferred in rev. 5 to make room for the updated SRS.
- Q&A over the baseline, workspace search, meeting-notes import, structural change requests.
- Voice or video, direct messages, native mobile apps.
- Automatic edits of requirement text by the AI: **never**.

## 5. Tech Stack

| Layer | Choice |
|---|---|
| Frontend | React (Vite) + TypeScript, Tailwind CSS + shadcn/ui, TanStack Query; map library chosen by the Sprint 0 spike (Cytoscape.js vs React Flow, NFR-33) — React Flow is installed from the original scaffold |
| Backend | FastAPI (Python), Pydantic, SQLAlchemy, Alembic, Celery + Redis |
| Real-time | WebSocket in the API process, fan-out via Redis pub/sub; REST is the only write path (ADR-15) |
| AI / NLP | LLM via an `LLMClient` adapter (Google Gemini, Groq as backup), Sentence-Transformers (BAAI/bge-small-en-v1.5), pgvector |
| Ingestion | PyMuPDF (PDF), python-docx (Word), spaCy (segmentation) |
| Database / Infra | PostgreSQL + pgvector, Redis, Docker Compose, GitHub Actions; Railway/Render, Vercel |
| Testing | Pytest (backend), Vitest + React Testing Library (frontend), Playwright (E2E), load tests |

*Key architecture decision: an embedding pre-filter instead of brute-force all-pairs LLM comparison (ADR-01), complemented in rev. 4 by rule-based cross-checks that run regardless of similarity (ADR-27). See `decision-log.md`.*

## 6. Why This Project Was Chosen

Selected from a shortlist of 100+ candidate SE project ideas, ranked by placement/resume value, one-semester feasibility and room to extend, with rankings merged across the original team members.

| Alternative considered | Hardness | Why rejected |
|---|---|---|
| AI-Powered Software Development Platform | 8/10 | Too broad unless scoped to 2–3 features |
| Collaborative Code Editor + Sandboxed Execution | 9/10 | CRDT sync + secure Docker sandboxing — hardest on the list |
| Multi-Agent Research & Lit Review Assistant | 7.5/10 | Multi-agent debugging risk |
| Bug Reproduction & Triage Assistant | — | Lower resume/placement differentiation |
| Distributed API Health & Incident Monitoring Dashboard | — | Less novel, more commoditized problem space |

The original detector was rated ~6/10 hardness — the safest bet to finish polished in one semester. Step 7 widened it to suit a 10-person team (see [`IT314_RCD_Scope_Extension_v5.md` §6](../planning/v5/IT314_RCD_Scope_Extension_v5.md#6-why-this-suits-a-10-person-semester)) while keeping the detection engine as the core.
