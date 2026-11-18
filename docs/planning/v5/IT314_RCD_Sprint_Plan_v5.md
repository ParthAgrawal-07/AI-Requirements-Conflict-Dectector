# Sprint Plan and Work Assignment

**14-week semester plan for a 10-member team — AI Requirements Conflict Detector (collaborative workspace scope, revision 5)**

| | |
|---|---|
| **Replaces** | `Sprint_Plan` and `Sprint_Work_Assignment` (the old 6-sprint, 94-point plan) and revisions 1–4 of this file |
| **Cadence** | Sprint 0 (1 week), Sprints 1–6 (2 weeks each), Sprint 7 release week (1 week) = 14 weeks |
| **Scheduled work** | **224 points** across Sprints 1–6: 37 · 38 · 37 · 37 · 38 · 37 |
| **Revision 5.1 (rebalanced ownership)** | From Sprint 3, work is divided **by feature, not by layer**: each owner builds a feature's backend, UI and tests, testers also own features, and code lines across Sprints 2–6 are balanced to within about ±5% per person (§2.1). Points and scope are unchanged |
| **Revision 5 (context and updated SRS)** | Adds **US-60** project context compulsory before analysis (initial SRS or brief; context pack in every prompt; S1) and **US-61** LLM-generated updated SRS with section review and fidelity check (S6). US-41 now exports the published SRS. Defers **US-48** work-item links |
| **Revision 4 (trust review)** | Adds human-raised concerns (US-56, S4), decision rules (US-57, S5), rule-based cross-checks (US-58, S5) and the open-items report (US-59, S6). Defers report export (US-16), chat detection (US-32) and extra analytics (US-44): no new charts or AI features until the core workflow is proven |
| **Checkpoints** | **CP1 end of Week 7** (after Sprint 3) · **CP2 end of Week 11** (after Sprint 5) · **Final demo Week 14** |
| **Source of truth** | Story details in `IT314_RCD_Product_Backlog_v5.md`; epics, cut order and gaps in `IT314_RCD_Epics_v5.md`; screens in `IT314_RCD_Interface_Design_v5.md` |

---

## 1. Calendar

| Sprint | Weeks | Goal | Points | Ends with |
|---|---|---|---|---|
| **S0** | 1 | Re-baseline: tenancy and permission migration, spikes (WebSocket, map library), contracts, wireframes, benchmark plan | 0 (enablers) | Contracts signed off; `docker compose up` with the new schema |
| **S1** | 2–3 | Join by code, roles, workspaces and projects **with compulsory context**, upload and extract an SRS | 37 | Demo: PM creates a project with its initial SRS or brief → creates a code → developer joins → sees requirements |
| **S2** | 4–5 | Detection engine, real-time channels, custom roles | 38 | Demo: findings with confidence on the planted SRS; live chat |
| **S3** | 6–7 | Requirement composer, live analysis, **live map**, review | 37 | **CP1** |
| **S4** | 8–9 | **Issues (AI and human-raised) and PR-style change requests**, findings delta, agreement rules, versions | 37 | Demo: conflict issue + a raised concern → change request → findings delta → review → merge |
| **S5** | 10–11 | **AI suggestions with structured feedback**, **decision rules**, **rule-based cross-checks**, notifications, dashboard, baselines, lint and pre-flight | 38 | **CP2** |
| **S6** | 12–13 | **Written change log**, map preview and time slider, **LLM-generated updated SRS** with review, export + **open-items report**, compliance, severity, votes | 37 | Feature freeze at the end of Week 13 |
| **S7** | 14 | Release: bug bash, deployment freeze, demo data, rehearsal, final report | 0 | **Final demo** ends with the published updated SRS exported |

## 2. Team and Areas of Ownership

### 2.1 From Sprint 3: features, not layers

The team divided Sprints 3–6 again so that everyone writes about the same amount of code and carries about
the same load. The rules:

1. **One owner per feature.** The owner writes its API, database work, screen and unit tests. Nobody is
   frontend-only or backend-only.
2. **Large stories are split by feature, not by layer.** For example US-14 is *live updates* (Dhavni didi)
   and *map view* (Abhijeet); US-35 is *reviews* (Heet), *merge and agreement guard* (Parth) and *merge box* (Affan).
