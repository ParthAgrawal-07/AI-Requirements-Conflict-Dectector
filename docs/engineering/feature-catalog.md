# Features Overview

**All 23 User Stories — ID, Priority, Owner, Status**

| | |
|---|---|
| **Source** | Consolidated Product Backlog (23 stories, reconciled from 7 team drafts) |
| **MVP path** | US-01, US-02, US-05, US-09 form the minimum demonstrable path |
| **Status** | All features below are planned — none implemented yet |

---

## 1. Feature List

| ID | Feature | Priority | Pts | Owner | Status |
|---|---|---|---|---|---|
| US-01 | Upload SRS Document (Multi-Format) | Must | 5 | Role 1 — Ingestion | Planned — Sprint 1 |
| US-02 | Automatic Requirement Extraction | Must | 5 | Role 1 — Ingestion | Planned — Sprint 1 |
| US-03 | Track Long-Running Analysis Progress | Must | 3 | Role 5 — Backend API | Planned — Sprint 2 |
| US-04 | View Extracted Requirements List | Must | 3 | Role 1 — Ingestion | Planned — Sprint 1 |
| US-05 | Detect Requirement Issues (5-Category Classification) | Must | 13 | Role 3 — LLM Classification | Planned — Sprint 2 (core) |
| US-06 | Tune Ambiguity / Dependency / Duplicate Thresholds | Should | 5 | Role 2 — Embedding & Similarity | Planned — Sprint 4 |
| US-07 | Explain Findings with Confidence Score & Context | Must | 5 | Role 3 — LLM Classification | Planned — Sprint 2 |
| US-08 | Assign Severity to Flagged Issues | Should | 3 | Role 6 — Frontend Core UI | Planned — Sprint 4 |
| US-09 | Generate Clarification Questions | Must | 5 | Role 4 — Clarification/Impact | Planned — Sprint 3 |
| US-10 | Suggest Resolutions & Human Review of Findings | Must | 5 | Role 6 — Frontend Core UI | Planned — Sprint 3 |
| US-11 | Run Change-Impact Analysis on Requirement Edit | Must | 8 | Role 4 — Clarification/Impact | Planned — Sprint 3 |
| US-12 | Maintain Requirement Version History | Must | 3 | Role 4 — Clarification/Impact | Planned — Sprint 3 |
| US-13 | View Requirements Quality Dashboard | Must | 5 | Role 7 — Viz & DevOps | Planned — Sprint 4 |
| US-14 | Visualize the Dependency / Conflict Graph | Should | 5 | Role 7 — Viz & DevOps | Planned — Sprint 4 |
| US-15 | Dismiss / Resolve a Flag (Feedback Loop) | Should | 3 | Role 6 — Frontend Core UI | Planned — Sprint 5 |
| US-16 | Deliver Reports Through Multiple Channels | Should | 5 | Role 7 — Viz & DevOps | Planned — Sprint 5 |
| US-17 | Receive Executive / ROI Summary Report | Could | 5 | Role 7 — Viz & DevOps | Deferred (post-MVP) |
| US-18 | Protect Compliance-Critical Requirements | Must (conditional) | 5 | Role 5 — Backend API | Planned — Sprint 5 |
| US-19 | Authenticate via JWT | Must | 5 | Role 5 — Backend API | Planned — Sprint 2 |
| US-20 | Documented REST API for Third-Party Integration | Could | 8 | Role 5 — Backend API | Deferred (post-MVP) |
| US-21 | Integrate with Jira/Confluence/GitHub | Could | 8 | Role 7 — Viz & DevOps | Deferred (post-MVP) |
| US-22 | Validate Flagged Output with Low-Fidelity Preview | Could | 3 | Role 6 — Frontend Core UI | Planned — Sprint 5 |
| US-23 | Capture End-Customer Feedback Trends (Outcome Story) | Won't Have | N/A | — (no dev task) | Tracked, not scheduled |

## 2. MVP Scope Note

US-01, US-02, US-05, and US-09 form the minimum demonstrable path: upload → extraction → issue detection → clarification generation. If the Week 7 integration checkpoint slips, US-11 (impact analysis) and US-14 (graph visualization) are cut first. US-18 through US-21 (compliance protection, SSO, REST API, tool integrations) are industry-deployment extensions and are not required for the semester deliverable.

**US-05 (issue detection) is the core value proposition and must be protected before any other feature.**

## 3. Deferred / Post-MVP Backlog

| ID | Story | Points | Why Deferred |
|---|---|---|---|
| US-17 | Executive / ROI Summary Report | 5 | Industry-extension; not required for academic demo |
| US-20 | Documented REST API for Third-Party Integration | 8 | Recommended for post-MVP phase per its own acceptance notes |
| US-21 | Jira/Confluence/GitHub Integration | 8 | Out of scope for semester MVP; included only for industry-deployment completeness |

*Kept in the backlog as stretch goals only — pull from here if Sprints 0–5 finish early; do not add new scope mid-sprint.*

## 4. Full Acceptance Criteria

Each story's full front/back card — As a / I want / So that, Acceptance Criteria, FR trace, and source-draft attribution — lives in the team's Consolidated Product Backlog source document. This overview is a summary index only; see `feature-deep-dive.md` for a per-feature deep dive on the highest-risk stories.
