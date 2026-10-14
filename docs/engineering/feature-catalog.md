# Features Overview

**All 23 User Stories — ID, Priority, Owner, Status**

| | |
|---|---|
| **Source** | [`../product-backlog.md`](../product-backlog.md) (23 stories, reconciled from 7 team drafts) — wins if this table disagrees |
| **Owners** | From [`../sprint-plan.md`](../sprint-plan.md); testing for every story is Abhyudit (backend) and Affan (frontend) |
| **MVP path** | US-01, US-02, US-05, US-09 form the minimum demonstrable path |
| **Status** | Sprint 0 merged; Sprint 1 stories in review — status column below |

---

## 1. Feature List

| ID | Feature | Priority | Pts | Owners | Status |
|---|---|---|---|---|---|
| US-01 | Upload SRS Document (PDF/DOCX) | Must | 5 | Parth (API) · Pranshu (UI) | In review — Sprint 1 (PR #7) |
| US-02 | Automatic Requirement Extraction | Must | 5 | Bansil | In review — Sprint 1 (PR #8); PDF/DOCX parsers merged in Sprint 0 |
| US-03 | Track Long-Running Analysis Progress | Must | 3 | Pranshu (UI) · Dhvani (job queue) | Planned — Sprint 2 |
| US-04 | View Extracted Requirements List | Must | 3 | Pranshu (UI) | Planned — Sprint 1 |
| US-05 | Detect Requirement Issues (5-Category Classification) | Must | 13 | Heet (pre-filter) · Keval (classifier) · Abhijeet (UI) | Planned — Sprint 2 (core) |
| US-06 | Tune Ambiguity / Dependency / Duplicate Thresholds | Should | 5 | Heet · Keval · Abhijeet (UI) | Planned — Sprint 4 |
| US-07 | Explain Findings with Confidence Score & Context | Must | 5 | Keval · Abhijeet (UI) | Planned — Sprint 2 |
| US-08 | Assign Severity to Flagged Issues | Should | 3 | Madhav · Abhijeet (UI) | Planned — Sprint 4 |
| US-09 | Generate Clarification Questions | Must | 5 | Madhav · Abhijeet (UI) | Planned — Sprint 3 |
| US-10 | Suggest Resolutions & Human Review of Findings | Must | 5 | Parth (API) · Abhijeet (UI) | Planned — Sprint 3 |
| US-11 | Run Change-Impact Analysis on Requirement Edit | Must | 8 | Madhav · Dhvani (UI) | Planned — Sprint 3 |
| US-12 | Maintain Requirement Version History | Must | 3 | Parth · Pranshu (UI) | Planned — Sprint 3 |
| US-13 | View Requirements Quality Dashboard | Must | 5 | Parth (aggregation) · Pranshu (UI) | Planned — Sprint 4 |
| US-14 | Visualize the Dependency / Conflict Graph | Should | 5 | Dhvani | Planned — Sprint 4 |
| US-15 | Dismiss / Resolve a Flag (Feedback Loop) | Should | 3 | Madhav · Pranshu (UI) | Planned — Sprint 5 |
| US-16 | Deliver Reports Through Multiple Channels | Should | 5 | Dhvani (delivery) · Abhijeet (UI) | Planned — Sprint 5 |
| US-17 | Receive Executive / ROI Summary Report | Could | 5 | — (deferred) | Deferred (post-MVP) |
| US-18 | Protect Compliance-Critical Requirements | Should (conditional on regulated-industry scope) | 5 | Parth | Planned — Sprint 5 |
| US-19 | Authenticate via JWT (SSO Path for Enterprise Deployment) | Must | 5 | Parth | Partly done — login, `/auth/me` and roles merged in Sprint 0; workspace scoping (T15) in Sprint 2 |
| US-20 | Documented REST API for Third-Party Integration | Could | 8 | — (deferred) | Deferred (post-MVP) |
| US-21 | Integrate with Jira/Confluence/GitHub | Could | 8 | — (deferred) | Deferred (post-MVP) |
| US-22 | Validate Flagged Output with Low-Fidelity Preview | Could | 3 | Affan | Planned — Sprint 5 |
| US-23 | Capture End-Customer Feedback Trends (Outcome Story) | Won't Have | N/A | — (no dev task) | Tracked, not scheduled |

## 2. MVP Scope Note

US-01, US-02, US-05 and US-09 form the minimum demonstrable path: upload → extraction → issue detection → clarification generation. If the Week 7 integration checkpoint slips, US-11 (impact analysis) and US-14 (graph visualization) are cut first. US-18 (compliance tagging, review queue and audit export), US-20, US-21 and the SSO extension of US-19 are industry-deployment extensions and are not required for the semester deliverable; the JWT baseline of US-19 **is** required.

**US-05 (issue detection) is the core value proposition and must be protected before any other feature.**

## 3. Deferred / Post-MVP Backlog

| ID | Story | Points | Why Deferred |
|---|---|---|---|
| US-17 | Executive / ROI Summary Report | 5 | Industry-extension; not required for academic demo |
| US-20 | Documented REST API for Third-Party Integration | 8 | Recommended for post-MVP phase per its own acceptance notes |
| US-21 | Jira/Confluence/GitHub Integration | 8 | Out of scope for semester MVP; included only for industry-deployment completeness |

*Kept in the backlog as stretch goals only — pull from here if Sprints 0–5 finish early; do not add new scope mid-sprint.*

## 4. Full Acceptance Criteria

Each story's full card (As a / I want / So that, acceptance criteria, FR trace, notes and source drafts) is in [`../product-backlog.md`](../product-backlog.md). This catalog is a summary index only; see `feature-deep-dive.md` for the highest-risk stories.