3. **Testers keep their test plan and also own features.** Abhyudit and Affan each own fewer features
   because the checkpoint reports, E2E, load and security work stay with them.
4. **Area owners review.** Parth reviews every migration and permission change, Keval every LLM call and
   prompt, Dhavni didi real-time events and CI, Pranshu the app shell and shared styles.
5. **Balance.** Code lines added in Sprints 2–6 (measured from the per-person sprint commits; docs, JSON and
   CSV excluded) come out within about ±5% of the average (≈6,580 lines per person). Sprints 0–1 are not
   counted because they were not committed per person.
6. **Merge order follows dependencies.** Each sprint's work ships as one PR per owner, in the order in
   `SprintN-zips/MERGE_ORDER.md`. Testers open a feature PR mid-sprint and a `-tests` PR last. Heet has a
   second PR in S4 (reviews, after Madhav's migration) and in S6 (change-log UI and tests, after Dhavni's map
   history), because his work sits on both sides of someone else's.

| Member | S2 (done) | S3 | S4 | S5 | S6 | Total | vs average |
|---|---|---|---|---|---|---|---|
| Parth | 2,659 | 1,184 | 1,344 | 1,571 | 0 (integration, release prep) | 6,758 | +2.7% |
| Dhavni didi | 1,504 | 1,630 | 1,493 | 652 | 1,459 | 6,738 | +2.4% |
| Bansil | 868 | 873 | 1,561 | 979 | 2,061 | 6,342 | −3.6% |
| Pranshu | 1,215 | 1,692 | 815 | 890 | 2,094 | 6,706 | +1.9% |
| Heet | 345 | 617 | 1,720 | 1,607 | 2,202 | 6,491 | −1.4% |
| Keval | 1,369 | 1,329 | 455 | 1,916 | 1,283 | 6,352 | −3.5% |
| Madhav | 1,566 | 1,157 | 1,681 | 1,897 | 445 (security tests with Affan) | 6,746 | +2.5% |
| Abhijeet | 1,310 | 1,288 | 1,363 | 1,091 | 1,485 | 6,537 | −0.7% |
| Abhyudit | 371 | 800 | 1,144 | 1,909 | 2,295 | 6,519 | −0.9% |
| Affan | 196 | 1,711 | 1,098 | 745 | 2,870 | 6,620 | +0.6% |

### 2.2 Roles from Sprint 3

| Member | Role | Features they own (backend + UI + tests) | Also |
|---|---|---|---|
| **Parth** | Backend lead, integration lead | US-37 lifecycle and the review/lifecycle tables · US-35 merge, needs-update, agreement guard · US-57 decision rules engine | Reviews every migration and permission change; S6 integration and release prep |
| **Dhavni didi** | Real-time, map backend, DevOps | US-14 graph revisions, deltas, narrator · US-52 auto conflict issues · US-50 preview layer, revisions, history · US-55 changes API | S5 load test; CI/CD, Docker, deployment |
| **Bansil** | Authoring and the updated SRS | US-36 owners and ownership requests · US-33 change editor · US-51 authoring panel · US-45 change request from a suggestion · US-61 SRS generation, readiness, fidelity check, publishing · US-41 DOCX, PDF and Markdown exporters | Scrum Master S3; demo data S7 |
| **Pranshu** | Composer, change requests, baselines, SRS review | US-30 composer · US-33 change-request list and page · US-40 baselines · US-61 SRS API, section review and SRS screen · US-41 export API | App shell, component kit, shared styles; Scrum Master S4 |
| **Heet** | Retrieval, impact, reviews, change log | US-31 retrieval and hints · US-11 impact and relationship queries · US-35 reviews · US-58 rule checks · US-06 thresholds · US-55 change-log backend, Changes panel and tests · US-50 time slider | Scrum Master S5 |
| **Keval** | LLM and AI quality | US-31 classification, budget, result card · US-34 narrative · US-51 lint, pre-flight, AI wording · US-58 attribute extraction · US-45 prompts · US-15 feedback loop · US-55 summary · US-61 section prompts | Reviews every LLM call; Scrum Master S6 |
| **Madhav** | Clarification and consequences | US-09 clarification questions · US-34 consequence checks and Checks tab · US-45 suggestion service | S6 injection and rate-limit tests with Affan; Scrum Master S7 |
| **Abhijeet** | Map UI, issues, notifications, compliance | US-14 map UI and live updates · US-52 issue API, list, page, comments · US-38 notifications, inbox, bell · US-18 compliance | Demo script S7 |
| **Abhyudit** | Testing (accuracy, backend) + features | US-31 requirement runs · US-56 raise a concern · US-13 dashboard · US-45 suggestion panel · US-42 timeline · US-59 open-items report · US-08 severity and severity sort | CP1 and CP2 accuracy and recall reports, regression, SRS fidelity tests |
| **Affan** | Testing (E2E, performance, security) + features | US-10 finding review · US-12 version history · US-35 merge box · US-57 decision owners and settings page · US-53 discussion, votes, watch, links and link edges on the map | CP1 and CP2 E2E, merge-rule tests, security, accessibility, smoke; bug bash lead |

