# Project Status

**AI Requirements Conflict Detector — Live Dashboard**

| | |
|---|---|
| **Course** | IT314 — Software Engineering, Autumn 2026–27 |
| **Team size** | 10 members |
| **Plan** | Revision 5 — [`IT314_RCD_Sprint_Plan_v5.md`](../planning/v5/IT314_RCD_Sprint_Plan_v5.md) |
| **Current phase** | Sprint 1 (Weeks 2–3): joining, roles, workspaces and projects with compulsory context, upload and extraction |
| **Last updated** | 22 Oct 2026 |

---

## 1. Status at a Glance

| Metric | Value | Note |
|---|---|---|
| Overall phase | Sprint 1 in progress | Sprint 0 enablers and the Sprint 1 backend for US-19, US-24, US-27, US-01, US-02, US-04, US-60 are on `main` |
| Sprints | S0 (1 week) + S1–S6 (2 weeks each) + S7 release week | 14 weeks |
| Backlog stories | 61 (US-01–US-61) in 15 epics | US-23 is outcome-only, no development task |
| Story points | 284 total · **224 scheduled** · 60 deferred | 37 · 38 · 37 · 37 · 38 · 37 across S1–S6 |
| Priorities (points) | Must 168 · Should 74 · Could 42 | Must is 75% of scheduled points (decision D9) |
| Functional requirements | 107 (FR-01–FR-107) | Canonical numbering, `requirements-spec.md` |
| Non-functional requirements | 39 (NFR-01–NFR-39) | |
| Domain requirements | 25 (DR-01–DR-25) | |
| Stakeholder groups | 12 | 10 original + Workspace Owner / PM and Stakeholder Contributors (new in Step 7) |
| Checkpoints | CP1 end of Week 7 · CP2 end of Week 11 · Final demo Week 14 | |

## 2. Sprint Plan

| Sprint | Weeks | Goal | Points | Status |
|---|---|---|---|---|
| S0 | 1 | Re-baseline: tenancy and permission migration, spikes (WebSocket, map library), contracts, wireframes, benchmark plan | 0 (enablers) | 🟡 Migrations `0003`, `0004`, contracts (`docs/contracts/`), wireframes and benchmark merged; WebSocket and map-library spikes not on `main` yet |
| S1 | 2–3 | Join by code, roles, workspaces and projects **with compulsory context**, upload and extract an SRS | 37 | 🟡 In progress — see §3 |
| S2 | 4–5 | Detection engine, real-time channels, custom roles | 38 | ⬜ |
| S3 | 6–7 | Composer, live analysis, **live map**, review → **CP1** | 37 | ⬜ |
| S4 | 8–9 | Issues (AI and human-raised), PR-style change requests, findings delta, agreement rules, versions | 37 | ⬜ |
| S5 | 10–11 | AI suggestions with feedback, decision rules, rule-based cross-checks, notifications, dashboard, baselines, lint and pre-flight → **CP2** | 38 | ⬜ |
| S6 | 12–13 | Written change log, map preview and time slider, **LLM-generated updated SRS**, export + open-items report, compliance, severity, votes | 37 | ⬜ |
| S7 | 14 | Release: bug bash, deployment freeze, demo data, rehearsal, final report | 0 | ⬜ |

## 3. Sprint 1 Progress

| Story | Pts | Owners | Status on `main` |
|---|---|---|---|
| US-19 Authenticate via JWT (sign-up only with a code) | 5 | Parth, Pranshu | 🟡 Backend ✅; login UI ⬜ |
| US-27 Enforce roles and permissions | 5 | Parth, Affan | 🟡 Backend ✅ (catalogue, 9 default roles, `require_permission`); UI ⬜ |
| US-24 Create a workspace and projects | 3 | Parth, Abhijeet | 🟡 Backend ✅; UI ⬜ |
| US-60 Project context required before analysis | 3 | Bansil, Abhijeet, Keval | 🟡 Context service, AI-drafted brief and activation ✅; setup wizard UI and context pack ⬜ |
| US-25 Join a workspace with a code or invite link | 5 | Madhav, Abhijeet | 🟡 Sign-up redeems a code ✅; join-code management ⬜ (branch `feat/madhav-sprint1-join-codes`, not merged) |
| US-01 Upload SRS into a project | 5 | Parth, Pranshu | 🟡 Backend ✅; UI ⬜ |
| US-02 Automatic requirement extraction | 5 | Bansil | ✅ |
| US-03 Track analysis progress | 3 | Dhavni didi, Pranshu | 🟡 Status endpoint ✅; stage progress and UI ⬜ |
| US-04 View extracted requirements | 3 | Parth, Pranshu | 🟡 Backend ✅; UI ⬜ |

