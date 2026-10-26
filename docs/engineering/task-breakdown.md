# Development Tasks

**Sprint 0–7 Work, With Owners and Dependencies (revision 5)**

| | |
|---|---|
| **Source** | [`IT314_RCD_Sprint_Plan_v5.md`](../planning/v5/IT314_RCD_Sprint_Plan_v5.md) §3–§4; story detail in [`IT314_RCD_Product_Backlog_v5.md`](../planning/v5/IT314_RCD_Product_Backlog_v5.md) |
| **Replaces** | The earlier 60-task list (T01–T60) for the old 6-sprint, 94-point plan |
| **Status legend** | ✅ on `main` · 🟡 part delivered · ⬜ not started |

---

## 1. Sprint 0 · Week 1 · Re-baseline (enablers, 0 points)

| Member | Tasks | Status |
|---|---|---|
| Parth | Migrations `0003` (severity, `escalated`) and `0004` (projects, memberships, roles and permissions with the 9 defaults seeded); `require_permission()` skeleton; existing RBAC and isolation tests passing on it | ✅ |
| Dhavni didi | WebSocket + Redis pub/sub spike; map library spike with Abhijeet (Cytoscape.js vs React Flow, 500 nodes / 2,000 edges, NFR-33); `graph.delta` event schema; Compose and CI for new packages | ⬜ |
| Bansil | Composer field schema and draft model with Pranshu; EARS template definitions with Keval; project brief schema (required and optional fields); G3 plan | 🟡 Composer schema, EARS templates and brief schema ✅ (PR #27, `docs/contracts/composer-and-context.md`); G3 plan not tracked in the repo |
| Pranshu | App shell, routing, component kit (buttons, badges with icon + text, drawer, tabs); start login and sign-up-with-code screens | ⬜ |
| Heet | Confirm embedding model; measure similar-requirement hint latency (target < 500 ms server time); draft `analyse_text()` contract | ⬜ |
| Keval | `LLMClient` adapter; prompt v1 with delimited inputs and a context-pack slot; lint pattern catalogue v1 (shared with DR-07); `BudgetGuard` design | 🟡 (classification prompts in open PR #21) |
| Madhav | Join code design (format, hashing, limits, approval); `ImpactReport` and checks schema | 🟡 (clarification and impact design merged, PR #9) |
| Abhijeet | Wireframes from [`IT314_RCD_Interface_Design_v5.md`](../planning/v5/IT314_RCD_Interface_Design_v5.md) turned into clickable prototypes for US-22; map spike with Dhavni didi | 🟡 Wireframes merged (PRs #11, #14, #22); clickable prototypes ⬜ |
| Abhyudit | Benchmark v2 plan: planted-conflict SRS, 40 post-style requirements, 10 scripted change requests with known affected sets and owners | 🟡 (planted-conflict benchmark merged, PR #16; v2 plan in open PR #24) |
| Affan | Playwright skeleton in CI; permission test matrix (permission × role) generated from the catalogue | ⬜ |

**Exit criteria:** the contracts in [`IT314_RCD_Design_Update_v5.md` §6](../planning/v5/IT314_RCD_Design_Update_v5.md#6-interface-contracts-to-agree-in-sprint-0) agreed in writing; `docker compose up` works with the new schema; an event reaches sockets on two API processes; the map library is chosen; Step 7 decisions sent to stakeholders.

## 2. Sprints 1–6 — Stories and Owners

Owners are listed primary first. Enablers are 0-point tasks inside the sprint. Dependencies between stories are in §4.

### Sprint 1 · Weeks 2–3 · Joining, roles, ingestion (37 points)

| Story | Pts | Owners |
|---|---|---|
| US-19 Authenticate via JWT (sign-up only with a code) | 5 | Parth, Pranshu |
| US-27 Enforce roles and permissions | 5 | Parth, Affan |
| US-24 Create a workspace and projects | 3 | Parth, Abhijeet |
| US-60 Project context required before analysis | 3 | Bansil, Abhijeet, Keval |
| US-25 Join a workspace with a code or invite link | 5 | Madhav, Abhijeet |
| US-01 Upload SRS into a project | 5 | Parth, Pranshu |
| US-02 Automatic requirement extraction | 5 | Bansil |
| US-03 Track analysis progress | 3 | Dhavni didi, Pranshu |
| US-04 View extracted requirements | 3 | Parth, Pranshu |

**Enablers:** Heet — embedding stage; Keval — classifier skeleton and retries; Dhavni didi — event bus; Abhyudit — label the benchmark; Affan — E2E *create code → join → upload*, join-code brute-force test.

### Sprint 2 · Weeks 4–5 · Detection engine, channels, custom roles (38 points)

| Story | Pts | Owners |
|---|---|---|
| US-05 Detect requirement issues (5a conflicts · 5b duplicates and ambiguous · 5c incomplete and dependent) | 13 | Keval, Heet, Abhyudit |
| US-07 Explain findings with confidence and context | 5 | Keval, Abhijeet |
| US-26 Remove members, change roles, leave | 3 | Parth, Abhijeet |
| US-49 Custom roles and permission sets | 3 | Parth, Abhijeet |
| US-28 Create and manage channels | 3 | Madhav, Pranshu |
| US-29 Real-time messaging with threads and mentions | 8 | Dhavni didi, Pranshu |
| US-22 Low-fidelity validation sessions | 3 | Abhyudit, Affan, Abhijeet |

**Milestones:** 5a by day 4 · 5b by day 7 · 5c by day 9. **Midpoint rule:** if 5a is not done by day 5, move US-07, US-49 and US-22 to Sprint 3.
**AI providers (ADR-31, [`ai-providers.md`](ai-providers.md) §6):** Keval — Gemini and Groq transports with failover, config, tests; Heet — switch to `BAAI/bge-small-en-v1.5`, re-embed, re-tune the similarity threshold with Abhyudit.
**Hybrid candidates (ADR-30, [`conflict-detection-strategy.md`](conflict-detection-strategy.md) §10):** Keval — minimal attribute extractor and concept lexicon (pulled forward from US-58); Heet — `find_candidates` with signals S1–S6, ranking and caps; Keval — pre-check notes in the pair prompt (switchable for the ablation); Parth — `candidate_pairs.signals` and `disputed` status in `0006`; Abhyudit — `eval/candidate_recall.py`. **Gate:** 100 % candidate recall on the 8 planted conflicts, ≥ 95 % on all pairwise labels, ≤ 10 % of all pairs.
**Enablers:** Parth — per-pair classification status (G1), orchestration; Bansil — post backend and drafts, G3 cleanup; Dhavni didi — graph API v0 (`GET /graph`) from stored findings; Madhav — clarification prompt drafts.

### Sprint 3 · Weeks 6–7 · Composer, live analysis, live map (37 points) → CP1

| Story | Pts | Owners |
|---|---|---|
| US-30 Requirement composer with EARS templates | 5 | Bansil, Pranshu |
| US-31 Live analysis of a posted requirement | 8 | Heet, Keval, Dhavni didi |
| US-14 Live requirements map | 8 | Dhavni didi, Abhijeet |
| US-37 Requirement lifecycle states | 3 | Parth |
| US-36 Owners, stakeholder groups, ownership requests | 3 | Bansil, Pranshu |
| US-09 Generate clarification questions | 5 | Madhav |
| US-10 Human review of findings (with protected guard) | 5 | Parth, Abhijeet |

### Sprint 4 · Weeks 8–9 · Issues and PR-style change requests (37 points)

| Story | Pts | Owners |
|---|---|---|
| US-11 Change-impact analysis engine | 8 | Madhav, Heet |
| US-33 Open a change request (change editor) | 5 | Bansil, Abhijeet |
| US-34 Consequence checks | 8 | Madhav, Keval, Abhijeet |
| US-35 Review and merge | 5 | Parth, Abhijeet |
| US-52 Requirement issues and auto conflict issues | 5 | Dhavni didi, Pranshu |
| US-12 Version history | 3 | Parth, Pranshu |
| US-56 Raise a concern (human-raised findings) | 3 | Bansil, Pranshu |

**Order inside the sprint:** week 1 — US-11, US-33, US-52, US-56; week 2 — US-34, US-35 on top of them. Abhijeet starts the change-request page against a fixed sample JSON on day 1.

### Sprint 5 · Weeks 10–11 · Suggestions, awareness and preview (38 points) → CP2

| Story | Pts | Owners |
|---|---|---|
| US-45 AI resolution suggestions with human feedback | 5 | Madhav, Keval, Abhijeet |
| US-38 Inbox and notifications | 5 | Madhav, Abhijeet |
| US-13 Quality dashboard | 5 | Pranshu, Parth |
| US-40 Baseline snapshots and comparison | 5 | Parth, Pranshu |
| US-57 Decision rules and decision owners | 3 | Parth, Pranshu |
| US-58 Rule-based cross-checks (extends the S2 extractor; strongest signals become `source = rule` findings — ADR-30) | 5 | Heet, Keval, Abhyudit |
| US-51 Live lint, similar hints, pre-flight, AI wording | 5 | Keval, Bansil |
| US-06 Tune thresholds per project | 5 | Keval, Heet, Abhijeet |

**Load test (Affan, Dhavni didi):** NFR-24, NFR-25, NFR-26, NFR-32, NFR-33.

### Sprint 6 · Weeks 12–13 · Written changes, trustworthy exports, governance (37 points)

| Story | Pts | Owners |
|---|---|---|
| US-18 Protect compliance-critical requirements (conditional) | 5 | Parth, Abhijeet |
| US-61 Generate the updated SRS with the LLM and review it | 5 | Bansil, Keval, Pranshu |
| US-41 Export the updated SRS (DOCX, PDF, Markdown) | 5 | Bansil |
| US-59 Open-items report beside the approved baseline | 2 | Bansil |
| US-50 Map preview layer and time slider | 5 | Dhavni didi, Pranshu |
| US-08 Assign severity | 3 | Keval, Abhijeet |
| US-53 Discussion, votes, watch and links | 3 | Madhav |
| US-55 Written change log and summaries for the map | 3 | Dhavni didi, Keval, Pranshu |
| US-15 Feedback loop | 3 | Keval, Abhijeet |
| US-42 Requirement activity timeline | 3 | Dhavni didi, Pranshu |

No stretch item. **Feature freeze at the end of Week 13**; anything unfinished returns to the backlog.

## 3. Sprint 7 · Week 14 · Release (0 points)

| Day | Activity | Lead |
|---|---|---|
| 1 | Bug bash on the deployed system, all members | Affan |
| 2–3 | Blocking fixes only; deployment freeze end of day 3 | Parth, Dhavni didi |
| 3 | Demo data: 1 workspace, 3 projects (each with its context), 10 members in different roles, planted scenarios, one published SRS v1.0 | Abhyudit, Bansil |
| 4 | Demo script and two rehearsals | Pranshu, Abhijeet |
| 4–5 | Final report: accuracy, load, usability, retrospective, extensions | Madhav, Heet, Keval |
| 5 | **Final demo** | All |

## 4. Dependency Notes

- **Critical path (epics):** EP-01 → EP-02 → EP-03 → EP-11 → EP-15 / EP-12 → EP-13 → EP-08. The detection engine (US-05) feeds the document path, live analysis, the map and the change-request checks, so a delay there delays almost everything.
- EP-10 (joining and channels) must be ready for EP-11 (composer, live analysis) by Sprint 3.
- **US-60 gates analysis:** no `analysis_runs` row may be created for a project that is not `active` (`ContextGate`), so US-05, US-31 and US-34 all depend on it.
- US-05 is engine-first: the same engine checks one requirement against a baseline, so US-31 (live analysis), US-51 (pre-flight) and US-34 (checks) reuse it unchanged.
- US-61 depends on the change log (US-55, `graph_events`) for its "changes since the previous version" section and on baselines (US-40).
- **Checkpoint rule:** if CP1 fails on the collaboration path or the map, Sprint 4 starts with the missing items; if CP2 fails, US-50 and US-53 are dropped and Sprint 6 finishes US-45, US-57 and US-58 first. US-61 is never dropped; if the LLM budget runs out, its narrative falls back to the template export.

The per-member, per-sprint matrix is [`IT314_RCD_Sprint_Plan_v5.md` §4](../planning/v5/IT314_RCD_Sprint_Plan_v5.md#4-work-assignment-matrix).