### 2.3 Areas in Sprints 0–2

Each member owned one primary area as code owner and reviewer. Everyone writes unit tests for their own code.

| Member | Primary area | Also | Code they own |
|---|---|---|---|
| **Parth** | Backend lead: auth, memberships, **permissions and roles**, review state, lifecycle, approvals and merge, versions, baselines, audit | Reviews all migrations; integration lead | `app/core/auth`, `app/services/{membership,roles,change_requests,approvals,baselines}`, `alembic/` |
| **Dhavni didi** | DevOps and real-time: Docker, CI/CD, Celery, WebSocket gateway, event bus, **graph API and graph deltas**, issues backend, deployment | Report service (US-16), timeline (US-42) | `app/realtime/`, `app/graph/`, `app/services/issues.py`, `.github/`, `docker/` |
| **Bansil** | Ingestion and authoring: extraction, **project context**, requirement posts and drafts, ownership, change-request intake, votes, watches and links, **updated SRS generator** and export | Composer wiring of lint and pre-flight (US-51), chat promotion (US-32) | `app/ingestion/`, `app/intake/`, `app/export/` |
| **Pranshu** | Frontend lead: shell, login, channels, composer, requirements table, issues UI, dashboard, baselines, map preview and time slider, analytics | Component kit and design system | `frontend/src/{app,features/channels,composer,requirements,issues,dashboard,baselines,analytics}` |
| **Heet** | Embeddings and retrieval: vector store, candidates, incremental retrieval, similar-requirement hints, relationship queries, search | Analytics metrics (US-44) | `app/embeddings/`, `app/search/` |
| **Keval** | Classification and LLM: clients, prompts, **context pack**, classifier, severity, budget, **lint pattern catalogue, pre-flight and AI wording**, SRS section prompts | Prompt-injection defences | `app/classification/`, `app/lint/` |
| **Madhav** | Clarification and consequences: questions, impact engine, consequence checks, risk, notifications, **join codes backend**, **AI resolution suggestions (US-45)** | E2E help in S6 | `app/clarification/`, `app/consequences/`, `app/notifications/`, `app/services/join_codes.py` |
| **Abhijeet** | Frontend: members, roles and join codes UI, **project setup wizard**, findings and review, **live map UI**, change editor and change-request page, inbox, compliance UI | Low-fidelity prototypes (US-22) | `frontend/src/features/{members,findings,review,map,changes,notifications,compliance}` |
| **Abhyudit** | QA — accuracy and backend: benchmark, evaluation harness, API and database tests | Usability sessions (US-22) | `eval/`, `backend/tests/` (integration) |
| **Affan** | QA — E2E, performance, security: Playwright, permission tests, join-code abuse tests, WebSocket and load tests, accessibility | Usability sessions, release checklist | `e2e/`, `load/` |

**Scrum roles.** The Scrum Master rotates: Parth (S0–S1), Dhavni didi (S2), Bansil (S3), Pranshu (S4), Heet (S5), Keval (S6), Madhav (S7). The team names one fixed **Product Owner proxy** for the semester; this plan does not presume who.

## 3. Sprints in Detail