**Sprint 1 exit criteria** (from the plan): a project cannot be analysed until its PM uploads an initial SRS or confirms a brief; AI-drafted brief fields are labelled until confirmed; a PM creates a code; a developer signs up with it, gets the Developer role, uploads the planted SRS and sees its requirements with printed IDs; the permission matrix test passes.

## 4. Team and Areas of Ownership

From Sprint 3 the work is divided **by feature, not by layer**: each owner builds a feature's backend, UI and
tests, testers also own features, and code lines across Sprints 2–6 are balanced to within about ±5% per
person. Full rules, line counts and roles: [Sprint Plan §2](../planning/v5/IT314_RCD_Sprint_Plan_v5.md#2-team-and-areas-of-ownership).

| Member | Role from Sprint 3 | Features they own (backend + UI + tests) |
|---|---|---|
| **Parth** | Backend lead, integration lead; reviews every migration and permission change | US-37 lifecycle · US-35 merge and agreement guard · US-57 decision rules engine |
| **Dhavni didi** | Real-time, map backend, DevOps | US-14 deltas and narrator · US-52 auto issues · US-38 bell and inbox UI · US-50 preview layer and history · US-18 compliance UI · S5 load test |
| **Bansil** | Authoring and the updated SRS | US-36 ownership · US-33 change editor · US-51 authoring panel · US-61 SRS generation and fidelity · US-41 exporters |
| **Pranshu** | Composer, change requests, baselines, SRS API; app shell | US-30 composer · US-33 change-request page · US-40 baselines · US-51 authoring-aids API · US-61 SRS API · US-41 export API · US-15 AI feedback API |
| **Heet** | Retrieval, impact, reviews, change log | US-31 retrieval · US-11 impact · US-35 reviews · US-58 rule checks · US-06 thresholds · US-55 change log · US-50 time slider |
| **Keval** | LLM and AI quality; reviews every LLM call | US-31 classification · US-34 narrative · US-51 lint engine and pre-flight · US-58 extraction · US-15 feedback loop and view · US-61 prompts and SRS screen |
| **Madhav** | Clarification and consequences | US-09 clarification · US-34 consequence checks · US-45 suggestion service · S6 security tests |
| **Abhijeet** | Map UI, issues, notifications and compliance backends, changes API | US-14 map UI · US-52 issue pages · US-38 notifications backend · US-18 compliance backend · US-55 changes API |
| **Abhyudit** | Testing (accuracy) + features | US-31 requirement runs · US-56 concerns · US-13 dashboard · US-45 suggestion panel · US-42 timeline · US-59 open items · US-08 severity |
| **Affan** | Testing (E2E, security) + features | US-10 finding review · US-12 version history · US-35 merge box · US-57 decision owners · US-53 discussion and votes |

Scrum Master rotates: Parth (S0–S1), Dhavni didi (S2), Bansil (S3), Pranshu (S4), Heet (S5), Keval (S6), Madhav (S7). The team names one fixed Product Owner proxy for the semester.

## 5. Risks Being Watched

| Risk | Mitigation | Owner |
|---|---|---|
| Sprint loads of 37–38 points are above revision 1 (D12) | Recalibrate after Sprint 1 with actual velocity; midpoint rule and cut order from Sprint 2 | Scrum Master |
| US-05 (13 pts) is the riskiest story | Tasks 5a/5b/5c with milestones; if 5a is not done by day 5, US-07, US-49, US-22 move to Sprint 3 | Keval, Heet |
| Real-time layer and map performance (D10, D14) | Sprint 0 spikes; polling fallback (map refresh every 5 s); cluster view, table view, 2-hop focus | Dhavni didi, Abhijeet |
| Conflicts missed because wording differs | Rule-based cross-checks (US-58); recall measured below the similarity threshold (NFR-37); human-raised concerns (US-56) | Heet, Keval, Abhyudit |
| LLM spend above 80% of the course budget | Shorten the context pack, lower top-*k*, raise thresholds, limit pre-flight, rely on the cache | Keval |
| Two frontend developers for many screens (D13) | Component kit from Sprint 0; Bansil and Madhav wire some UI in Sprints 5–6 | Pranshu |
| Generated SRS misstates the baseline (D20) | Requirement text inserted by the system, never the LLM; fidelity check blocks publishing (DR-25) | Bansil, Abhyudit |

Full risk list: [`IT314_RCD_Scope_Extension_v5.md` §10](../planning/v5/IT314_RCD_Scope_Extension_v5.md#10-risks-introduced-by-the-widening); open decisions: [`IT314_RCD_Epics_v5.md` §6](../planning/v5/IT314_RCD_Epics_v5.md#6-gaps-and-decisions).

## 6. Document Index

See `INDEX.md` for the master index and change-impact matrix. This dashboard is a summary view; it does not duplicate detail owned by the other documents.
