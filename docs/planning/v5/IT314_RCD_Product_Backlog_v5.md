# Consolidated Product Backlog v3.4

**User Stories — AI Requirements Conflict Detector (collaborative workspace scope, revision 2)**

*IT314 — Software Engineering | Reconciled from 7 team drafts (v1), conflict-reviewed in Step 6 (v2), widened for a 10-member semester in Step 7 (v3), extended with join codes, roles, requirement actions, the live map and GitHub-style collaboration (v3.1)*

## 0. What Changed

| | |
|---|---|
| **Stories** | 61 (US-01–US-61). US-01–US-23 keep their IDs; US-24–US-48 came in v3; US-49–US-54 in v3.1; US-55 in v3.2; US-56–US-59 in v3.3; **US-60–US-61 in v3.4** |
| **Points** | **284 total · 224 scheduled** in Sprints 1–6 (37 · 38 · 37 · 37 · 38 · 37) · 60 deferred (US-16, US-17, US-20, US-21, US-32, US-39, US-43, US-44, US-46, US-47, US-48, US-54) · US-23 is an outcome story with no points |
| **Priorities (points)** | Must 168 · Should 74 · Could 42 (3 of them scheduled: US-22) |
| **Traces** | Canonical numbering of `IT314_RCD_Requirements_Spec_v5.md` (FR-01–FR-107, NFR-01–NFR-39, DR-01–DR-25) |
| **Fields** | Every card states its **Sprint**, **Epic** and **Owners** (primary first), following `IT314_RCD_Sprint_Plan_v5.md` §2. Screens are in `IT314_RCD_Interface_Design_v5.md` |
| **Changed in v3.1** | **US-14** becomes the Must "Live Requirements Map" (8 pts, Sprint 3, new EP-15) · **US-25** becomes join by code or link · **US-27** permission-based · **US-30** EARS composer · **US-33/34/35** pull-request style · **US-36** adds ownership requests · **US-19** sign-up only with a code · moved: US-08 → S4, US-32 → S6, US-42 → S6, US-46 → S6 · deferred: US-39 (email), US-43 (Q&A) |
| **New in v3.1** | US-49 Custom roles · US-50 Map preview and time slider · US-51 Lint, similar hints, pre-flight, AI wording · US-52 Issues and auto conflict issues · US-53 Discussion, votes, watch, links · US-54 Structural change requests (deferred) |
| **Changed in v3.4 (context and updated SRS)** | New: **US-60** project context (initial SRS or brief) compulsory before analysis, with a context pack in every LLM prompt (S1); **US-61** LLM-generated updated SRS with readiness checklist, section review, fidelity check and publishing (S6). Changed: US-24 (setup wizard), US-05 and US-31 (prompts carry the context pack), US-41 (exports the published SRS in DOCX, PDF and Markdown). Deferred to make room: **US-48** work-item links |
| **Changed in v3.3 (trust review)** | New: **US-56** human-raised concerns, **US-57** decision rules and decision owners, **US-58** rule-based cross-checks, **US-59** open-items report. Tightened: US-33/35/37 (agreement rules, approvals tied to the proposal revision), US-34 (findings delta), US-45 (structured feedback, no self-learning claim), US-41 (approved-only export). Deferred to make room: US-16, US-32, US-44 (no extra charts or AI features until the core workflow is proven). Moved: US-08, US-53, US-50 → S6 |
| **Changed in v3.2** | **US-45** becomes the Must "AI Resolution Suggestions with Human Feedback" for every finding category (5 pts, Sprint 5) · **US-55** new: written change log and summaries beside the map · **US-14** gains a basic written feed · US-48 → S6 · US-46 deferred |

**Merge decisions carried over:** classification is one core story (US-05) with the five-category taxonomy (ADR-02); every story is traced to a requirement; enterprise extensions are marked Could/Won't. Step 6 decisions CR-16, CR-17, CR-19 and CR-23 still apply; CR-20 and CR-22 are superseded by SX-03 and SX-01.

## 1. Backlog Summary