### Sprint 0 · Week 1 · Re-baseline (enablers, 0 points)

| Member | Tasks |
|---|---|
| Parth | Migrations `0003` (severity, `escalated`) and `0004` (projects, memberships, **roles and permissions** with the 9 defaults seeded); `require_permission()` skeleton; existing RBAC and isolation tests passing on it |
| Dhavni didi | WebSocket + Redis pub/sub spike; **map library spike with Abhijeet** (Cytoscape.js vs React Flow, 500 nodes / 2,000 edges, NFR-33); `graph.delta` event schema; Compose and CI for new packages |
| Bansil | Composer field schema and draft model with Pranshu; EARS template definitions with Keval; **project brief schema** (required and optional fields); G3 plan |
| Pranshu | App shell, routing, component kit (buttons, badges with icon + text, drawer, tabs); start login and sign-up-with-code screens |
| Heet | Confirm embedding model; measure similar-requirement hint latency (target < 500 ms server time); draft `analyse_text()` contract |
| Keval | `LLMClient` adapter; prompt v1 with delimited inputs and a **context-pack slot**; **lint pattern catalogue v1** (shared with DR-07); `BudgetGuard` design |
| Madhav | Join code design (format, hashing, limits, approval); `ImpactReport` and checks schema |
| Abhijeet | Wireframes from `IT314_RCD_Interface_Design_v5.md` turned into clickable prototypes for US-22; map spike with Dhavni didi |
| Abhyudit | Benchmark v2 plan: planted-conflict SRS, 40 post-style requirements, 10 scripted change requests with known affected sets and owners |
| Affan | Playwright skeleton in CI; **permission test matrix** (permission × role) generated from the catalogue |

**Exit criteria:** the contracts in `IT314_RCD_Design_Update_v5.md` §6 agreed in writing; `docker compose up` works with the new schema; an event reaches sockets on two API processes; the map library is chosen; Step 7 decisions sent to stakeholders (`IT314_RCD_Scope_Extension_v5.md` §11).

### Sprint 1 · Weeks 2–3 · Joining, roles, ingestion (34 points)

| Story | Pts | Owners |
|---|---|---|
| US-19 Authenticate via JWT (sign-up only with a code) | 5 | Parth, Pranshu |
| US-27 Enforce roles and permissions | 5 | Parth, Affan |
| US-24 Create a workspace and projects | 3 | Parth, Abhijeet |
| US-60 **Project context required before analysis** | 3 | Bansil, Abhijeet, Keval |
| US-25 Join a workspace with a code or invite link | 5 | Madhav, Abhijeet |
| US-01 Upload SRS into a project | 5 | Parth, Pranshu |
| US-02 Automatic requirement extraction | 5 | Bansil |
| US-03 Track analysis progress | 3 | Dhavni didi, Pranshu |
| US-04 View extracted requirements | 3 | Parth, Pranshu |

**Enablers:** Heet — embedding stage; Keval — classifier skeleton and retries; Dhavni didi — event bus; Abhyudit — label the benchmark; Affan — E2E *create code → join → upload*, join-code brute-force test.
**Exit criteria:** a project cannot be analysed until its PM uploads an initial SRS or confirms a brief; AI-drafted brief fields are labelled until confirmed; a PM creates a code; a developer signs up with it, gets the Developer role, uploads the planted SRS and sees its requirements with printed IDs; the permission matrix test passes.

### Sprint 2 · Weeks 4–5 · Detection engine, channels, custom roles (38 points)

| Story | Pts | Owners |
|---|---|---|
| US-05 Detect requirement issues (tasks 5a, 5b, 5c) | 13 | Keval, Heet, Abhyudit |
| US-07 Explain findings with confidence and context | 5 | Keval, Abhijeet |
| US-26 Remove members, change roles, leave | 3 | Parth, Abhijeet |
| US-49 Custom roles and permission sets | 3 | Parth, Abhijeet |
| US-28 Create and manage channels | 3 | Madhav, Pranshu |
| US-29 Real-time messaging with threads and mentions | 8 | Dhavni didi, Pranshu |
| US-22 Low-fidelity validation sessions | 3 | Abhyudit, Affan, Abhijeet |

