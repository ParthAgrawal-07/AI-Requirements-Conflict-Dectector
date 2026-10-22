# Features Overview

**All 61 User Stories — ID, Priority, Points, Sprint, Epic, Owners, Status**

| | |
|---|---|
| **Source** | [`IT314_RCD_Product_Backlog_v5.md`](../planning/v5/IT314_RCD_Product_Backlog_v5.md) (v3.4, 61 stories) and [`IT314_RCD_Epics_v5.md`](../planning/v5/IT314_RCD_Epics_v5.md) (15 epics) |
| **Points** | **284 total · 224 scheduled** in Sprints 1–6 (37 · 38 · 37 · 37 · 38 · 37) · 60 deferred · US-23 is an outcome story with no points |
| **Priorities (points)** | Must 168 · Should 74 · Could 42 |
| **Status legend** | ✅ delivered · 🟡 in progress (part delivered) · ⬜ not started · ⏸ deferred (post-MVP or cut in rev. 3–5). Status reflects `main` as of 22 Oct 2026 |

---

## 1. Feature List

| ID | Feature | Priority | Pts | Sprint | Epic | Owners | Trace | Status |
|---|---|---|---|---|---|---|---|---|
| US-01 | Upload SRS Document into a Project | Must | 5 | S1 | EP-02 | Parth (API), Pranshu (UI) | FR-01, FR-02, FR-04, FR-54 | 🟡 Backend ✅ (upload into a project, baseline or proposals, validation); UI ⬜ |
| US-02 | Automatic Requirement Extraction | Must | 5 | S1 | EP-02 | Bansil | FR-03, FR-04 | ✅ Extraction, segmentation, printed IDs, sections, `needs_review` |
| US-03 | Track Long-Running Analysis Progress | Must | 3 | S1 | EP-02 | Dhavni didi (Celery), Pranshu (UI) | Operational (supports FR-03–FR-17), FR-52 | 🟡 Document status and progress endpoint ✅; stage progress and UI ⬜ |
| US-04 | View Extracted Requirements List | Must | 3 | S1 | EP-02 | Parth (API), Pranshu (UI) | FR-03, FR-05, FR-60 | 🟡 Backend ✅ (paginated, filterable list per project); UI ⬜ |
| US-05 | Detect Requirement Issues (5-Category Classification) | Must | 13 | S2 | EP-03 | Keval (classification), Heet (embeddings, candidates), Abhyudit (accuracy) | FR-07–FR-12, FR-15, DR-07, DR-09, DR-10 | ⬜ |
| US-06 | Tune Detection Thresholds per Project | Should | 5 | S5 | EP-03 | Keval, Heet, Abhijeet (settings UI) | FR-10, FR-16, FR-17, NFR-18 | ⬜ |
| US-07 | Explain Findings with Confidence Score & Context | Must | 5 | S2 | EP-03 | Keval, Abhijeet (findings UI) | FR-13, FR-14, NFR-17 | ⬜ |
| US-08 | Assign Severity to Flagged Issues | Should | 3 | S6 | EP-04 | Keval, Abhijeet | FR-42 | ⬜ |
| US-09 | Generate Clarification Questions | Must | 5 | S3 | EP-04 | Madhav | FR-22, FR-23 | ⬜ |
| US-10 | Suggest Resolutions & Human Review of Findings | Must | 5 | S3 | EP-04 | Parth (review-state API, guard), Abhijeet (review UI) | FR-18–FR-21 | ⬜ |
| US-11 | Change-Impact Analysis Engine | Must | 8 | S4 | EP-05 | Madhav (impact), Heet (relationship queries) | FR-24, FR-25 | ⬜ |
| US-12 | Maintain Requirement Version History | Must | 3 | S4 | EP-05 | Parth (backend), Pranshu (history UI) | FR-26, DR-08 | ⬜ |
| US-13 | View Requirements Quality Dashboard | Must | 5 | S5 | EP-06 | Pranshu (UI), Parth (aggregation) | FR-27, FR-28, FR-42 | ⬜ |
| US-14 | Live Requirements Map | Must | 8 | S3 | EP-15 | Dhavni didi (graph API, deltas), Abhijeet (map UI) | FR-29, FR-84, NFR-32, NFR-33 | ⬜ |
| US-15 | Dismiss / Resolve a Flag (Feedback Loop) | Should | 3 | S6 | EP-04 | Keval (tuning signal), Abhijeet (UI) | FR-18, NFR-22 | ⬜ |
| US-16 | Export Issue, Impact and Consequence Reports | Should | 5 | — | EP-06 | — | FR-30 | ⏸ Deferred |
| US-17 | Receive Executive / ROI Summary Report | Could | 5 | — | EP-09 | — | — | ⏸ Deferred |
| US-18 | Protect Compliance-Critical Requirements | Should — conditional | 5 | S6 | EP-07 | Parth (backend), Abhijeet (UI) | FR-21, FR-36, NFR-13, DR-05, DR-12 | ⬜ |
| US-19 | Authenticate via JWT (Sign-Up Only with a Code, SSO Later) | Must | 5 | S1 | EP-01 | Parth (backend), Pranshu (login UI) | FR-37, FR-38, NFR-11, NFR-12 | 🟡 Backend ✅ (login, sign-up with a code, `/auth/me`); login UI ⬜ |
| US-20 | Documented REST API for Third-Party Integration | Could | 8 | — | EP-09 | — | — | ⏸ Deferred |
| US-21 | Integrate with Jira / Confluence / GitHub | Could | 8 | — | EP-09 | — | — | ⏸ Deferred |
| US-22 | Validate Flagged Output and Workspace Flows with Low-Fidelity Previews | Could | 3 | S2 | EP-08 | Abhyudit, Affan (sessions), Abhijeet (prototypes) | FR-31, NFR-15, NFR-31 | ⬜ |
| US-23 | Capture End-Customer Feedback Trends (Outcome) | Won't | N/A | — | EP-09 | — | — | ⏸ Deferred |
| US-24 | Create a Workspace and Projects | Must | 3 | S1 | EP-10 | Parth (backend), Abhijeet (UI) | FR-43, FR-46, FR-47 | 🟡 Backend ✅ (workspaces, projects in `setup`); UI ⬜ |
| US-25 | Join a Workspace with a Code or Invite Link | Must | 5 | S1 | EP-10 | Madhav (backend), Abhijeet (UI) | FR-44, FR-77, NFR-35 | 🟡 Sign-up redeems a code ✅; join-code management API and UI ⬜ |
| US-26 | Remove Members, Change Roles, Leave a Workspace | Must | 3 | S2 | EP-10 | Parth (backend), Abhijeet (UI) | FR-45, FR-49, NFR-27 | ⬜ |
| US-27 | Enforce Roles and Permissions | Must | 5 | S1 | EP-10 | Parth (backend), Affan (permission tests) | FR-38, FR-48, NFR-11, NFR-27 | 🟡 Backend ✅ (permission catalogue, 9 default roles, `require_permission`); UI ⬜ |
| US-28 | Create and Manage Channels | Must | 3 | S2 | EP-10 | Madhav (backend), Pranshu (UI) | FR-50 | ⬜ |
| US-29 | Real-Time Messaging with Threads and Mentions | Must | 8 | S2 | EP-10 | Dhavni didi (WebSocket, event bus), Pranshu (chat UI) | FR-51, FR-52, NFR-24 | ⬜ |
| US-30 | Requirement Composer with EARS Templates | Must | 5 | S3 | EP-11 | Bansil (backend), Pranshu (composer UI) | FR-55, FR-60, FR-81, DR-15, DR-18 | ⬜ |
| US-31 | Live Analysis of a Posted Requirement | Must | 8 | S3 | EP-11 | Heet (incremental retrieval), Keval (classification, budget), Dhavni didi (queue, events) | FR-56, FR-57, NFR-25, NFR-28 | ⬜ |
| US-32 | Suggest Requirements Detected in Chat (Opt-In) | Should | 5 | — | EP-11 | — | FR-58, NFR-30, DR-15 | ⏸ Deferred |
| US-33 | Open a Change Request (Change Editor) | Must | 5 | S4 | EP-12 | Bansil (backend), Abhijeet (UI) | FR-62, FR-89, DR-14 | ⬜ |
| US-34 | Consequence Checks for a Change Request | Must | 8 | S4 | EP-12 | Madhav (checks, risk), Keval (narrative), Abhijeet (Checks and Map-preview tabs) | FR-24, FR-25, FR-63, FR-64, FR-88, NFR-26, DR-16 | ⬜ |
| US-35 | Review and Merge | Must | 5 | S4 | EP-12 | Parth (policy, merge), Abhijeet (UI) | FR-21, FR-65, FR-66, FR-88, DR-04 | ⬜ |
| US-36 | Owners, Stakeholder Groups and Ownership Requests | Should | 3 | S3 | EP-11 | Bansil (backend), Pranshu (UI) | FR-59, DR-11 | ⬜ |
| US-37 | Requirement Lifecycle States | Must | 3 | S3 | EP-11 | Parth | FR-61, DR-13 | ⬜ |
| US-38 | Inbox and Notifications | Must | 5 | S5 | EP-13 | Madhav (notification service), Abhijeet (inbox UI) | FR-69, FR-70 | ⬜ |
| US-39 | Notification Preferences and Email Digest | Could | 3 | — | EP-13 | — | FR-71 | ⏸ Deferred |
| US-40 | Baseline Snapshots and Comparison | Should | 5 | S5 | EP-14 | Parth (backend), Pranshu (UI) | FR-73, DR-08 | ⬜ |
| US-41 | Export the Updated SRS (DOCX, PDF, Markdown) | Should | 5 | S6 | EP-14 | Bansil | FR-74, FR-107, DR-02, DR-03 | ⬜ |
| US-42 | Requirement Activity Timeline | Should | 3 | S6 | EP-13 | Dhavni didi (backend), Pranshu (UI) | FR-72, DR-06, DR-08 | ⬜ |
| US-43 | Ask the Baseline (Q&A with Citations) | Could | 5 | — | EP-14 | — | FR-75, NFR-17 | ⏸ Deferred |
| US-44 | Requirements Health Analytics | Should | 5 | — | EP-06 | — | FR-76 | ⏸ Deferred |
| US-45 | AI Resolution Suggestions with Human Feedback | Must | 5 | S5 | EP-12 | Madhav (suggestion engine), Keval (prompts, feedback examples), Abhijeet (suggestion panel UI) | FR-68, FR-94, NFR-36, DR-04, DR-20 | ⬜ |
| US-46 | Search Across the Workspace | Should | 3 | — | EP-10 | — | FR-53 | ⏸ Deferred |
| US-47 | Import Meeting Notes as Candidate Requirements | Could | 5 | — | EP-11 | — | — | ⏸ Deferred |
| US-48 | Link Requirements to Work Items | Should | 3 | — | EP-12 | — | FR-67 | ⏸ Deferred |
| US-49 | Custom Roles and Permission Sets | Should | 3 | S2 | EP-10 | Parth (backend), Abhijeet (UI) | FR-78, FR-79 | ⬜ |
| US-50 | Map Preview Layer and Time Slider | Should | 5 | S6 | EP-15 | Dhavni didi (snapshots of graph state), Pranshu (UI) | FR-85 | ⬜ |
| US-51 | Live Lint, Similar Hints, Pre-Flight Check and AI Wording | Should | 5 | S5 | EP-11 | Keval (lint catalogue, dry run, AI wording), Bansil (composer wiring) | FR-82, FR-83, FR-93, NFR-34, DR-07, DR-18 | ⬜ |
| US-52 | Requirement Issues and Auto Conflict Issues | Must | 5 | S4 | EP-12 | Dhavni didi (backend, auto-open rules), Pranshu (UI) | FR-86, FR-87, SX-18 | ⬜ |
| US-53 | Discussion, Votes, Watch and Links | Should | 3 | S6 | EP-11 | Madhav | FR-80, FR-90, FR-91, DR-17, DR-19 | ⬜ |
| US-54 | Structural Change Requests and Counter-Proposals | Could | 5 | — | EP-12 | — | FR-92 | ⏸ Deferred |
| US-55 | Written Change Log and Summaries for the Map | Should | 3 | S6 | EP-15 | Dhavni didi (change sentences, summaries), Keval (AI narrative), Pranshu (Changes panel UI) | FR-95, FR-96 | ⬜ |
| US-56 | Raise a Concern (Human-Raised Findings) | Must | 3 | S4 | EP-04 | Bansil (backend), Pranshu (UI) | FR-97, DR-21 | ⬜ |
| US-57 | Decision Rules and Decision Owners per Project | Must | 3 | S5 | EP-12 | Parth (rules engine), Pranshu (settings UI) | FR-65, FR-100, DR-23 | ⬜ |
| US-58 | Rule-Based Cross-Checks for Conflicts the Similarity Filter Misses | Must | 5 | S5 | EP-03 | Heet (attribute index), Keval (attribute extraction), Abhyudit (recall measurement) | FR-101, NFR-37, DR-21 | ⬜ |
| US-59 | Open-Items Report Beside the Approved Baseline | Should | 2 | S6 | EP-14 | Bansil | FR-74, FR-102, DR-22 | ⬜ |
| US-60 | Project Context Required Before Analysis | Must | 3 | S1 | EP-10 | Bansil (context service, SRS draft of the brief), Abhijeet (setup wizard UI), Keval (context pack in prompts) | FR-47, FR-103, FR-104, FR-105, NFR-39, DR-24 | 🟡 Backend ✅ (versioned context, AI-drafted brief, activation gate); setup wizard UI and context pack in prompts ⬜ |
| US-61 | Generate the Updated SRS with the LLM and Review It | Must | 5 | S6 | EP-14 | Bansil (generator, fidelity check), Keval (section prompts), Pranshu (review UI) | FR-106, FR-107, NFR-38, DR-25 | ⬜ |