| ID | Title | Stakeholder | Priority | Pts | Sprint | Epic |
|---|---|---|---|---|---|---|
| US-01 | Upload SRS Document into a Project | Business Analyst | Must | 5 | S1 | EP-02 |
| US-02 | Automatic Requirement Extraction | Business Analyst | Must | 5 | S1 | EP-02 |
| US-03 | Track Long-Running Analysis Progress | Business Analyst / IT-DevOps | Must | 3 | S1 | EP-02 |
| US-04 | View Extracted Requirements List | Business Analyst | Must | 3 | S1 | EP-02 |
| US-05 | Detect Requirement Issues (5-Category Classification) | Business Analyst, Project Manager | Must | 13 | S2 | EP-03 |
| US-06 | Tune Detection Thresholds per Project | Software Architect | Should | 5 | S5 | EP-03 |
| US-07 | Explain Findings with Confidence Score & Context | Business Analyst | Must | 5 | S2 | EP-03 |
| US-08 | Assign Severity to Flagged Issues | Business Analyst, Product Owner | Should | 3 | S6 | EP-04 |
| US-09 | Generate Clarification Questions | Business Analyst, QA Engineer | Must | 5 | S3 | EP-04 |
| US-10 | Suggest Resolutions & Human Review of Findings | Business Analyst, Software Architect | Must | 5 | S3 | EP-04 |
| US-11 | Change-Impact Analysis Engine | Project Manager, Software Architect | Must | 8 | S4 | EP-05 |
| US-12 | Maintain Requirement Version History | Business Analyst | Must | 3 | S4 | EP-05 |
| US-13 | View Requirements Quality Dashboard | Product Owner, Business Analyst | Must | 5 | S5 | EP-06 |
| US-14 | Live Requirements Map | All members | Must | 8 | S3 | EP-15 |
| US-15 | Dismiss / Resolve a Flag (Feedback Loop) | Business Analyst | Should | 3 | S6 | EP-04 |
| US-16 | Export Issue, Impact and Consequence Reports | Project Manager | Should | 5 | — | EP-06 |
| US-17 | Receive Executive / ROI Summary Report | Executive Sponsor | Could | 5 | — | EP-09 |
| US-18 | Protect Compliance-Critical Requirements | Legal / Compliance Officer | Should — conditional | 5 | S6 | EP-07 |
| US-19 | Authenticate via JWT (Sign-Up Only with a Code, SSO Later) | System Administrator, All Users | Must | 5 | S1 | EP-01 |
| US-20 | Documented REST API for Third-Party Integration | Third-Party API Consumer | Could | 8 | — | EP-09 |
| US-21 | Integrate with Jira / Confluence / GitHub | IT / DevOps, Project Manager | Could | 8 | — | EP-09 |
| US-22 | Validate Flagged Output and Workspace Flows with Low-Fidelity Previews | QA Engineer, Contributors | Could | 3 | S2 | EP-08 |
| US-23 | Capture End-Customer Feedback Trends (Outcome) | End Customer (Indirect) | Won't | N/A | — | EP-09 |
| US-24 | Create a Workspace and Projects | Project Manager / Owner | Must | 3 | S1 | EP-10 |
| US-25 | Join a Workspace with a Code or Invite Link | Project Manager, all members | Must | 5 | S1 | EP-10 |
| US-26 | Remove Members, Change Roles, Leave a Workspace | Project Manager / Admin | Must | 3 | S2 | EP-10 |
| US-27 | Enforce Roles and Permissions | IT/DevOps, Legal / Compliance | Must | 5 | S1 | EP-10 |
| US-28 | Create and Manage Channels | Business Analyst, Project Manager | Must | 3 | S2 | EP-10 |
| US-29 | Real-Time Messaging with Threads and Mentions | All Members | Must | 8 | S2 | EP-10 |
| US-30 | Requirement Composer with EARS Templates | Stakeholder Contributor | Must | 5 | S3 | EP-11 |
| US-31 | Live Analysis of a Posted Requirement | Stakeholder Contributor, Business Analyst | Must | 8 | S3 | EP-11 |
| US-32 | Suggest Requirements Detected in Chat (Opt-In) | Business Analyst | Should | 5 | — | EP-11 |
| US-33 | Open a Change Request (Change Editor) | Stakeholder Contributor, Project Manager | Must | 5 | S4 | EP-12 |
| US-34 | Consequence Checks for a Change Request | Project Manager, Software Architect | Must | 8 | S4 | EP-12 |
| US-35 | Review and Merge | Product Owner, Business Analyst | Must | 5 | S4 | EP-12 |
| US-36 | Owners, Stakeholder Groups and Ownership Requests | Project Manager | Should | 3 | S3 | EP-11 |
| US-37 | Requirement Lifecycle States | Product Owner, Business Analyst | Must | 3 | S3 | EP-11 |
| US-38 | Inbox and Notifications | All Members | Must | 5 | S5 | EP-13 |
| US-39 | Notification Preferences and Email Digest | Project Manager | Could | 3 | — | EP-13 |
| US-40 | Baseline Snapshots and Comparison | Product Owner, Legal / Compliance | Should | 5 | S5 | EP-14 |
| US-41 | Export the Updated SRS (DOCX, PDF, Markdown) | Business Analyst, Client | Should | 5 | S6 | EP-14 |
| US-42 | Requirement Activity Timeline | Business Analyst, Legal / Compliance | Should | 3 | S6 | EP-13 |
| US-43 | Ask the Baseline (Q&A with Citations) | Business Analyst, QA Engineer | Could | 5 | — | EP-14 |
| US-44 | Requirements Health Analytics | Project Manager, Product Owner | Should | 5 | — | EP-06 |
| US-45 | AI Resolution Suggestions with Human Feedback | Business Analyst, requirement owners | Must | 5 | S5 | EP-12 |
| US-46 | Search Across the Workspace | Business Analyst, QA Engineer | Should | 3 | — | EP-10 |
| US-47 | Import Meeting Notes as Candidate Requirements | Business Analyst | Could | 5 | — | EP-11 |
| US-48 | Link Requirements to Work Items | Project Manager | Should | 3 | — | EP-12 |
| US-49 | Custom Roles and Permission Sets | Workspace Owner, Project Manager | Should | 3 | S2 | EP-10 |
| US-50 | Map Preview Layer and Time Slider | Project Manager, Product Owner | Should | 5 | S6 | EP-15 |
| US-51 | Live Lint, Similar Hints, Pre-Flight Check and AI Wording | Stakeholder Contributor, QA Engineer | Should | 5 | S5 | EP-11 |
| US-52 | Requirement Issues and Auto Conflict Issues | Project Manager, requirement owners | Must | 5 | S4 | EP-12 |
| US-53 | Discussion, Votes, Watch and Links | All members | Should | 3 | S6 | EP-11 |
| US-54 | Structural Change Requests and Counter-Proposals | Business Analyst | Could | 5 | — | EP-12 |
| US-55 | Written Change Log and Summaries for the Map | All members | Should | 3 | S6 | EP-15 |
| US-56 | Raise a Concern (Human-Raised Findings) | All stakeholders | Must | 3 | S4 | EP-04 |
| US-57 | Decision Rules and Decision Owners per Project | Project Manager, Compliance | Must | 3 | S5 | EP-12 |
| US-58 | Rule-Based Cross-Checks for Conflicts the Similarity Filter Misses | Business Analyst, QA | Must | 5 | S5 | EP-03 |
| US-59 | Open-Items Report Beside the Approved Baseline | Product Owner | Should | 2 | S6 | EP-14 |
| US-60 | Project Context Required Before Analysis | Project Manager | Must | 3 | S1 | EP-10 |
| US-61 | Generate the Updated SRS with the LLM and Review It | Business Analyst, Project Manager | Must | 5 | S6 | EP-14 |

## 2. MVP Scope Note

There are **two protected demo paths**, and nothing on them is ever cut:

1. **Document path (CP1 → final):** **US-60**, US-01, US-02, US-05, US-09, then **US-61** — context first, upload, extraction, issue detection, clarification, and at the end the updated SRS.
2. **Collaboration path (CP1 → CP2):** US-24, US-25, US-27, US-29, US-30, US-31, **US-14**, then **US-52**, **US-56**, US-33, US-34, US-35, **US-57**, **US-45** — a team joins with a code, writes a requirement, sees it analysed and appear on the live map, gets an issue when it clashes with someone else's requirement, picks or edits an AI-suggested solution, proposes the change, sees its checks, reviews and merges it.

If a checkpoint slips, cut in the order of `IT314_RCD_Epics_v5.md` §5. US-16, US-17, US-20, US-21, US-32, US-39, US-43, US-44, US-46, US-47, US-48, US-54 and the SSO extension of US-19 are post-MVP (`IT314_RCD_Scope_Extension_v5.md` §12). Issue detection (US-05) is the core value and is protected before any other feature.

## 3. Detailed Story Cards

Format: *As a … I want … so that …*, then acceptance criteria (AC). Owners: primary first. "Carried over" means the backend was built in the earlier Sprints 0–1. "Can" in an AC always means "can, if their permissions allow it" (`IT314_RCD_Requirements_Spec_v5.md` §1.22).

---

### EP-01 · Platform Foundation and Access

#### US-19 — Authenticate via JWT (Sign-Up Only with a Code, SSO Later)
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Must | 5 | S1 | Parth (backend), Pranshu (login UI) | FR-37, FR-38, NFR-11, NFR-12 |

*As a user, I want to sign in securely before I can see any workspace, so that my organisation's data stays protected.*

**AC**
- JWT authentication is required for every REST route and for the WebSocket handshake; an invariant test fails if any route is unauthenticated.
- There is no open sign-up: an account is created only with a valid join code or invite link (US-25); the CLI creates only the first platform admin (SX-02).
- The SPA has a login screen, stores the token in memory with silent re-login on expiry, and signs out cleanly (closes gap D1).
- (Enterprise extension) SSO/LDAP can replace token decoding without a redesign.

*Carried over: login, `/auth/me`, RBAC skeleton. Merged from drafts E, G, F, C.*

---

### EP-02 · Document Ingestion and Processing Visibility

#### US-01 — Upload SRS Document into a Project
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Must | 5 | S1 | Parth (API), Pranshu (UI) | FR-01, FR-02, FR-04, FR-54 |

*As a Business Analyst, I want to upload an SRS in PDF or DOCX into a project, either as the baseline or as proposals, so that I can start analysis without re-entering existing documents.*

**AC**
- A supported file (.pdf, .docx) returns a document ID and initial status; unsupported, corrupted or oversized files (default 25 MB, configurable) are rejected with a specific error and nothing is stored (CR-16).
- The uploader chooses **import as baseline** (analyst, admin or owner only; requirements become Approved) or **import as proposals** (requirements become Proposed) (SX-08).
- An optional stakeholder group can be supplied at upload (FR-05).
- Uploading from a channel shows the document and its progress in that channel (FR-54).

*Carried over: upload API and validation. Plain text is a Could; ReqIF is deferred with US-21.*

#### US-02 — Automatic Requirement Extraction
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Must | 5 | S1 | Bansil | FR-03, FR-04 |

*As a Business Analyst, I want the document split automatically into individual requirement statements, so that I don't enumerate hundreds of requirements by hand.*

**AC**
- Raw text is extracted from PDF/DOCX and segmented along the document's own boundaries; wording is never rewritten (CR-06).
- Printed IDs are preserved; an item with no printed ID is stored without one.
- Non-requirement content (TOC, headers, footers, prose) is excluded.
- Extraction failures or low-confidence segments are surfaced for manual review, never silently dropped.