**US-05 milestones:** 5a conflicts by day 4 · 5b duplicates and ambiguous by day 7 · 5c incomplete and dependent by day 9.
**Enablers:** Parth — per-pair classification status (G1), orchestration; Bansil — post backend and drafts, G3 cleanup; Dhavni didi — graph API v0 (`GET /graph`) from stored findings; Madhav — clarification prompt drafts.
**Midpoint rule:** if 5a is not done by day 5, move US-07, US-49 and US-22 to Sprint 3.
**Exit criteria:** findings with confidence on the planted SRS; first precision/recall numbers; two browsers chat in real time; a custom role "Client reviewer" can review but not propose.

### Sprint 3 · Weeks 6–7 · Composer, live analysis, live map (37 points) → **CP1**

| Story | Pts | Owners |
|---|---|---|
| US-30 Requirement composer with EARS templates | 5 | Pranshu (backend and composer UI) |
| US-31 Live analysis of a posted requirement | 8 | Heet (incremental retrieval, similar hints), Keval (classification, budget, result card), Abhyudit (requirement runs) |
| US-14 **Live requirements map** | 8 | Dhavni didi (graph revisions, deltas, narrator, positions), Abhijeet (map UI, changes feed, live updates) |
| US-37 Requirement lifecycle states | 3 | Parth |
| US-36 Owners, stakeholder groups, ownership requests | 3 | Bansil (backend and UI) |
| US-09 Generate clarification questions | 5 | Madhav |
| US-10 Human review of findings (with protected guard) | 5 | Affan (review state, protected guard, review UI), Parth (review and lifecycle tables) |

**Integration Checkpoint 1 (end of Week 7) — must demonstrate:**
1. Document path: upload → extraction → findings with confidence → clarification → review action, and the **map built from the result**.
2. Collaboration path: join with a code → write a requirement in the composer → result card in the thread within 60 s → **every open map shows the new node and its conflict edge within 2 s of the analysis, and the feed under the map says so in writing** → owner @mentioned.
3. Accuracy report (precision/recall/F1 per category; document-style and post-style separately; **with and without the context pack**, NFR-39).
4. Tenant isolation over REST and WebSocket; a viewer cannot see the composer.

### Sprint 4 · Weeks 8–9 · Issues and PR-style change requests (37 points)

| Story | Pts | Owners |
|---|---|---|
| US-11 Change-impact analysis engine | 8 | Heet (impact analysis, relationship queries) |
| US-33 Open a change request (change editor) | 5 | Bansil (intake, change editor, diff view), Heet (change-request API client), Pranshu (change-request list and page) |
| US-34 Consequence checks | 8 | Madhav (checks, findings delta, risk, Checks tab), Keval (narrative) |
| US-35 Review and merge | 5 | Heet (reviews, review requests, Reviews tab), Parth (merge, needs-update, agreement guard), Affan (merge box) |
| US-52 **Requirement issues and auto conflict issues** | 5 | Dhavni didi (auto conflict issues, issues client), Abhijeet (issue API, list, page, comments) |
| US-12 Version history | 3 | Affan (backend and UI) |
| US-56 **Raise a concern (human-raised findings)** | 3 | Abhyudit (backend and UI) |

**Order inside the sprint:** week 1 — US-11, US-33, US-52, US-56; week 2 — US-34, US-35 on top of them. Pranshu starts the change-request page against a fixed sample JSON on day 1.
**Testing:** Abhyudit checks each scripted change request's affected set and findings delta (resolved, new, still open) and that auto issues are assigned to the right owners; Affan tests no self-approval, compliance sign-off, merge permission, "needs update", and that editing a proposal dismisses earlier approvals (FR-98).
**Exit criteria:** a two-owner conflict opens an issue; a change request with *Resolves ISS-n* shows diff and checks, auto-requests the right reviewers, merges into the baseline as version 2, closes the issue and updates the map; a second open request on the same requirement shows "needs update".

### Sprint 5 · Weeks 10–11 · Suggestions, awareness and preview (38 points) → **CP2**

