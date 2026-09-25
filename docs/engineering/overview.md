# Project Overview

**AI Requirements Conflict Detector**

| | |
|---|---|
| **Course** | IT314 — Software Engineering, Autumn 2026–27 |
| **Team** | 7 members |
| **Status** | Planning complete, pre-Sprint 0 |

---

## 1. Problem Statement

Software Requirements Specification (SRS) documents are written by multiple stakeholders over time. This introduces recurring, hard-to-catch problems across a 5-category taxonomy:

- **Conflicting** — two or more requirements cannot reasonably be satisfied together under the same stated context.
- **Duplicate** — near-identical requirements restated in different words.
- **Ambiguous** — vague quantifiers or missing acceptance criteria (e.g. "fast", "user-friendly").
- **Incomplete** — a requirement missing information needed to implement or verify it.
- **Dependent** — one requirement's satisfaction relies on another.

Manually cross-checking every requirement pair does not scale as SRS size grows — this is an O(n²) comparison problem for a human reviewer. The project builds a tool that pre-filters and classifies candidate pairs automatically, with a human always making the final call.

## 2. Objectives

- Detect conflicting, duplicate, ambiguous, incomplete, and dependent requirements automatically, with confidence scores and rationale.
- Keep humans in the loop — the system never silently deletes, merges, or alters requirement text.
- Generate clarification questions for flagged issues that a QA engineer or business analyst can act on without needing to understand the underlying model.
- Support change-impact analysis so editing one requirement surfaces everything else it may affect.
- Stay within a 14-week, one-semester delivery window without sacrificing the core detection capability.

## 3. Scope

### In scope for the semester MVP

- Upload → extraction → segmentation of SRS documents (PDF, DOCX, plain text)
- Embedding-based candidate-pair pre-filter (pgvector) ahead of LLM classification
- LLM classification into the 5-category taxonomy with confidence + rationale
- Human review workflow: confirm, dismiss, merge, reclassify
- Clarification question generation
- Change-impact analysis and requirement version history
- Quality dashboard and dependency/conflict graph
- Multi-channel export (dashboard, PDF/CSV, scheduled digest)

### Explicitly out of scope for the semester MVP

- SSO (enterprise identity federation) — JWT auth only for MVP
- Jira / Confluence / GitHub integration
- Public, documented REST API for third-party consumers
- Compliance tagging beyond the basic "protected requirement" flag

*These are retained in the backlog and requirements as stretch/industry-extension items to show awareness of a fuller deployment picture, not because the team plans to build them this semester.*

## 4. Tech Stack

| Layer | Choice |
|---|---|
| Frontend | React (Vite) + TypeScript, Tailwind CSS + shadcn/ui, React Flow, TanStack Query |
| Backend | FastAPI (Python), Pydantic, SQLAlchemy/SQLModel, Celery + Redis |
| AI / NLP | Anthropic Claude API / OpenAI API, Sentence-Transformers (all-MiniLM-L6-v2), pgvector |
| Ingestion | PyMuPDF (PDF), python-docx (Word), spaCy (segmentation) |
| Database / Infra | PostgreSQL + pgvector, Redis, Docker Compose, Railway/Render, Vercel, GitHub Actions |
| Testing | Pytest (backend), Vitest + React Testing Library (frontend) |

*Key architecture decision: an embedding pre-filter was deliberately chosen over brute-force all-pairs LLM comparison, cutting LLM calls by an estimated 70%+. See `decision-log.md`.*

## 5. Why This Project Was Chosen

Selected from a shortlist of 100+ candidate SE project ideas, ranked by placement/resume value, one-semester feasibility, and room to extend, with rankings merged across all 7 team members.

| Alternative considered | Hardness | Why rejected |
|---|---|---|
| AI-Powered Software Development Platform | 8/10 | Too broad unless scoped to 2–3 features |
| Collaborative Code Editor + Sandboxed Execution | 9/10 | CRDT sync + secure Docker sandboxing — hardest on the list |
| Multi-Agent Research & Lit Review Assistant | 7.5/10 | Multi-agent debugging risk |
| Bug Reproduction & Triage Assistant | — | Lower resume/placement differentiation |
| Distributed API Health & Incident Monitoring Dashboard | — | Less novel, more commoditized problem space |

The AI Requirements Conflict Detector was rated ~6/10 hardness — the safest bet to finish polished within one semester while still solving a real, textbook requirements-engineering problem rather than "just another AI wrapper".