#### US-03 — Track Long-Running Analysis Progress
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Must | 3 | S1 | Dhavni didi (Celery), Pranshu (UI) | Operational (supports FR-03–FR-17), FR-52 |

*As a Business Analyst, I want to see the progress of analysis, so that I know the system is working and roughly how long it will take.*

**AC**
- Analysis runs as a background job and never blocks the API or UI.
- Status is queued / processing / done / failed (`done` shown as "Complete"), with progress mapped to pipeline stages.
- From Sprint 2 the UI updates by WebSocket event; polling remains the fallback.
- Failed jobs show a readable reason and the stage that failed.

#### US-04 — View Extracted Requirements List
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Must | 3 | S1 | Parth (API), Pranshu (UI) | FR-03, FR-05, FR-60 |

*As a Business Analyst, I want to browse the parsed requirements of a project, so that I can verify extraction before trusting the analysis.*

**AC**
- Paginated, searchable list with ID, text, state, owner, origin and issue badges.
- Reflects live backend data and filters by state and origin (document, post, change request).
- An empty or failed extraction shows an explanatory state.

*Carried over: list API.*

---

### EP-03 · Issue Detection Engine (core value)

#### US-05 — Detect Requirement Issues (5-Category Classification)
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Must | 13 | S2 | Keval (classification), Heet (embeddings, candidates), Abhyudit (accuracy) | FR-07–FR-12, FR-15, DR-07, DR-09, DR-10 |

*As a Business Analyst, I want requirements and candidate pairs classified as Conflicting, Duplicate, Ambiguous, Incomplete or Dependent, so that I find real problems without cross-checking every pair.*

**AC**
- Candidate pairs come from the embedding pre-filter, not all-pairs; similarity never decides a category alone.
- Conflicting, Duplicate and Dependent come from pairs; Ambiguous and Incomplete are assessed per requirement against recognised patterns (DR-07).
- Each finding names all requirements involved; flagged pairs are shown side by side with the problem clause highlighted where possible; Incomplete states what is missing where determinable.
- Schema-invalid output is retried up to 3 times; a pair that still fails is recorded as failed (gap G1), never dropped.
- The same engine is callable for one requirement against a baseline, so US-31 and US-34 reuse it unchanged.
- Precision, recall and F1 per category are reported on the benchmark at CP1. **Recall** is the headline number, including planted conflicts that fall below the similarity threshold (complemented by US-58).

- Every prompt carries the project context pack (US-60, FR-105); each finding records the `context_version` it used.

**Tasks (D5 split):** 5a conflicts (5 pts) · 5b duplicates and ambiguous (4 pts) · 5c incomplete and dependent (4 pts).

#### US-07 — Explain Findings with Confidence Score & Context
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Must | 5 | S2 | Keval, Abhijeet (findings UI) | FR-13, FR-14, NFR-17 |

*As a Business Analyst, I want every finding to show an explanation, a confidence score and context, so that I can judge reliability before acting.*

**AC**
- Every finding shows confidence (0–100%) next to its category.
- Findings below the project's confidence threshold are marked "low confidence — recommend manual review".
- A rationale and related requirement IDs plus the source section or originating post accompany every flag.

#### US-06 — Tune Detection Thresholds per Project
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Should | 5 | S5 | Keval, Heet, Abhijeet (settings UI) | FR-10, FR-16, FR-17, NFR-18 |

*As a Software Architect, I want to adjust the thresholds and criteria per project, so that flags match our team's definitions.*

**AC**
- Similarity and confidence thresholds and ambiguity/dependency criteria are configurable per project without a code change; ambiguity criteria are edited in the pattern catalogue (SC-3).
- A preview shows example flagged and unflagged pairs at a candidate threshold before saving.
- Changes apply on re-analysis without re-uploading.

#### US-58 — Rule-Based Cross-Checks for Conflicts the Similarity Filter Misses
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Must | 5 | S5 | Heet (attribute index), Keval (attribute extraction), Abhyudit (recall measurement) | FR-101, NFR-37, DR-21 |

*As a Business Analyst, I want conflicts found even when two requirements are worded very differently, so that "no issue detected" is not just a sign that the similarity filter skipped the pair.*

**AC**
- Each requirement is parsed into structured attributes where possible: subject or entity, metric, numeric value and unit, comparison (≤, ≥, =), actor, condition, negation and modality (shall, may, shall not).
- Deterministic checks compare requirements that share an entity or metric **regardless of embedding similarity**: different numeric limits for the same metric and condition, "shall" versus "shall not" for the same action, the same action given to different actors, overlapping conditions with different responses.
- Findings from these checks carry the source **Rule** and the rule that fired, and enter the same review workflow as AI findings (ADR-25); the LLM may be asked to confirm, but a rule finding is never dropped because the model disagrees.
- Recall is measured on the labelled benchmark **including planted conflicts whose similarity is below the threshold**; the report shows how many each layer (similarity + AI, rule checks, people) caught (NFR-37).

---

### EP-04 · Clarification, Triage and Human Review

#### US-08 — Assign Severity to Flagged Issues
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Should | 3 | S6 | Keval, Abhijeet | FR-42 |

*As a Business Analyst, I want each issue to carry a severity, so that I triage the most valuable problems first.*

**AC**
- Every finding carries Low, Medium or High, proposed by the system and overridable by a reviewer with the override recorded.
- Lists can be filtered and sorted by severity; severity feeds the risk level of consequence reports (US-34).
- Severity and confidence are shown as separate fields ("how bad" versus "how sure").

#### US-09 — Generate Clarification Questions
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Must | 5 | S3 | Madhav | FR-22, FR-23 |

*As a Business Analyst, I want a specific question for every Ambiguous, Incomplete or Conflicting finding, so that I can take it straight to the right stakeholder.*

**AC**
- Each such flag has a question specific to its requirements; generic or empty questions count as a failure and are retried.
- A QA engineer can resolve the issue from the question alone.
- For a requirement post, the question appears on the result card and @mentions the requirement's owner; for a conflict issue it is the issue's first comment (SX-18).
- The question can be marked Answered with resolution text, stored in the requirement's history.

#### US-10 — Suggest Resolutions & Human Review of Findings
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Must | 5 | S3 | Parth (review-state API, guard), Abhijeet (review UI) | FR-18–FR-21 |

*As a Business Analyst, I want to accept, dismiss, merge or reclassify a finding, optionally guided by an AI suggestion, so that the issue list holds only real work and I stay in control.*

**AC**
- Review states: open, accepted, dismissed, merged, reclassified; "resolved" = accepted and its clarification answered or its change approved; "rejected" applies to an AI suggestion (CR-18).
- The original AI finding is retained after any human correction.
- AI suggestions are labelled and need explicit approval; adopting one that changes text opens a change request (DR-14).
- The review panel is reachable from the finding, the conflict issue (US-52) and the map.
- A finding involving a protected requirement can only be acted on by a compliance reviewer (CR-19 guard). Status changes update counts and filters immediately.
- Findings from every source — AI, Rule (US-58) and Person (US-56) — use this same review workflow, and the source is always shown.

#### US-15 — Dismiss / Resolve a Flag (Feedback Loop)
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Should | 3 | S6 | Keval (tuning signal), Abhijeet (UI) | FR-18, NFR-22 |

*As a Business Analyst, I want my false-positive and resolved decisions logged as feedback, so that the tool gets more accurate over time.*

**AC**
- Dismissed flags are hidden by default but restorable (the actions themselves are US-10, CR-17).
- False-positive feedback is logged per category and pattern; once a configurable threshold accumulates, the rule is surfaced for tuning.
- Dismissal reasons and suggestion feedback (US-45) are shown together in one "AI feedback" report per project.
- Counts and filters update immediately.

#### US-56 — Raise a Concern (Human-Raised Findings)
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Must | 3 | S4 | Bansil (backend), Pranshu (UI) | FR-97, DR-21 |