## 2. MVP Scope Note

There are **two protected demo paths**; nothing on them is ever cut:

1. **Document path (CP1 → final):** US-60, US-01, US-02, US-05, US-09, then US-61 — context first, upload, extraction, issue detection, clarification, and at the end the updated SRS.
2. **Collaboration path (CP1 → CP2):** US-24, US-25, US-27, US-29, US-30, US-31, US-14, then US-52, US-56, US-33, US-34, US-35, US-57, US-45 — join with a code, write a requirement, see it analysed and appear on the live map, get an issue when it clashes, pick or edit an AI-suggested solution, propose the change, see its checks, review and merge.

The trust layer (US-56, US-57, US-58) is also never cut. If a checkpoint slips, cut in the order of [`IT314_RCD_Epics_v5.md` §5](../planning/v5/IT314_RCD_Epics_v5.md#5-cut-order-if-the-schedule-slips):

| Order | Cut | Points freed |
|---|---|---|
| 1 | US-53 Discussion, votes, watch, links | 3 |
| 2 | US-50 Map preview and time slider (live map remains) | 5 |
| 3 | US-49 Custom roles (defaults remain) | 3 |
| 4 | US-18 Compliance queue (the protected guard remains) | 5 |
| 5 | US-55 Change summaries (the one-line feed of US-14 remains) | 3 |
| 6 | US-15 Feedback loop view | 3 |
| 7 | US-42 Activity timeline | 3 |
| 8 | US-08 Severity overrides (system-proposed severity remains) | 3 |
| 9 | US-41 DOCX and PDF export (Markdown download in US-61 remains) | 5 |

**US-05 (issue detection) is the core value and is protected before any other feature.**

## 3. Deferred / Post-MVP Backlog

| ID | Story | Points | Why deferred |
|---|---|---|---|
| US-16 | Export Issue, Impact and Consequence Reports | 5 | Rev. 4: no new charts or exports until the core workflow is proven |
| US-17 | Executive / ROI Summary Report | 5 | Post-MVP (EP-09) |
| US-20 | Documented REST API for Third-Party Integration | 8 | Post-MVP (EP-09) |
| US-21 | Jira / Confluence / GitHub Integration | 8 | Post-MVP (EP-09) |
| US-32 | Suggest Requirements Detected in Chat (Opt-In) | 5 | Rev. 4 (privacy and cost; SX-04) |
| US-39 | Notification Preferences and Email Digest | 3 | No SMTP in the MVP (SX-21) |
| US-43 | Ask the Baseline (Q&A with Citations) | 5 | Rev. 2 |
| US-44 | Requirements Health Analytics | 5 | Rev. 4 |
| US-46 | Search Across the Workspace | 3 | Rev. 3; map search and table filters cover the MVP |
| US-47 | Import Meeting Notes as Candidate Requirements | 5 | Could; not scheduled |
| US-48 | Link Requirements to Work Items | 3 | Rev. 5, to make room for US-60 and US-61 (SX-33) |
| US-54 | Structural Change Requests and Counter-Proposals | 5 | Could; not scheduled |
| US-23 | End-Customer Feedback Trends | n/a | Outcome story, no development task |

The post-semester roadmap is [`IT314_RCD_Scope_Extension_v5.md` §12](../planning/v5/IT314_RCD_Scope_Extension_v5.md#12-extensions-after-this-semester).

## 4. Full Acceptance Criteria

Each story's card — As a / I want / So that, acceptance criteria, owners and trace — is in [`IT314_RCD_Product_Backlog_v5.md` §3](../planning/v5/IT314_RCD_Product_Backlog_v5.md#3-detailed-story-cards). This overview is a summary index; see `feature-deep-dive.md` for the stories on the protected demo paths.