| Story | Pts | Owners |
|---|---|---|
| US-45 **AI resolution suggestions with human feedback** | 5 | Madhav (suggestion service and feedback), Keval (prompts), Abhyudit (suggestion panel), Bansil (change request from a suggestion) |
| US-38 Inbox and notifications | 5 | Abhijeet (notifications, inbox, bell) |
| US-13 Quality dashboard | 5 | Abhyudit (aggregation and dashboard) |
| US-40 Baseline snapshots and comparison | 5 | Pranshu (backend and UI) |
| US-57 **Decision rules and decision owners** | 3 | Parth (rules engine), Affan (decision owners, rules tab, project settings) |
| US-58 **Rule-based cross-checks** (conflicts the similarity filter misses) | 5 | Heet (attribute index, rule checks), Keval (attribute extraction), Abhyudit (recall measurement) |
| US-51 Live lint, similar hints, pre-flight, AI wording | 5 | Keval (lint, pre-flight, AI wording), Bansil (authoring panel, composer wiring) |
| US-06 Tune thresholds per project | 5 | Heet (threshold preview, re-analysis), Keval, Affan (settings page) |

**Load test (Affan, Dhavni didi):** NFR-24 (messages), NFR-25 (live analysis), NFR-26 (checks), **NFR-32 (map freshness)**, **NFR-33 (map with 500 nodes)**.

**Integration Checkpoint 2 (end of Week 11) — must demonstrate:**
1. The full loop: composer with lint and pre-flight → post → live map → auto conflict issue → **AI suggests three solutions; both owners mark their preferred one; one is edited and accepted** → pre-filled change request with checks and map preview → reviews → merge → notifications to affected owners → snapshot "v1.1" compared with "v1.0".
2. Suggestion outcomes recorded in the six structured categories; an analyst rates 30 suggestions for correctness, reported next to the acceptance rate (NFR-36).
3. **Recall report** on the benchmark including differently worded conflicts below the similarity threshold: caught by AI, by rule checks, missed (NFR-37). A raised concern on a conflict both missed is handled end to end.
4. Dashboard counts equal database counts.
5. Load-test results.
6. Decision rules shown on every issue and change request; risk thresholds reviewed with Project Manager stakeholders (D11).

### Sprint 6 · Weeks 12–13 · Written changes, trustworthy exports, governance (35 points)

| Story | Pts | Owners | Notes |
|---|---|---|---|
| US-18 Protect compliance-critical requirements | 5 | Abhijeet (backend and UI) | Conditional |
| US-61 **Generate the updated SRS with the LLM and review it** | 5 | Bansil (generator, readiness, fidelity check, publishing), Keval (section prompts), Pranshu (SRS API, section review, SRS screen) | Readiness checklist, verbatim requirements, fidelity check |
| US-41 Export the updated SRS (DOCX, PDF, Markdown) | 5 | Bansil (DOCX, PDF, Markdown exporters), Pranshu (export API) | |
| US-59 **Open-items report** beside the approved baseline | 2 | Abhyudit | |
| US-50 Map preview layer and time slider | 5 | Dhavni didi (preview layer, revisions, history), Heet (time slider) | |
| US-08 Assign severity | 3 | Abhyudit (backend and UI) | |
| US-53 Discussion, votes, watch and links | 3 | Affan (backend and UI) | |
| US-55 **Written change log and summaries for the map** | 3 | Heet (change-log backend, Changes panel), Dhavni didi (changes API), Keval (summary paragraph) | |
| US-15 Feedback loop | 3 | Keval (backend and UI) | |
| US-42 Requirement activity timeline | 3 | Abhyudit (backend and UI) | |

There is no stretch item. **Feature freeze at the end of Week 13.** Anything unfinished returns to the backlog, not into Sprint 7.
**Testing:** Abhyudit — full regression, final accuracy, **SRS fidelity tests** (every baseline requirement exactly once and verbatim, no Proposed text); Affan (isolation, join codes) with Madhav (rate limits, injection in posts) — security, accessibility of core flows, production smoke tests.

### Sprint 7 · Week 14 · Release (0 points)