*As a stakeholder, I want to flag a problem the AI did not find — for example a contractual promise or an operational limit it cannot know — so that my concern is handled with the same seriousness as an AI finding and does not disappear because the AI saw no conflict.*

**AC**
- From a requirement, a pair of requirements, the map or a channel message, a member with `issue.open` chooses **Raise a concern**: category (one of the five, or "Other"), involved requirements, explanation, and an optional external reference (e.g. "Contract §7.2").
- It creates a finding with source **Person** (author shown) and an issue, and follows the same workflow as AI findings: severity, clarification, AI suggestions on request, review, change requests, decision owner (US-57).
- Source is always visible on findings, issues, result cards and the map (AI · Rule · Person); filters by source exist.
- A human-raised finding can be closed only by the decision owner with a reason; the AI's opinion ("no conflict detected") is shown as information, never as a reason to close.
- When a person raises a concern the AI had not flagged on the same requirements, it is counted as an **AI miss** for evaluation (NFR-37).

---

### EP-05 · Change Impact and Version History

#### US-11 — Change-Impact Analysis Engine
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Must | 8 | S4 | Madhav (impact), Heet (relationship queries) | FR-24, FR-25 |

*As a Project Manager, I want to see everything a proposed change could affect, so that I can judge scope and risk before it is approved.*

**AC**
- For proposed text, lists affected requirements with the reason for each link, without saving anything (read-only, OD §4).
- Distinguishes direct from transitive impact where relationships support it.
- States explicitly when there is no downstream impact.
- Results are delivered inside the consequence report (US-34) and exportable as PDF/CSV (US-16). Requirements only; design and test-case impact need US-21 (CR-09). *(Changed by SX-03: editing now happens through change requests, not here.)*

#### US-12 — Maintain Requirement Version History
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Must | 3 | S4 | Parth (backend), Pranshu (history UI) | FR-26, DR-08 |

*As a Business Analyst, I want every requirement's versions kept and comparable, so that I understand what changed and why.*

**AC**
- Every approved change request and every pre-approval correction adds a version; earlier versions never change.
- Each version links to the change request or correction that produced it, its author and its approvers.
- A version can be compared (diff) with the previous one; history stays available after deprecation.

---

### EP-06 · Insight and Reporting

#### US-13 — View Requirements Quality Dashboard
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Must | 5 | S5 | Pranshu (UI), Parth (aggregation) | FR-27, FR-28, FR-42 |

*As a Product Owner, I want a dashboard per project and across the workspace, so that I can gauge requirements quality and decide whether sign-off is safe.*

**AC**
- Counts of findings by category, severity and status; requirements by lifecycle state; open change requests by risk; issues opened and closed.
- Drill-down from any count to the underlying list.
- Filters by requirement ID, type, stakeholder group, owner, status and priority; role-appropriate default filters (NFR-16).
- Updates live after analysis runs and decisions; dashboard numbers equal a direct database count on demo data.

#### US-16 — Export Issue, Impact and Consequence Reports
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Should | 5 | — | — | FR-30 |

*As a Project Manager, I want reports (findings, impact, change-request checks) I can share, so that the information reaches people outside the tool.*

**AC**
- Findings, impact and consequence reports export as PDF and CSV on demand.
- Exports respect the user's permissions and state their filters and generation time.
- Scheduled email delivery is US-39; webhook and PM-tool delivery are post-MVP and must retry and log failures (CR-10).

#### US-44 — Requirements Health Analytics
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Should | 5 | — | — | FR-76 |

*As a Project Manager, I want analytics on how our requirements behave over time, so that I can see where the risk concentrates.*

**AC**
- Volatility: changes per requirement and per stakeholder group over time.
- Conflict hotspots: requirements and groups with the most open conflicts.
- A stakeholder-group contention matrix: how often each pair of groups conflicts.
- Time from proposal to decision. All metrics are computed from recorded data, with their definitions shown (DR-16).

---

### EP-07 · Compliance and Governance (conditional)

#### US-18 — Protect Compliance-Critical Requirements
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Should — conditional on regulated scope | 5 | S6 | Parth (backend), Abhijeet (UI) | FR-21, FR-36, NFR-13, DR-05, DR-12 |

*As a Compliance Officer, I want compliance-critical requirements routed to mandatory manual review, so that regulatory requirements are never silently altered or removed.*

**AC**
- Requirements can be tagged protected at import or afterwards.
- A manual review queue lists findings and change requests involving protected requirements; sign-off is recorded.
- Every action on a protected requirement, including viewing, is in an exportable, immutable audit trail.

*The guard itself is delivered earlier, in US-10 (findings) and US-35 (change requests). Closes gap D2.*

---

### EP-08 · Validation, Hardening and Delivery

#### US-22 — Validate Flagged Output and Workspace Flows with Low-Fidelity Previews
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Could | 3 | S2 | Abhyudit, Affan (sessions), Abhijeet (prototypes) | FR-31, NFR-15, NFR-31 |

*As a QA Engineer, I want sample users to try low-fidelity versions of the findings view, the requirement post and the consequence report, so that we fix usability problems before building them.*

**AC**
- At least 5 sessions with sample users (classmates outside the team count); a reviewer can judge whether a test case could be written from a flagged item.
- A new contributor can find a channel and post a requirement on the prototype within 5 minutes (NFR-31).
- Every usability gap is logged against the relevant story before implementation. A validation activity, not a product mode (CR-13).

---

### EP-09 · Enterprise Integration and Outcomes (post-MVP)

#### US-17 — Receive Executive / ROI Summary Report
| Priority | Pts | Sprint | Trace |
|---|---|---|---|
| Could | 5 | — | FR-32, FR-33 |

*As an Executive Sponsor, I want a periodic summary of conflicts caught, decisions made and adoption, so that I can justify wider rollout.* **AC:** monthly aggregated report; metrics computed from system data; cost and time-saved only as labelled user-supplied estimates; readable without the dashboard.

#### US-20 — Documented REST API for Third-Party Integration
| Priority | Pts | Sprint | Trace |
|---|---|---|---|
| Could | 8 | — | FR-40, NFR-06, NFR-20 |

*As an external developer, I want a documented, versioned API, so that I can integrate analysis into our pipeline.* **AC:** OpenAPI spec with examples; versioned; documented and enforced rate limits with structured errors; uses the `service` role and project scoping.

#### US-21 — Integrate with Jira / Confluence / GitHub
| Priority | Pts | Sprint | Trace |
|---|---|---|---|
| Could | 8 | — | FR-39, NFR-20 |

*As a System Administrator, I want the workspace connected to our tools, so that issues and requirements stay in sync.* **AC:** export findings as Jira tickets; import requirements from Confluence/GitHub; per-project enable/disable. Work-item links (US-48) become live syncs here.

#### US-23 — Capture End-Customer Feedback Trends (Outcome)
| Priority | Pts | Trace |
|---|---|---|
| Won't this iteration | N/A | Outcome (FR-41 post-MVP) |

*As an end customer, I want products to ship with fewer requirement-driven defects.* Measured indirectly across releases; no development task.

---

### EP-10 · Workspace, Joining and Roles

#### US-24 — Create a Workspace and Projects
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Must | 3 | S1 | Parth (backend), Abhijeet (UI) | FR-43, FR-46, FR-47 |

*As a project manager, I want to create a workspace and projects inside it, so that each product's requirements and discussions live in their own place.*

**AC**
- An authenticated user creates a workspace and becomes its owner.
- Owners and admins create projects with a name, description and default settings (thresholds, budget, required approvals); each new project gets a `#general` channel.
- A user in several workspaces can switch between them; the last-used one opens by default.
- A new project opens the setup wizard, whose context step is compulsory (US-60).

#### US-60 — Project Context Required Before Analysis
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Must | 3 | S1 | Bansil (context service, SRS draft of the brief), Abhijeet (setup wizard UI), Keval (context pack in prompts) | FR-47, FR-103, FR-104, FR-105, NFR-39, DR-24 |

