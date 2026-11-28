# Project Status

**AI Requirements Conflict Detector — Live Dashboard**

| | |
|---|---|
| **Course** | IT314 — Software Engineering, Autumn 2026–27 |
| **Team size** | 10 members |
| **Plan** | Revision 5 — [`IT314_RCD_Sprint_Plan_v5.md`](../planning/v5/IT314_RCD_Sprint_Plan_v5.md) |
| **Current phase** | Sprint 7 (Week 14): release — merge the remaining Sprint 6 PRs, bug bash, demo data, rehearsal, final report. Submission deadline 3 Dec 2026 |
| **Last updated** | 28 Nov 2026 (against `main` at `eea5be7`, 24 Nov 2026) |

---

## 1. Status at a Glance

| Metric | Value | Note |
|---|---|---|
| Overall phase | Sprint 7 (release) | Sprints 0–5 merged; Sprint 6 partly merged (US-50 part, US-53, US-55 part); 7 Sprint 6 stories wait on open PRs (§3) |
| Delivered on `main` | 41 of 48 scheduled stories | 39 fully, 2 in part; see [`feature-catalog.md`](feature-catalog.md) for each story's PRs |
| CI on `main` | Green | Backend CI, Frontend CI, E2E and Deploy (Azure VM) all passed on the last push (#122, 24 Nov) |
| Deployment | Live on one Azure VM | Deployed by `.github/workflows/deploy-azure.yml` on every push to `main` ([`devops-guide.md`](devops-guide.md)) |
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
| S0 | 1 | Re-baseline: tenancy and permission migration, spikes (WebSocket, map library), contracts, wireframes, benchmark plan | 0 (enablers) | ✅ Migrations, contracts, wireframes, benchmark plan, WebSocket and map spikes ([`docs/spikes/`](../spikes/)), Playwright skeleton |
| S1 | 2–3 | Join by code, roles, workspaces and projects **with compulsory context**, upload and extract an SRS | 37 | ✅ All 9 stories merged (#7, #8, #26, #27, #37–#40, #43, #45) |
| S2 | 4–5 | Detection engine, real-time channels, custom roles | 38 | ✅ All 7 stories merged (#42, #46, #47, #50–#52, #56–#59); usability sessions in [`docs/usability/`](../usability/) |
| S3 | 6–7 | Composer, live analysis, **live map**, review → **CP1** | 37 | ✅ All 7 stories merged (#60–#70, CP1 benchmark #93) |
| S4 | 8–9 | Issues (AI and human-raised), PR-style change requests, findings delta, agreement rules, versions | 37 | ✅ All 7 stories merged (#71–#88) |
| S5 | 10–11 | AI suggestions with feedback, decision rules, rule-based cross-checks, notifications, dashboard, baselines, lint and pre-flight → **CP2** | 38 | ✅ All 8 stories merged (#87–#103); CP2 report `eval/reports/cp2.md`, load test `load/reports/cp2.md` |
| S6 | 12–13 | Written change log, map preview and time slider, **LLM-generated updated SRS**, export + open-items report, compliance, severity, votes | 37 | 🟡 US-53 merged; US-50, US-55 in part; US-08, US-15, US-18, US-41, US-42, US-59, US-61 built, PRs open (§3) |
| S7 | 14 | Release: bug bash, deployment freeze, demo data, rehearsal, final report | 0 | 🟡 In progress |

## 3. What Is Not Complete

**Built in Sprint 6 but not merged to `main`** (code exists in the Sprint 6 zips and open PRs; merge order in the
Sprint 6 `MERGE_ORDER.md`):

| Story | Pts | What is missing on `main` | Where it is |
|---|---|---|---|
| US-61 Generate the updated SRS with the LLM (Must, protected demo path) | 5 | Generator, readiness, fidelity check, publishing, SRS API, SRS screen, section prompts | PRs #108, #107 open; SRS screen and section prompts have no open PR (#123 closed) |
| US-41 Export the updated SRS (DOCX, PDF, Markdown) | 5 | Exporters and export API | PRs #108, #107 open |
| US-18 Protect compliance-critical requirements | 5 | Protection, compliance queue, audit export, protected badge | PRs #116 (backend), #118 (UI) open. The protected guard on review actions (US-10) is already on `main` |
| US-08 Assign severity to flagged issues | 3 | Severity override and sort | PR #106 open. Severity proposed by the system is stored already |
| US-42 Requirement activity timeline | 3 | Timeline API and UI | PR #106 open |
| US-59 Open-items report beside the baseline | 2 | Report | PR #106 open |
| US-15 Dismiss / resolve feedback loop | 3 | AI feedback report and view | API in PR #107 open; feedback view PR #123 closed |
| US-50 Map preview and time slider (part) | — | Time slider and map page UI | PR #111 open |
| US-55 Written change log (part) | — | Changes API, Changes panel, AI change-summary paragraph | PRs #116, #111 open; #123 closed |

Sprint 6 test PRs also open: #105 (final accuracy report, SRS fidelity tests), #109 (injection and rate-limit
tests). Infrastructure PRs open: #94 / #104 (Docker runtime fixes).

**Deferred by plan** (not built, 60 points): US-16, US-17, US-20, US-21, US-32, US-39, US-43, US-44, US-46, US-47,
US-48, US-54, and outcome story US-23. Reasons in [`feature-catalog.md` §3](feature-catalog.md#3-deferred--post-mvp-backlog).

**Measured gaps:**

* Classification precision/recall per category with a live model is not in a report on `main`: the CP2 report
  (`eval/reports/cp2.md`) leaves the AI layer and the 30-suggestion rating study empty until a live run, and the
  final accuracy report is in open PR #105. What is measured on `main`: rule checks catch 12 of 15 reworded
  conflicts (6 of the 9 below the similarity threshold) with 0 false positives on look-alikes (NFR-37).
* Advanced ML depth (a fine-tuned embedding model, gap D6) was not done.
* Notification email digests (US-39) need SMTP, which the MVP does not have.

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
