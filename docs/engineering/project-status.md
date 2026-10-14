# Project Status

**AI Requirements Conflict Detector — Live Dashboard**

| | |
|---|---|
| **Course** | IT314 — Software Engineering, Autumn 2026–27 |
| **Team size** | 10 members — Backend 5, Frontend 3, Testing 2 ([`../sprint-plan.md`](../sprint-plan.md)) |
| **Current phase** | Sprint 0 merged; Sprint 1 (Weeks 3–4) in review |
| **Last updated** | 2026-10-14 |

---

## 1. Status at a Glance

| Metric | Value | Note |
|---|---|---|
| Overall phase | Building | Sprint 0 foundation on `main`; Sprint 1 PRs open (#7 upload, #8 extraction, #17 frontend tests) |
| Sprints defined | 6 (+ Sprint 0 setup) | Weeks 1–14 |
| Total backlog stories | 23 (US-01–US-23) | US-23 is outcome-only, no dev task |
| Stories scheduled in MVP sprints | 19 | Sprints 1–5 |
| Stories deferred (post-MVP) | 3 | US-17, US-20, US-21 |
| Total story points (scheduled) | 94 | Sprints 1–5 combined |
| Functional requirements | 42 (FR-01–FR-42) | Lab 6 numbering is canonical (CR-21) |
| Non-functional requirements | 23 (NFR-01–NFR-23) | Per Lab 6 numbering |
| Domain requirements | 12 (DR-01–DR-12) | Per Lab 6 numbering |
| Stakeholder groups | 10 | 8 complete, 2 ongoing by design |
| Integration checkpoints | 2 | Week 7 (core pipeline) · Week 11 (UI + real docs) |

## 2. Sprint Burn-Down Plan

| Sprint | Weeks | Goal | Points | Status |
|---|---|---|---|---|
| Sprint 0 — Setup | 1–2 | Repo scaffold, DB schema, Docker Compose, wireframes | 0 | ✅ Done: schema + migration, JWT auth, Compose, CI, ingestion parsers, upload wireframe, benchmark SRS |
| Sprint 1 — Foundation | 3–4 | Upload + extraction working | 13 | 🔄 In review: PR #7 (US-01), PR #8 (US-02) |
| Sprint 2 — Core Detection | 5–7 | Classification pipeline (Checkpoint 1) | 26 | Not started |
| Sprint 3 — Review & Impact | 8–9 | Human-in-the-loop + impact analysis | 21 | Not started |
| Sprint 4 — Dashboard & Tuning | 10–11 | Visual layer (Checkpoint 2) | 18 | Not started |
| Sprint 5 — Harden & Ship | 12–13 | Testing, feedback loop, deployment | 16 | Not started |
| Sprint 6 — Demo Prep | 14 | Polish only, no new stories | 0 | Not started |

> Sprint 2 carries the heaviest load (26 pts over 3 weeks vs. ~18–21 pts elsewhere) because US-05 (5-category classification, 13 pts) is the highest-risk item in the backlog and is deliberately front-loaded. See `decision-log.md` for the reasoning.

## 3. Team & Sprint 0 Check

Owners and key stories are from [`../sprint-plan.md`](../sprint-plan.md). The Sprint 0 column compares each person's Sprint 0 task with what is on GitHub as of 2026-10-14. Work that exists only on someone's laptop doesn't count until it's pushed.

| Person | Owns | Key stories | Sprint 0 task | On GitHub |
|---|---|---|---|---|
| Bansil | Ingestion | US-02 | Ingestion scaffold, parser choice | ✅ #4 merged |
| Heet | Embeddings | US-05 (pre-filter), US-06 | Set up pgvector, benchmark embedding model | ⚠️ Nothing pushed. pgvector is enabled by Parth's migration; no model benchmark yet |
| Keval | Classification | US-05, US-07, US-06 | Draft LLM prompts, Pydantic output schemas | ⚠️ Not delivered: `classification/` holds only stubs. PR #5 is a separate full-repo scaffold, superseded by #6 and conflicting |
| Madhav | Clarification & impact | US-09, US-11, US-08, US-15 | Design clarification/impact data model | ✅ #9 merged |
| Parth | API, auth, orchestration | US-01, US-19, US-10, US-12, US-18 | Repo, Compose, schema, auth, CI | ✅ #1–#3, #6 merged |
| Pranshu | Upload & list UI | US-01/US-04 UI, US-03, US-13 | Upload + requirements-list wireframes | 🟡 Upload wireframe merged (#11, #14, #15); requirements-list wireframe is in #12 |
| Abhijeet | Findings & review UI | US-05/07/09/10 UI, US-08 | Findings/review wireframes | 🔄 #12 open, conflicting (edits the old `docs/Wireframes` file; its PDF exports are missing) |
| Dhvani | Graph, DevOps | US-14, US-11 UI, US-16 | Dashboard/graph wireframes, CI review | ⚠️ Nothing pushed |
| Abhyudit | Backend testing | — | pytest structure, planted-conflict SRS | ✅ #13, #16 merged |
| Affan | Frontend testing | US-22 | Vitest structure, QA checklist template | 🔄 #17 open, changes requested |

**Sprint 0 is 5 of 10 done.** The gaps that block later sprints are Keval's prompts and schemas and Heet's embedding choice, which Sprint 2 (US-05, 13 points) depends on, and Dhvani's and Abhijeet's wireframes, which Sprints 2–4 UI depends on.

## 4. Risks Being Watched

- **Sprint 2 velocity** — 26 points is above the other sprint loads. If Sprint 1 velocity lands below ~18–20 pts, US-07 is the agreed item to push into Sprint 3.
- **Sprint 0 carry-over** — Keval (prompts, schemas) and Heet (embedding model) have no Sprint 0 output on GitHub, and both own the 13-point US-05 in Sprint 2. Ask for draft PRs early in Sprint 1. Close PR #5, which duplicates #6.
- **Open-PR backlog** — five PRs are open (#5, #7, #8, #12, #17), and #7 and #8 both touch ingestion and storage. Merge #7 first, then rebase #8, so the `process_document` contract and migration `0003` (see `../ingestion-design.md`) land in order.
- **Severity levels** — US-08/FR-42 say Low/Medium/High, but the `Severity` enum also has `critical`. Decide before Sprint 4 (T44).
- **Clarification/impact schema** — `../clarification-impact-design.md` proposes 1:N clarifications and a `requirement_impact_links` table. Both are pending approval, and Sprint 3 depends on the decision.
- **ML depth** — the fine-tuned embedding model is recommended but not yet committed (`decision-log.md`).
- **Resolved:** the FR/NFR/DR numbering mismatch and the DR-01 taxonomy wording (`requirements-spec.md`, Section 0).

## 5. Document Index

See `INDEX.md` for the full master index and change-impact matrix. This dashboard is a summary view only — it does not duplicate detail owned by the other documents.