*As a Project Manager, I want to give each project its context — an initial SRS or a short brief — before anyone posts requirements, so that the AI knows what the product is, who its users are and what our terms mean, and classifies requirements correctly.*

**AC**
- Creating a project opens a setup wizard whose context step cannot be skipped: **Upload initial SRS**, **Write a brief**, or both. Required brief fields: purpose and problem, scope in and out, user classes and actors, operating environment and domain; optional glossary, constraints and assumptions, quality goals, regulations and references.
- With an uploaded SRS, its requirements are extracted (US-02, imported as baseline or proposals) and the brief fields are **drafted by the LLM** from its introduction and overall description; each drafted field is labelled *AI-drafted* until the PM confirms or edits it.
- Until the context is confirmed the project shows **Setup**: members can join and chat, but the composer, document analysis and change requests are disabled with a message naming the missing fields. Confirming makes it **Active**.
- Every LLM prompt for the project includes the context pack (brief summary, actors, matched glossary terms, up to three relevant initial-SRS sections; at most 1,500 tokens); findings record the `context_version`.
- Members with `project.context` can edit the context later; each edit is a new version with author and reason and offers to re-run analysis of open findings.
- The CP1 accuracy report includes a run **with and without** the context pack (NFR-39).

#### US-25 — Join a Workspace with a Code or Invite Link
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Must | 5 | S1 | Madhav (backend), Abhijeet (UI) | FR-44, FR-77, NFR-35 |

*As a project manager, I want to share a join code so that colleagues and client stakeholders can join the workspace or a project with the right role, without me creating accounts or needing email.*

**AC**
- Owners, admins and PMs create a code (and matching link) for the workspace or one project with a default role, expiry (1, 7 or 30 days), maximum uses and an optional "require approval"; a code can never grant Owner or Admin (SX-14).
- A person signs up (or signs in) and enters the code; without approval they join immediately with the code's role, otherwise a join request appears for PMs and admins to approve (choosing the role) or deny.
- Codes are random (≥ 40 bits), stored hashed, shown in full only when created, listed with uses and expiry, and revocable; attempts are rate-limited, and invalid, expired or used-up codes give one generic error (NFR-35).
- New members land in `#general` with an onboarding checklist (NFR-31). Every code creation, use, revocation and approval is audited.

*Replaces "Invite Members by Email" (SX-21: email delivery is post-MVP).*

#### US-27 — Enforce Roles and Permissions
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Must | 5 | S1 | Parth (backend), Affan (permission tests) | FR-38, FR-48, NFR-11, NFR-27 |

*As a compliance officer, I want every action limited by the member's role in that workspace, so that people can do only what they are entitled to.*

**AC**
- The `memberships` table replaces the global role (migration `0004`, SX-06); existing users are mapped without data loss.
- Authorisation checks **permissions, never role names** (ADR-20); the nine default roles are seeded with the permissions of `IT314_RCD_Requirements_Spec_v5.md` §1.22; a parametrised test covers every permission × default role.
- The UI shows only the actions a member is allowed (FR-80).
- Another workspace's or project's resource returns 404 (ADR-12).
- Role and membership are re-read on every request, so changes apply immediately.

#### US-26 — Remove Members, Change Roles, Leave a Workspace
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Must | 3 | S2 | Parth (backend), Abhijeet (UI) | FR-45, FR-49, NFR-27 |

*As a workspace owner, I want to remove members and change roles, so that access always matches the current team.*

**AC**
- Owners, admins and PMs (for their projects) change roles or remove members; access ends on the next request and open WebSockets close within 5 s.
- The removed member's messages, posts and decisions stay, attributed as "former member"; their open change requests, approvals and owned requirements appear in a "needs reassignment" list (SX-11).
- A member can leave; the last owner must transfer ownership first.
- Every membership change is audited.

#### US-49 — Custom Roles and Permission Sets
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Should | 3 | S2 | Parth (backend), Abhijeet (UI) | FR-78, FR-79 |

*As a workspace owner or project manager, I want to create roles such as "Client reviewer" or "Tech lead" from a list of permissions, and give someone a different role inside one project, so that access matches how our organisation actually works.*

**AC**
- Owners and admins create, edit and delete custom roles by ticking permissions from the catalogue; the page states in one sentence what the role can and cannot do.
- The nine default roles cannot be edited or deleted; a role in use cannot be deleted until its members are reassigned.
- A PM can set a project-level role for a member of their project, never with more permissions than the PM has.
- Changes apply on the member's next request and are audited.

#### US-28 — Create and Manage Channels
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Must | 3 | S2 | Madhav (backend), Pranshu (UI) | FR-50 |

*As a Business Analyst, I want channels per module or stakeholder group, so that discussions and requirements stay organised.*

**AC**
- Analysts, admins and owners create, rename and archive channels; public channels are open to all project members, private ones to listed members.
- Archived channels are read-only and hidden by default.
- The sidebar lists projects and channels with unread counts.

#### US-29 — Real-Time Messaging with Threads and Mentions
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Must | 8 | S2 | Dhavni didi (WebSocket, event bus), Pranshu (chat UI) | FR-51, FR-52, NFR-24 |

*As a member, I want to discuss requirements in real time with threads and @mentions, so that the conversation happens next to the requirements.*

**AC**
- Members post, reply in threads, @mention, and edit or delete their own chat messages; edits are marked "edited".
- Messages reach connected channel members within 1 s at p95 (NFR-24); history loads with cursor pagination.
- After a reconnect the client catches up on missed events through REST; nothing is lost.
- Content is rendered as text (no HTML injection); posting is rate-limited.

#### US-46 — Search Across the Workspace
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Should | 3 | — | — | FR-53 |

*As a Business Analyst, I want to search messages, requirements and findings, so that I can find earlier discussions and decisions.*

**AC**
- Keyword search (PostgreSQL full-text) combined with semantic search over requirements (embeddings).
- Filters by type (message, requirement, finding, issue, change request), project, channel, author and date.
- Results include only what the user may access, verified by a test with private channels.

*Deferred in v3.2 to make room for US-45 and US-55; the map search and requirements-table filters cover the MVP (`IT314_RCD_Scope_Extension_v5.md` §12).*

---

### EP-11 · Requirement Authoring and Actions

#### US-30 — Requirement Composer with EARS Templates
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Must | 5 | S3 | Bansil (backend), Pranshu (composer UI) | FR-55, FR-60, FR-81, DR-15, DR-18 |

*As a stakeholder, I want a guided form for writing a requirement — opened from the sidebar, from `/req` in a channel or from the map — so that what I write is complete and enters the project properly instead of getting lost in chat.*