| Day | Activity | Lead |
|---|---|---|
| 1 | Bug bash on the deployed system, all members | Affan |
| 2–3 | Blocking fixes only; deployment freeze end of day 3 | Parth, Dhavni didi |
| 3 | Demo data: 1 workspace, 3 projects (each with its context), 10 members in different roles, planted scenarios, one published SRS v1.0 | Abhyudit, Bansil |
| 4 | Demo script and two rehearsals | Pranshu, Abhijeet |
| 4–5 | Final report: accuracy, load, usability, retrospective, extensions (`IT314_RCD_Scope_Extension_v5.md` §12) | Madhav, Heet, Keval |
| 5 | **Final demo** | All |

## 4. Work Assignment Matrix

Primary work per member per sprint (story numbers; *E* = enabler or test work). From Sprint 3 each story number means the whole feature slice — backend, UI and tests (§2.1).

| Member | S0 | S1 | S2 | S3 | S4 | S5 | S6 | S7 |
|---|---|---|---|---|---|---|---|---|
| Parth | E: tenancy and permission migration, contracts | 19, 27, 24, 01, 04 | 26, 49; E: G1, orchestration | 37 (lifecycle) | 35 (merge, needs-update, agreement guard) | 57 (rules engine) | Integration, migration review, release prep | Fixes, deploy |
| Dhavni didi | E: WebSocket and map spikes, CI | 03; E: event bus | 29; E: graph API v0 | 14 (revisions, deltas, narrator) | 52 (auto issues, issues client) | E: load test | 50 (preview layer, revisions, history), 55 (changes API) | Deploy freeze |
| Bansil | E: composer schema, EARS, brief schema, G3 plan | 02, 60 | E: post backend, drafts, G3 | 36 (owners, ownership requests) | 33 (intake, change editor, diff) | 51 (authoring panel), 45 (change request from a suggestion) | 61 (generator, readiness, fidelity, publishing), 41 (DOCX, PDF, Markdown exporters) | Demo data |
| Pranshu | E: shell, component kit | 19, 01, 03, 04 (UI) | 28, 29 (UI) | 30 (composer) | 33 (change-request list and page) | 40 (baselines) | 61 (SRS API, section review, SRS screen), 41 (export API) | Demo script |
| Heet | E: embedding contract, hint latency | E: embedding stage | 05 (candidates) | 31 (retrieval, hints) | 11 (impact, relations), 33 (change-request client), 35 (reviews) | 58 (rule checks), 06 (thresholds) | 55 (change log, Changes panel), 50 (time slider); E: recall tuning for 58 | Final report |
| Keval | E: LLM adapter, lint catalogue | 60 (context pack); E: classifier skeleton | 05 (classification), 07 | 31 (classify, budget, result card) | 34 (narrative) | 51 (lint, pre-flight, AI), 45 (prompts), 58 (extraction) | 15 (feedback loop and view), 55 (summary), 61 (section prompts) | Final report |
| Madhav | E: join codes, checks schema | 25 | 28; E: question prompts | 09 | 34 (checks, delta, risk, Checks tab) | 45 (suggestion service) | E: injection and rate-limit tests with Affan | Final report |
| Abhijeet | E: prototypes, map spike | 24, 25, 60 (UI) | 07, 26, 49 (UI); 22 prototypes | 14 (map UI, live updates) | 52 (issue API, list, page, comments) | 38 (notifications, inbox, bell) | 18 (compliance) | Demo script |
| Abhyudit | E: benchmark v2 plan | E: labelling, API tests | 05 accuracy; 22 sessions | 31 (requirement runs); CP1 accuracy report | 56 (raise a concern); affected sets, auto-issue owners | 13 (dashboard), 45 (suggestion panel); CP2 recall report, suggestion rating | 42 (timeline), 59 (open items), 08 (severity); regression, final accuracy | Demo data |
| Affan | E: Playwright, permission matrix | 27 tests; join-code abuse; E2E | 22 sessions; WebSocket tests | 10 (finding review); CP1 E2E, map freshness | 12 (version history), 35 (merge box); merge-rule tests | 57 (decision owners, settings page); CP2 E2E | 53 (discussion, votes, watch, links); isolation, accessibility, smoke | Bug bash lead |

## 5. Definitions of Ready and Done

**Ready:** acceptance criteria agreed with the PO proxy; dependencies delivered or stubbed by a contract; a wireframe exists in `IT314_RCD_Interface_Design_v5.md` for UI stories; estimate agreed; test approach named.

