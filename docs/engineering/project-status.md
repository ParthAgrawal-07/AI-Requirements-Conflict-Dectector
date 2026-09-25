# Project Status

**AI Requirements Conflict Detector — Live Dashboard**

| | |
|---|---|
| **Course** | IT314 — Software Engineering, Autumn 2026–27 |
| **Team size** | 7 members |
| **Current phase** | Planning complete — Sprint 0 (Weeks 1–2) not yet started |
| **Last updated** | Week 0 (pre-Sprint 0) |

---

## 1. Status at a Glance

| Metric | Value | Note |
|---|---|---|
| Overall phase | Planning | Requirements, backlog, sprint plan finalized; no code written yet |
| Sprints defined | 6 (+ Sprint 0 setup) | Weeks 1–14 |
| Total backlog stories | 23 (US-01–US-23) | US-23 is outcome-only, no dev task |
| Stories scheduled in MVP sprints | 19 | Sprints 1–5 |
| Stories deferred (post-MVP) | 3 | US-17, US-20, US-21 |
| Total story points (scheduled) | 94 | Sprints 1–5 combined |
| Functional requirements | 41 (FR-01–FR-41) | Per Lab 6 numbering |
| Non-functional requirements | 23 (NFR-01–NFR-23) | Per Lab 6 numbering |
| Domain requirements | 12 (DR-01–DR-12) | Per Lab 6 numbering |
| Stakeholder groups | 10 | 8 complete, 2 ongoing by design |
| Integration checkpoints | 2 | Week 7 (core pipeline) · Week 11 (UI + real docs) |

## 2. Sprint Burn-Down Plan

| Sprint | Weeks | Goal | Points | Status |
|---|---|---|---|---|
| Sprint 0 — Setup | 1–2 | Repo scaffold, DB schema, Docker Compose, wireframes | 0 | Not started |
| Sprint 1 — Foundation | 3–4 | Upload + extraction working | 13 | Not started |
| Sprint 2 — Core Detection | 5–7 | Classification pipeline (Checkpoint 1) | 26 | Not started |
| Sprint 3 — Review & Impact | 8–9 | Human-in-the-loop + impact analysis | 21 | Not started |
| Sprint 4 — Dashboard & Tuning | 10–11 | Visual layer (Checkpoint 2) | 18 | Not started |
| Sprint 5 — Harden & Ship | 12–13 | Testing, feedback loop, deployment | 16 | Not started |
| Sprint 6 — Demo Prep | 14 | Polish only, no new stories | 0 | Not started |

> Sprint 2 carries the heaviest load (26 pts over 3 weeks vs. ~18–21 pts elsewhere) because US-05 (5-category classification, 13 pts) is the highest-risk item in the backlog and is deliberately front-loaded. See `decision-log.md` for the reasoning.

## 3. Team & Module Ownership

| Role | Owns | Key stories |
|---|---|---|
| 1 — Document Ingestion | PDF/Word parsing, sentence segmentation | US-01, US-02, US-04 |
| 2 — Embedding & Similarity Search | Sentence-Transformers, pgvector, threshold tuning | US-06 |
| 3 — LLM Classification Pipeline | Prompt design, classification, output validation | US-05, US-07 |
| 4 — Clarification & Impact Analysis | Clarification generation, change-impact analysis | US-09, US-11, US-12 |
| 5 — Backend API & Orchestration | FastAPI, Celery/Redis, auth, end-to-end wiring | US-03, US-19 |
| 6 — Frontend, Core UI | Upload flow, requirements list, findings UI | US-08, US-10, US-15 |
| 7 — Frontend Visualization & DevOps | React Flow graph, Docker, CI/CD, deployment | US-13, US-14, US-16 |

## 4. Risks Being Watched

- Sprint 2 velocity — 26 points is above the team's other sprint loads; if Sprint 1 velocity lands below ~18–20 pts, US-07 is the agreed item to push into Sprint 3.
- Numbering mismatch between the Consolidated Requirements Baseline and the official Lab 6 submission (FR/NFR/DR numbering) is not yet reconciled — tracked in `requirements-spec.md`.
- Advanced/ML depth decision (fine-tuned embedding model) is recommended but not yet committed by the team — tracked in `decision-log.md`.

## 5. Document Index

See `INDEX.md` for the full master index and change-impact matrix. This dashboard is a summary view only — it does not duplicate detail owned by the other documents.