**AC**
- Five EARS templates (Always, When, While, If…then, Where) with labelled slots and a live sentence preview; free text remains available (`IT314_RCD_Interface_Design_v5.md` §5).
- Fields: type, MoSCoW priority, stakeholder group (default the author's), owner (default the author), rationale, Given/When/Then acceptance criteria, tags, links.
- Drafts autosave privately; **Propose** creates a requirement in state Proposed with origin "post", author and message link, posts a requirement card to the chosen channel and triggers live analysis (US-31).
- A requirement post cannot be edited afterwards; corrections go through a change request or a new post.

#### US-31 — Live Analysis of a Posted Requirement
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Must | 8 | S3 | Heet (incremental retrieval), Keval (classification, budget), Dhavni didi (queue, events) | FR-56, FR-57, NFR-25, NFR-28 |

*As a contributor, I want my posted requirement checked against the existing baseline within a minute, so that I hear about conflicts while the discussion is still fresh.*

**AC**
- An analysis run compares the new requirement with its top-*k* neighbours in the Approved baseline and open proposals, and runs the single-requirement checks, using the US-05 engine with the project context pack (US-60).
- A result card appears in the thread within 60 s for 90% of posts (NFR-25), with each finding's category, confidence, severity, rationale, involved IDs and clarification question.
- Owners of involved requirements are @mentioned.
- When the project's LLM budget is exhausted, the card shows "waiting for budget" and the run resumes later; failures show a readable reason.
- A clean result reads "No issues detected by analysis — analysis can miss conflicts" with a **Raise a concern** link; it never says "verified" or "conflict-free" (DR-21).

#### US-36 — Owners, Stakeholder Groups and Ownership Requests
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Should | 3 | S3 | Bansil (backend), Pranshu (UI) | FR-59, DR-11 |

*As a Project Manager, I want every requirement to have an owner and a stakeholder group, so that conflicts and changes reach the right people.*

**AC**
- New posts default the owner to the author; imported requirements default to the uploader until reassigned.
- Analysts and admins reassign owners and groups; reassignment is audited.
- Any member who can propose can **request ownership**; the current owner or a PM accepts or declines.
- Owners are used for @mentions (US-31), auto conflict issues (US-52), required reviews (US-35) and notifications (US-38).

#### US-37 — Requirement Lifecycle States
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Must | 3 | S3 | Parth | FR-61, DR-13 |

*As a Product Owner, I want each requirement to move through clear states, so that everyone knows what is agreed and what is only proposed.*

**AC**
- States: Proposed, Under Review, Approved, Rejected, Implemented, Deprecated; allowed transitions and roles follow `IT314_RCD_Design_Update_v5.md` §7.1.
- Only Approved and Implemented requirements form the baseline and are the targets of analysis comparisons.
- A Proposed requirement becomes Approved only when: an analysis run has completed on its current text; no High-severity finding is open unless the decision owner records an accepted risk; the decision owner and required reviewers approved this exact text; and the text has not changed since (FR-98). Every transition is audited.

#### US-51 — Live Lint, Similar Hints, Pre-Flight Check and AI Wording
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Should | 5 | S5 | Keval (lint catalogue, dry run, AI wording), Bansil (composer wiring) | FR-82, FR-83, FR-93, NFR-34, DR-07, DR-18 |

*As a stakeholder writing a requirement, I want instant feedback on its quality and on what it might clash with before I submit it, so that I submit fewer vague or conflicting requirements.*

**AC**
- Lint runs within 300 ms of typing pausing, with no LLM call: vague terms, weak verbs, missing actor, missing measurable value, "and/or", "etc.", multiple "shall"; issues are underlined and listed with a fix hint; a quality indicator summarises them. Lint never blocks submission.
- The 3 most similar existing requirements appear within 1 s, using embeddings only.
- **Pre-flight check** runs the incremental analysis in dry-run mode: likely findings and a ghost node on a mini-map; nothing is saved; the remaining monthly budget is shown.
- **Improve wording (AI)** proposes an EARS rewrite as a diff, labelled as AI; it is applied only if the member accepts it.
- The same panel works in the change editor (US-33).

#### US-53 — Discussion, Votes, Watch and Links
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Should | 3 | S6 | Madhav | FR-80, FR-90, FR-91, DR-17, DR-19 |

*As a member, I want to comment on a requirement, support or oppose it, watch it, and link it to related requirements, so that stakeholder opinion and known relationships are visible to whoever decides.*

**AC**
- Comment thread on each requirement (separate from channel chat).
- Support / oppose with an optional reason; tallies are shown in the drawer and to reviewers of change requests; votes never change state (DR-17).
- Watch a requirement, issue or change request; watchers are notified of its activity (US-38).
- Assert *depends on*, *refines* or *related to* links; human links are drawn differently from AI-detected relationships and are used by impact analysis (US-11); the AI never removes them (DR-19).

#### US-32 — Suggest Requirements Detected in Chat (Opt-In)
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Should | 5 | — | — | FR-58, NFR-30, DR-15 |

*As a Business Analyst, I want the system to notice requirement-like statements in chat and suggest turning them into posts, so that requirements stated casually are not lost.*

**AC**
- Off by default; an admin enables it per project after seeing the data-flow disclosure (SX-04).
- Detected messages show a discreet "Promote to requirement?" action to the author and analysts only.
- Promoting opens the composer pre-filled with the message text; nothing becomes a requirement without confirmation.
- Detection precision is measured on a labelled chat sample; batching keeps it within the budget.

#### US-47 — Import Meeting Notes as Candidate Requirements
| Priority | Pts | Sprint | Trace |
|---|---|---|---|
| Could | 5 | — | FR-58 (extension), DR-15 |

*As a Business Analyst, I want to paste meeting notes and get candidate requirements, so that decisions made in meetings reach the project.* **AC:** candidates listed for confirmation, never created automatically; each links back to the notes. Deferred.

---

### EP-12 · Issues and PR-Style Change Requests

#### US-52 — Requirement Issues and Auto Conflict Issues
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Must | 5 | S4 | Dhavni didi (backend, auto-open rules), Pranshu (UI) | FR-86, FR-87, SX-18 |

*As a requirement owner, I want a GitHub-style issue opened and assigned to me and the other owner whenever our requirements clash, so that the two of us resolve it together instead of finding out late.*

**AC**
- Members can open issues (ISS-n) with title, description, labels, assignees and linked requirements; comment; close and reopen.
- When a Conflicting or Duplicate finding of Medium or High severity involves requirements owned by two or more different members, one **conflict issue** is opened automatically, assigned to all owners, with both requirements side by side, the AI rationale and the clarification question as the first comment.
- The conflict issue shows the AI-suggested solutions (US-45) with each owner's preference, and offers "Accept suggestion", "Propose change to REQ-a", "Propose change to REQ-b" and "Not a conflict…" (which opens the finding review).
- It closes automatically when its finding is resolved or dismissed, or when a change request with "Resolves ISS-n" merges; closing an issue by hand never changes the finding.
- Issues appear as badges on the map and in the requirement drawer.

#### US-33 — Open a Change Request (Change Editor)
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Must | 5 | S4 | Bansil (backend), Abhijeet (UI) | FR-62, FR-89, DR-14 |

*As a stakeholder, I want to propose a change to an agreed requirement the way a developer opens a pull request, so that the change is reviewed and decided rather than slipped in.*

**AC**
- **Propose change** in the requirement drawer opens the change editor: the composer pre-filled with the current text, a live word-level diff, kind (modify or deprecate), a required reason and optional "Resolves ISS-n".
- Opening it creates RCR-n with the requirement's **base version**, auto-requests reviewers (US-35), runs the checks (US-34) and posts a change-request card in the requirement's channel.
- Several open change requests on one requirement are allowed; when the requirement moves past an RCR's base version, that RCR is marked **needs update** with a three-way view, and the proposer can update it (checks re-run).
- Every update of the proposal creates a new **proposal revision**; approvals given to an earlier revision are dismissed and must be given again (FR-98).
- The proposer can withdraw it while undecided. Approved requirements change only this way (SX-03).

#### US-34 — Consequence Checks for a Change Request
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Must | 8 | S4 | Madhav (checks, risk), Keval (narrative), Abhijeet (Checks and Map-preview tabs) | FR-24, FR-25, FR-63, FR-64, FR-88, NFR-26, DR-16 |

*As a Project Manager, I want every change request to show its consequences as checks, like CI checks on a pull request, so that we decide knowing what it breaks and who it affects.*

**AC**
- A **findings delta** at the top of the Checks tab: findings **resolved** by the change, **new** findings it creates, findings on affected requirements that **remain open**, and checks that **must re-run** before approval. A change is never shown as safe only because it resolves its original issue (FR-99).
- Checks tab with pass / warning / fail / information items (icon **and** text): conflicts, duplicates, ambiguity lint, impact (direct and transitive with reasons, via US-11 and human links), work touched (US-48, once it ships; deferred in v3.4), protected requirement, rule-based risk level (ADR-17), and an AI summary of options citing requirement IDs, labelled as AI.
- Ready within 90 s for 90% of requests (NFR-26); nothing in the baseline changes while it is built.
- If the baseline changes before merge, checks are marked stale and re-run (FR-64).
- A Map-preview tab shows the change as a ghost overlay (uses the US-14 map; the full preview layer comes with US-50). Checks are exportable (US-16).

#### US-35 — Review and Merge
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Must | 5 | S4 | Parth (policy, merge), Abhijeet (UI) | FR-21, FR-65, FR-66, FR-88, DR-04 |

*As a Product Owner, I want changes reviewed by the right people and merged only when they agree, so that the baseline changes only by agreement — especially when the change touches someone else's requirement.*

**AC**
- Reviewers come from the project's **decision rules** (US-57): the matching rule names the **decision owner** and required reviewers; the owners of the changed requirement and of requirements in direct conflict are always required; transitively affected owners are optional. The proposer never counts as an approver (SX-13), and votes never count.
- Reviewers approve, request changes or comment, including inline comments on the diff; each decision carries a rationale.
- **Merge** (members with `rcr.merge`) is enabled only when, for the **current proposal revision**: the base version is still the requirement's current version, the checks have re-run since the last base or proposal change, the decision owner and all required reviewers approved, and no "request changes" is outstanding. The merge re-verifies all of this inside one transaction; otherwise it shows exactly which condition is missing (FR-98).
- On merge: new version, baseline revision incremented, linked issues closed, affected findings marked stale and re-analysed, the map updated, everyone involved notified, all audited. Closing without merge leaves the baseline untouched.

#### US-48 — Link Requirements to Work Items
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Should | 3 | — | — | FR-67 |

*As a Project Manager, I want to link requirements to tasks or issues with estimates, so that consequence reports show the work a change touches.*

**AC**
- Add, edit and remove links (internal reference or URL, title, optional estimate in points).
- Consequence reports and requirement detail list linked items and total recorded estimates.
- URLs are validated and shown as plain links; no remote fetching (live sync is US-21).

*Deferred in v3.4 to make room for US-61; consequence reports show linked work only once this story ships (`IT314_RCD_Scope_Extension_v5.md` §12).*

#### US-57 — Decision Rules and Decision Owners per Project
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Must | 3 | S5 | Parth (rules engine), Pranshu (settings UI) | FR-65, FR-100, DR-23 |

*As a Project Manager, I want to define who decides which kind of issue — security exceptions by the security lead, compliance constraints by compliance, deadline trade-offs by me — so that decisions are made by the right authority and never by a head count.*

**AC**
- A **Decision rules** table per project: each rule matches on finding category, label, stakeholder group, protected flag or requirement type, and names a **decision owner** (a role or a person) plus required and optional reviewers. The most specific matching rule wins; a default rule always exists (requirement owner decides, one BA reviews).
- Every finding, issue and change request shows its **decision owner** and the rule that chose them ("Decides: Meera — rule *Protected requirements*").
- Merge and finding closure require the decision owner's approval in addition to the required reviewers; votes and approval counts alone can never satisfy a rule (DR-23).
- Examples seeded for new projects: protected → Compliance Reviewer; group Security → security lead; label `deadline` → Project Manager; category Duplicate → Business Analyst.
- Rule changes are audited and apply to open items only after their next update.

#### US-45 — AI Resolution Suggestions with Human Feedback
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Must | 5 | S5 | Madhav (suggestion engine), Keval (prompts, feedback examples), Abhijeet (suggestion panel UI) | FR-68, FR-94, NFR-36, DR-04, DR-20 |

*As a requirement owner or analyst, I want the AI to propose concrete solutions for every problem it finds — and to learn from what we accept, edit or reject — so that we resolve conflicts faster while people stay in charge of every decision.*

**AC**
- Every finding gets up to three **suggested resolutions**, labelled as AI with a confidence and the trade-off each one makes:
  - **Conflicting:** compromise wordings (e.g. "30 min generally, 5 min on payment screens"), or "keep A, change B" with the reason.
  - **Duplicate:** one merged wording and which requirement to keep.
  - **Ambiguous:** a measurable rewrite (vague words replaced by numbers or criteria, using EARS).
  - **Incomplete:** the missing parts filled in, with every invented value marked `[TBD — confirm]` for a human to supply.
  - **Dependent:** the link to record and the order to implement in.
- Suggestions appear on the finding, on the analysis result card, on the conflict issue (US-52) and next to a failing check on a change request (US-34).
- **Human in the loop:** each response is recorded as one structured outcome — **Accepted as suggested**, **Accepted after editing**, **Rejected: changes the intended meaning**, **Rejected: infeasible**, **Rejected: AI missed important context**, or **Deferred: team has not decided** — plus **Regenerate** with an instruction (e.g. "keep 30 minutes for the web app").
- Accepting never changes a requirement directly: for an Approved requirement it opens a pre-filled change request (US-33) linked to the finding and issue; for one's own Proposed requirement it creates a new post that supersedes it. Nothing is applied automatically (DR-04).
- On a conflict issue involving two owners, both see the options and can mark a preferred one; the issue shows "Riya ✓ Option B · Arjun ✓ Option B" before anyone opens the change request.
- All feedback is stored (FR-94) and used **first for evaluation and prompt improvement by the team**: reviewers see it, and the distribution of outcomes per category is reported at CP2 (NFR-36). Acceptance is **not** treated as proof that a suggestion was correct; a sample of suggestions is also rated by an analyst for correctness.
- Re-using accepted suggestions as examples in later prompts is an **experiment** switched off by default; it is enabled only if the CP2 evaluation shows it improves expert-rated quality. The UI never claims the AI "learns" from clicks.

*Replaces "AI Compromise Suggestions for Conflicts" (Could, 3 pts, conflicts only).*

#### US-54 — Structural Change Requests and Counter-Proposals
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Could | 5 | — | — | FR-92 |

*As a Business Analyst, I want change requests that split or merge requirements, and reviewers who can attach an alternative wording, so that larger restructuring follows the same reviewed path.* **AC:** split and merge kinds with checks on every resulting requirement; a counter-proposal is shown next to the original and can be adopted by the proposer. Deferred (`IT314_RCD_Scope_Extension_v5.md` §12, item 5).

---

### EP-13 · Notifications and Activity

#### US-38 — Inbox and Notifications
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Must | 5 | S5 | Madhav (notification service), Abhijeet (inbox UI) | FR-69, FR-70 |

*As a member, I want to be told when something needs me, so that I don't have to watch every channel.*

**AC**
- A GitHub-style inbox grouped as Review requested · Assigned · Mentioned · Watching · Results on my requirements, plus join requests for managers.
- A notification centre with unread counts, delivered in real time, each item linking to its subject; mark one or all as read.
- Payloads contain IDs and titles only (CR-04).

#### US-42 — Requirement Activity Timeline
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Should | 3 | S6 | Dhavni didi (backend), Pranshu (UI) | FR-72, DR-06, DR-08 |

*As a Business Analyst, I want one timeline of everything that happened to a requirement, so that I can explain how it got to its current form.*

**AC**
- Chronological list of posts, analysis runs, findings, clarifications, issues, change requests, reviews, merges, votes and versions, each linking to its detail.
- Filters by event type; visible to everyone who can see the requirement.

#### US-39 — Notification Preferences and Email Digest
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Could | 3 | — | — | FR-71 |

*As a Project Manager, I want to choose what I'm notified about and get a digest by email, so that I stay informed without living in the app.*

**AC**
- Preferences per notification kind; daily or weekly digest opt-in.
- Digests are sent by a scheduled task; failures are retried and logged; emails contain IDs, titles and links only.

*Deferred in v3.1: no SMTP in the MVP (SX-21).*

---

### EP-14 · Baselines and Knowledge

#### US-40 — Baseline Snapshots and Comparison
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Should | 5 | S5 | Parth (backend), Pranshu (UI) | FR-73, DR-08 |

*As a Product Owner, I want to freeze labelled baselines and compare them, so that sign-offs are traceable and I can see what changed between them.*

**AC**
- Analysts, admins and owners freeze a snapshot with a label; it records each requirement's version.
- Comparing two snapshots lists added, changed (with diff) and deprecated requirements.
- Snapshots are immutable and audited.

#### US-61 — Generate the Updated SRS with the LLM and Review It
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Must | 5 | S6 | Bansil (generator, fidelity check), Keval (section prompts), Pranshu (review UI) | FR-106, FR-107, NFR-38, DR-25 |

*As a Business Analyst, once findings are clarified and changes merged, I want the system to write the updated SRS for me, so that the team ends with a clean, current specification instead of a list of posts and decisions.*

**AC**
- **Generate updated SRS** first shows a readiness checklist: open clarification questions, open High findings without accepted risk, open change requests and open issues on included requirements. Blocking items link to where they are fixed; a PM can override with a recorded reason, which attaches the open-items report (US-59).
- The draft follows the ISO/IEC/IEEE 29148 outline. The system inserts every Approved and Implemented requirement **verbatim** with ID, priority and owner; the LLM writes only the narrative: purpose, scope, definitions (from the glossary), product perspective, user classes, assumptions, the change summary since the previous SRS version and a decisions appendix (resolved conflicts, chosen option, decision owner).
- Each section is reviewed: **Accept**, **Edit**, or **Regenerate** with an instruction; AI text stays labelled until accepted.
- A **fidelity check** runs before publishing: every baseline requirement appears exactly once and verbatim, no Proposed or rejected text appears, and no narrative sentence contains "shall" or "must" that is not a baseline requirement (DR-25). Failures are listed and block publishing.
- Publishing (`srs.publish`) creates an immutable, numbered SRS version (v1.0, v1.1, …) linked to the baseline revision, comparable with the previous version, and downloadable as Markdown; DOCX and PDF come with US-41.
- A 300-requirement draft is ready within 5 minutes for 90% of runs, with about one LLM call per narrative section (NFR-38).

#### US-41 — Export the Updated SRS (DOCX, PDF, Markdown)
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Should | 5 | S6 | Bansil | FR-74, FR-107, DR-02, DR-03 |

*As a Business Analyst, I want to export the published updated SRS, so that the live requirements can be delivered as a formal document.*

**AC**
- Exports a published SRS version (US-61) as **DOCX, PDF or Markdown**, keeping its sections, requirement tables and AI-written narrative as accepted.
- Without a published version, or with the LLM budget used up, a template export (IEEE 830 / 29148 outline with introduction placeholders, requirements grouped by type and stakeholder group) is offered as the fallback.
- Contains **only** Approved and Implemented requirements; proposed requirements and unresolved items go into the separate open-items report (US-59, DR-22).
- Requirement IDs, priorities and owners are preserved; the export states the snapshot or baseline revision.

#### US-43 — Ask the Baseline (Q&A with Citations)
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Could | 5 | — | — | FR-75, NFR-17 |

*As a QA engineer, I want to ask questions such as "what are the session-timeout requirements?", so that I get an answer with the requirements it comes from.*

**AC**
- Answers use only retrieved baseline requirements and cite their IDs; citations outside the retrieved set make the answer invalid and retried.
- When nothing relevant is retrieved, the answer is "not found in the baseline" without an LLM call.
- Counts against the project budget and is rate-limited.

*Deferred in v3.1 (`IT314_RCD_Scope_Extension_v5.md` §12, item 8).*

#### US-59 — Open-Items Report Beside the Approved Baseline
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Should | 2 | S6 | Bansil | FR-74, FR-102, DR-22 |

*As a Product Owner, I want the approved specification and the unresolved items exported separately, so that a polished SRS never hides open disagreements or mixes in unapproved suggestions.*

**AC**
- The SRS export (US-41) contains **only** Approved and Implemented requirements of the chosen baseline, and its first page states what was excluded (counts of proposed requirements, open findings, open change requests).
- A separate **Open-items report** (PDF or Markdown) lists proposed requirements, open findings by source and severity, open issues with decision owners, rejected or closed change requests with reasons, and accepted risks.
- Both exports name the same baseline revision so they can be read together; the Baselines screen shows the excluded counts before export.

---

### EP-15 · Live Requirements Map (new in v3.1)

#### US-14 — Live Requirements Map
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Must | 8 | S3 | Dhavni didi (graph API, deltas), Abhijeet (map UI) | FR-29, FR-84, NFR-32, NFR-33 |

*As any member, I want the requirements graph — the picture we used to get only at the end of SRS analysis — to update live whenever someone adds or changes a requirement, so that everyone always sees the current state and where the conflicts are.*

**AC**
- Requirements are nodes (shape by type, border by state); conflicts, duplicates, dependencies and human links are edges styled differently by colour **and** line style; badges show open issues and change requests.
- When an analysis run completes, or a requirement is posted, merged, reviewed or linked, every member viewing the map sees the change without reloading within 2 s at p95 (NFR-32); changed elements pulse and a toast names the actor.
- The map is built from stored results; it never triggers a whole-project re-analysis (SX-16). Node positions are persisted so the layout stays stable.
- Clicking a node opens the requirement drawer; focus mode highlights 1- and 2-hop neighbours; filters by category, state, owner and group; search by ID or text.
- Every delta also produces a **one-line written description** shown in an activity feed under the map ("Arjun added REQ-031 — 1 conflict with REQ-014"); the full Changes panel and summaries come with US-55.
- Responsive with 500 nodes and 2,000 edges (NFR-33); a table view shows the same data.

*Replaces the v3 "Visualize the Dependency / Conflict Graph" (Should, 5 pts).*

#### US-50 — Map Preview Layer and Time Slider
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Should | 5 | S6 | Dhavni didi (snapshots of graph state), Pranshu (UI) | FR-85 |

*As a Project Manager, I want to see on the map what a proposed change would do, and replay how the map looked at earlier baselines, so that I can judge changes visually and explain how we got here.*

**AC**
- Layers Baseline (solid), Proposed (dashed) and Preview (ghost) can be toggled; Proposed is on by default (SX-17).
- A pre-flight draft or an open change request can be shown as a Preview: edges it removes fade, edges it adds glow.
- A time slider moves through baseline revisions and labelled snapshots; the map shows that state read-only.
- Grouping by stakeholder group, type or owner; cluster view by default above 300 nodes.

#### US-55 — Written Change Log and Summaries for the Map
| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Should | 3 | S6 | Dhavni didi (change sentences, summaries), Keval (AI narrative), Pranshu (Changes panel UI) | FR-95, FR-96 |

*As any member, I want every change on the map also explained in writing — what changed, who did it and what it affected — so that I can understand the project without reading the graph, and share the summary with people who never open the map.*

**AC**
- A **Changes panel** beside the map lists every change as a sentence built from the graph delta, newest first, e.g. *"10:42 · Arjun added REQ-031 (Security). Analysis found 1 conflict: REQ-031 ↔ REQ-014 (High). ISS-12 opened for Arjun and Riya."* Clicking a line highlights the elements on the map; hovering a node lists its changes.
- Filters by person, requirement, kind (added, changed, merged, conflict found, conflict resolved, link) and time; the time slider (US-50) and the panel stay in step.
- **"Summarise changes since…"** (a snapshot, a date or my last visit) produces a written summary: counts computed from data (requirements added, changed, deprecated; conflicts opened and resolved; change requests merged), a bullet list of the important changes, and an optional AI narrative paragraph labelled as AI.
- When a node is focused, the drawer explains each relationship in a sentence ("REQ-014 conflicts with REQ-031: different inactivity limits for the same session; confidence 0.86").
- The summary can be copied as Markdown or exported with the reports (US-16).