**Done:**
- Acceptance criteria met and demonstrated in the sprint review.
- Reviewed by the area owner; CI green (ruff, mypy, pytest, Vitest, Playwright smoke, migration up/down).
- Unit tests for new logic; an API test per new endpoint, including a 404 test for another workspace and a 403 test for a missing **permission**.
- No requirement or message text in audit rows or notification payloads (CR-04).
- AI content labelled; statuses use icon or text as well as colour (NFR-29).
- API reference and `IT314_RCD_Epics_v5.md` status updated.

## 6. Testing Plan by Sprint

| Sprint | Abhyudit (accuracy, backend) | Affan (E2E, performance, security) |
|---|---|---|
| S0 | Benchmark v2 plan | Playwright skeleton, permission matrix |
| S1 | API tests for upload and extraction; labelling | Permission tests; join-code expiry, use limit, brute force; E2E join → upload |
| S2 | First accuracy run; usability sessions | WebSocket tests; custom-role tests; usability sessions |
| S3 | **CP1 accuracy report**, with and without the context pack | **CP1 E2E**; map freshness (NFR-32) |
| S4 | Affected sets; auto-issue owners | Self-approval, merge permission, needs update, compliance sign-off |
| S5 | **CP2 recall report** (AI, rules, missed); **suggestion correctness study** (analysts rate 30 suggestions; compared with acceptance) | **Load test** NFR-24–26, 32, 33; CP2 E2E |
| S6 | Regression; final accuracy; change-log sentences match deltas; SRS fidelity check | Security, accessibility, production smoke (with Madhav) |
| S7 | Demo data validation | Bug bash |

Two testers cover ten developers (D8): every developer owns their unit tests, and Madhav joins Affan for E2E in Sprint 6.

## 7. Ceremonies

| Ceremony | When | Length | Notes |
|---|---|---|---|
| Sprint planning | First day of each sprint | 90 min | Planning poker for new stories |
| Daily stand-up | Daily, asynchronous | — | Posted in the team's own workspace from Sprint 3 (the team uses its own product) |
| Mid-sprint check | Day 5 | 20 min | Applies the midpoint rule and cut order |
| Sprint review | Last day | 60 min | Demo to the PO proxy; to the instructor at CP1 and CP2 |
| Retrospective | After the review | 45 min | One improvement action with a named owner |
| Backlog refinement | Mid-sprint | 45 min | Ready the next sprint |

## 8. Capacity, Velocity and Risk Triggers

- **Capacity assumption:** about 6–8 hours per member per week, roughly 120–160 hours per sprint. The plan uses 34–38 points per sprint, slightly above revision 1; **recalibrate after Sprint 1** with actual velocity and apply the cut order early if needed.
- **Midpoint rule:** if less than 40% of a sprint's points are in review by day 5, cut according to `IT314_RCD_Epics_v5.md` §5.
- **Checkpoint rule:** if CP1 fails on the collaboration path or the map, Sprint 4 starts with the missing items; if CP2 fails, US-50 and US-53 are dropped and Sprint 6 finishes US-45, US-57 and US-58 first. US-61 is never dropped; if the LLM budget runs out, its narrative falls back to the template export (US-41).
- **No mid-sprint scope additions.**

| Trigger | Action |
|---|---|
| LLM spend above 80% of the course budget | Shorten the context pack to the brief summary and glossary, lower top-*k*, raise thresholds, limit pre-flight to 1 per draft, generate suggestions only when a finding is opened, rely on the cache |
| WebSocket hosting blocked (D10) | Polling fallback; the map refreshes every 5 s instead of live |
| Map too slow at 500 nodes | Cluster view by default, table view, 2-hop focus mode |
| A member unavailable for a week | Area reviewer takes over; the next cut-order item is cut |
| Recall below target at CP1 | Sprint 4 reserves 5 points of Keval's and Heet's time for prompts and thresholds; US-58 rule checks start in Sprint 4 instead of 5; US-50 is cut |
| Expert-rated suggestion correctness low at CP2 | Keval and Madhav spend Sprint 6 time on prompts using the structured rejection reasons; US-53 is cut |
