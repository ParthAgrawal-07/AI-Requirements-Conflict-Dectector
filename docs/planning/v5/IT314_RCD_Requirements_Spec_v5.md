# Requirements Specification

**Functional, Non-Functional & Domain Requirements — AI Requirements Conflict Detector (collaborative workspace scope)**

| | |
|---|---|
| **Source** | IT314 Lab Assignment 6 baseline, amended by the Step 6 conflict review and widened by the Step 7 scope extension |
| **Numbering** | FR-01–FR-107 · NFR-01–NFR-39 · DR-01–DR-25 (canonical; see §0) |
| **Tags** | `CR-xx` / `SC-x` / `G-x` = Step 6 (`conflict-resolution.md`) · `SX-xx` = Step 7 (`IT314_RCD_Scope_Extension_v5.md`, revision 2) |
| **Screens** | `IT314_RCD_Interface_Design_v5.md` shows the interface for these requirements |
| **Scope** | §7 classifies every requirement as MVP, reduced-target MVP or post-MVP |

---

## 0. Numbering

- **This document's numbering is canonical** (CR-21). The backlog, epics and sprint plan trace to it.
- Step 6 added **FR-42** (severity) and merged FR-35 into FR-36.
- Step 7 adds **FR-43–FR-76**, **NFR-24–NFR-31** and **DR-13–DR-16**, and amends 14 existing rows (tagged `SX-xx`); a few others gained small wording extensions to cover posts and channels. Numbers are never reused: a retired requirement keeps its number with a note.
- Step 7 revision 2 adds **FR-77–FR-93**, **NFR-32–NFR-35** and **DR-17–DR-19**, and amends FR-29, FR-37, FR-44, FR-48, FR-62–FR-66 and FR-69 (tags SX-14 to SX-21).
- Step 7 revision 3 adds **FR-94–FR-96**, **NFR-36** and **DR-20**, and widens FR-68 to AI resolution suggestions for every finding with human feedback (tags SX-22, SX-23).
- Step 7 revision 4 (trust review) adds **FR-97–FR-102**, **NFR-37** and **DR-21–DR-23**, and amends FR-65, FR-74, FR-94 and NFR-36 (tags SX-24 to SX-30). Rows are placed next to the requirements they refine, so numbers are not in strict order.
- Step 7 revision 5 adds **FR-103–FR-107** (compulsory project context; LLM-generated updated SRS with review and export), **NFR-38–NFR-39** and **DR-24–DR-25**, amends FR-47 and FR-74, and moves FR-67 (work-item links) to post-MVP to make room (tags SX-31 to SX-33).

### Glossary (Step 7)

| Term | Meaning |
|---|---|
| **Workspace** | A team: members, roles, join codes |
| **Join code** | A random code (or link) that lets a person create an account and join a workspace or project with a preset role (FR-44) |
| **Permission / role** | A permission is one allowed action (e.g. `rcr.merge`); a role is a named set of permissions. Authorisation checks permissions, never role names (ADR-20) |
| **Analyst, contributor** | Shorthand used in this document: *analyst* = the Business Analyst role; *contributor* = any role with `req.propose` that is not an analyst (by default Developer, QA Engineer, Stakeholder) |
| **Requirement issue (ISS-n)** | A GitHub-style issue about one or more requirements; may be opened automatically for a conflict between different owners |
| **Requirement change request (RCR-n)** | A pull-request-style proposal to change an Approved requirement, with base version, diff, checks, reviews and merge |
| **Live map** | The requirements graph that updates for all viewers whenever the data changes (FR-84) |
| **EARS** | Easy Approach to Requirements Syntax: five sentence templates (ubiquitous, event-driven, state-driven, unwanted behaviour, optional feature) |
| **Project** | One product's requirements inside a workspace: baseline, documents, channels, thresholds (SX-01) |
| **Channel** | A discussion space inside a project; public or private |
| **Requirement post** | A structured message that creates a requirement in state *Proposed* |
| **Baseline** | The set of *Approved* requirements of a project at a given revision; a **baseline snapshot** is a labelled, frozen copy |
| **Change request** | Same as RCR: a proposal to modify or deprecate an Approved requirement |
| **Consequence report / checks** | The read-only analysis of a proposal, shown as checks on the change request: conflicts, affected requirements, owners, work items, risk, and options |
| **Analysis run** | One execution of the detection pipeline, scoped to a document, a requirement or a change request |
| **Finding source** | Where a finding came from: **AI** (similarity filter + LLM), **Rule** (deterministic cross-check, FR-101) or **Person** (raised concern, FR-97). All share one workflow |
| **Decision owner** | The role or person who decides a finding or change under the project's decision rules (FR-100) |
| **Project context / brief** | What the product is, its scope, actors, environment and terms; compulsory before a project is analysed (FR-103) |
| **Context pack** | The bounded extract of the project context sent with every LLM call (FR-105) |
| **Updated SRS** | A specification document generated from the clarified baseline: requirement text inserted verbatim by the system, narrative written by the LLM, reviewed section by section and published as a numbered version (FR-106, FR-107) |
| **Proposal revision** | One version of a change request's proposed text; approvals apply to one revision only (FR-98) |

---

## 1. Functional Requirements (FR)

### 1.1 Document Ingestion — FR-01–FR-06

| ID | Requirement | Source Stakeholder(s) |
|---|---|---|
| FR-01 | The system shall allow an authorized user to upload an SRS document in PDF or Word (DOCX) format into a project, choosing **import as baseline** (requirements become Approved; analyst, admin or owner only) or **import as proposals** (requirements become Proposed). *(Amended — SX-08)* | Architects; IT/DevOps |
| FR-02 | The system shall validate that an uploaded document is a supported, uncorrupted file and reject/notify the user otherwise. | Architects |
| FR-03 | The system shall extract raw text from the uploaded document and segment it into individual, distinct requirement statements, following the document's own requirement boundaries (numbered lists, REQ-IDs) and never rewriting wording. *(Clarified — CR-06)* | Business Analysts; Architects |
| FR-04 | The system shall preserve original requirement identifiers and wording from the source document rather than regenerating its own numbering scheme. An item with no printed ID is stored without one; a provisional marker is never shown as if it were a source ID. *(Clarified — CR-06)* | Business Analysts |
| FR-05 | The system shall associate every requirement with its origin (document, requirement post or change request), its author or uploader, and its stakeholder group: for posts, the author's group; for uploads, an optional group supplied by the uploader. *(Amended — G-1 resolved by SX; see FR-60)* | Business Analysts; Product Owner |
| FR-06 | The system shall allow a user to correct extraction errors (split, merge or exclude a segment, fix an ID) while requirements are Proposed or before an imported baseline is first used. Corrections are recorded as new versions authored by the user (FR-26). Once a requirement is Approved, any change goes through a change request (FR-62). *(Amended — CR-06, SX-03)* | Business Analysts |

### 1.2 Embedding & Similarity Pre-Filter — FR-07–FR-10

| ID | Requirement | Source Stakeholder(s) |
|---|---|---|
| FR-07 | The system shall generate a vector embedding for each extracted requirement statement. | Architects / Senior Developers |
| FR-08 | The system shall store requirement embeddings in a vector-searchable data store (e.g., pgvector). | Architects / Senior Developers |
| FR-09 | The system shall compute pairwise similarity between requirements and generate a filtered candidate set of pairs above a configurable similarity threshold, so that not every pair requires LLM classification. This applies to the pair-based categories (Conflicting, Duplicate, Dependent); Ambiguous and Incomplete are assessed per requirement (see FR-11). *(Amended — CR-02)* | Architects; Business Analysts |
| FR-10 | The system shall allow the similarity threshold to be tuned per project via configuration, without requiring a code change. | Architects / Senior Developers |

### 1.3 AI Classification — FR-11–FR-17

| ID | Requirement | Source Stakeholder(s) |
|---|---|---|
| FR-11 | The system shall classify findings into one of five categories: **pair-based** — Conflicting, Duplicate, Dependent — for each candidate requirement pair; and **single-requirement** — Ambiguous, Incomplete — for each requirement assessed on its own. *(Amended — CR-01, CR-02)* | Business Analysts; Architects |
| FR-12 | The system shall distinguish true duplicates from merely similar requirements: the configurable similarity threshold only decides which pairs become *candidates* (DR-10); whether a pair is a duplicate is decided by LLM judgment against the duplicate criteria. *(Clarified — CR-05)* | Business Analysts |
| FR-13 | The system shall return a confidence/trust score alongside each classification result so users can judge reliability before acting on it. | Business Analysts |
| FR-14 | The system shall attach supporting context to every flagged issue: related requirement ID(s), source document section or originating post, and a natural-language rationale for the flag. | QA Engineers; Business Analysts |
| FR-15 | The system shall validate and structure classification output (schema-valid) before it is persisted or displayed. | Architects / Senior Developers |
| FR-16 | The system shall allow authorized users to define and adjust the criteria that qualify a requirement as "ambiguous" by editing the recognised-pattern catalogue (DR-07); an added pattern needs a name and description, and LLM judgment supplements the patterns but never replaces them. *(Clarified — SC-3)* | Architects / Senior Developers |
| FR-17 | The system shall allow authorized users to define and adjust the criteria that qualify two requirements as "dependent" on one another. | Architects / Senior Developers |

### 1.4 Human Review & Feedback — FR-18–FR-21

| ID | Requirement | Source Stakeholder(s) |
|---|---|---|
| FR-18 | The system shall allow authorized users to confirm, dismiss (as a false positive), merge, or reclassify a flagged issue. | Senior Developers; Business Analysts |
| FR-19 | The system shall persist all classification results — including dismissed ones — for audit and traceability, subject to the retention and erasure rules in NFR-14. *(Amended — CR-04)* | Legal / Compliance Team |
| FR-20 | The system shall retain the original AI-generated finding when a human corrects or reclassifies it, rather than overwriting it. | Business Analysts; QA Engineers |
| FR-21 | The system shall allow compliance-critical requirements to be marked "protected." Protected requirements are still analysed and flagged, but a finding or change request that involves one is never auto-resolved, merged, dismissed, approved or removed without explicit sign-off by a compliance reviewer. *(Amended — CR-03; extended to change requests — SX-13)* | Legal / Compliance Team |

### 1.5 Clarification Workflow — FR-22–FR-23

| ID | Requirement | Source Stakeholder(s) |
|---|---|---|
| FR-22 | For every requirement flagged as Ambiguous, Incomplete or Conflicting, the system shall generate a clarification question sufficient for a QA engineer to resolve the issue without further discussion. Duplicate and Dependent findings are resolved by a merge or link decision and need no question. *(Amended — CR-01)* | QA Engineers |
| FR-23 | The system shall allow a user to mark a clarification question as answered and attach the resolution text. | QA Engineers; Business Analysts |

### 1.6 Change & Impact Analysis — FR-24–FR-26

| ID | Requirement | Source Stakeholder(s) |
|---|---|---|
| FR-24 | Whenever a change to a requirement is proposed, the system shall perform a change-impact analysis identifying all affected requirements, distinguishing direct from transitive impact. The result feeds the consequence report (FR-63). Design elements and test cases are out of scope (post-MVP, with FR-39); linked work items are covered by FR-67. *(Amended — CR-09, SX-03)* | Project Managers |
| FR-25 | The system shall present the list of potentially impacted requirements before a proposed change is decided, as part of the consequence report. *(Amended — SX-03)* | Project Managers; Architects |
| FR-26 | The system shall maintain a version history for every requirement, including prior text, the change request that produced each version, and resolution status, to support change comparison and audit. *(Amended — SX-03)* | Architects; Legal / Compliance |

### 1.7 Dashboard, Visualization & Reporting — FR-27–FR-32

| ID | Requirement | Source Stakeholder(s) |
|---|---|---|
| FR-27 | The system shall display a summary dashboard per project, and a roll-up per workspace, showing counts of flagged issues by type (Conflicting / Duplicate / Ambiguous / Incomplete / Dependent), by severity (FR-42) and by status, plus requirements by lifecycle state and open change requests. *(Amended — CR-01, CR-15, SX)* | Project Managers; Business Analysts |
| FR-28 | The system shall allow drill-down navigation from a summary count to the underlying list of flagged requirements. | Business Analysts |
| FR-29 | The system shall render a visual relationship graph of requirements, with requirements as nodes and detected relationships as connections. In the extended scope this graph is the **live requirements map** (FR-84, FR-85). *(Amended — SX-16)* | Architects; Project Managers |
| FR-30 | The system shall allow users to generate and export flagged-issue, impact and consequence reports as PDF or CSV on demand. Scheduled email delivery is covered by FR-71; webhook and PM-tool delivery remain post-MVP and must retry and log failures. *(Amended — CR-10, SX-05)* | Project Managers |
| FR-31 | The usability of the flagged output and the workspace flows shall be validated with sample users through low-fidelity previews before further implementation effort is committed. This is a validation activity, not a product mode. *(Amended — CR-13)* | QA Engineers |
| FR-32 | The system shall generate an aggregated, executive-level summary report for periodic distribution to sponsors, using metrics computed from recorded system data. Time-saved and cost figures appear only as labelled, user-supplied estimates. Post-MVP. *(Amended — CR-11)* | Executive Sponsor / Budget Holder |

### 1.8 Configuration & Scope Control — FR-33–FR-34

| ID | Requirement | Source Stakeholder(s) |
|---|---|---|
| FR-33 | The system shall allow the Client/Product Owner to configure the success metrics/KPIs to be tracked. *Post-MVP; no story (gap G-3).* | Client / Product Owner |
| FR-34 | The system shall support configuration of an explicit "out of scope" list of requirement types or SRS sections excluded from automated analysis. *Post-MVP; no story (gap G-3).* | Client / Product Owner |

### 1.9 Escalation & Audit Trail — FR-35–FR-36

| ID | Requirement | Source Stakeholder(s) |
|---|---|---|
| FR-35 | *Merged into FR-36 (CR-14).* | — |
| FR-36 | The system shall maintain a complete, exportable audit trail of all automated flags, manual overrides, sign-offs, escalations, membership changes, change-request decisions and baseline snapshots. Audit entries hold identifiers, actions and timestamps, not requirement or message text (see NFR-14). *(Amended — CR-04, CR-14, SX)* | Legal / Compliance; Executive Sponsor; Business Analysts |

### 1.10 Authentication & External Integration — FR-37–FR-41

| ID | Requirement | Source Stakeholder(s) |
|---|---|---|
| FR-37 | The system shall require user authentication before granting access to any workspace, project, channel, document or dashboard, over REST and WebSocket alike. MVP: JWT-based; SSO/LDAP is post-MVP (ADR-07). An account can be created **only with a valid join code or invite link** (FR-44); the CLI is used only to create the first platform administrator. *(Amended — SX-02)* | IT/DevOps / System Admins |
| FR-38 | The system shall associate every workspace resource with its workspace and project, and restrict access to active members of that workspace according to their role (FR-48). *(Amended — SX-01, SX-06)* | IT / DevOps |
| FR-39 | The system shall provide read/write integration with common engineering tools (e.g., Jira, Confluence, GitHub). *Post-MVP.* | IT/DevOps / System Admins |
| FR-40 | The system shall expose a documented, versioned REST API (JSON) for third-party developers, with configurable per-consumer rate limits. *Post-MVP.* | Third-Party API Consumers |
| FR-41 | The system shall provide a mechanism to intake survey or customer-feedback data on how unclear requirements affected end customers. *Post-MVP.* | End Customers (Indirect) |

### 1.11 Triage — FR-42

| ID | Requirement | Source Stakeholder(s) |
|---|---|---|
| FR-42 | The system shall assign each flagged issue a severity level — Low, Medium or High — that is proposed by the system, distinct from the confidence score ("how bad" versus "how sure"), and can be overridden by a reviewer with the override recorded. *(New — CR-15)* | Business Analysts; Product Owner |

### 1.12 Workspace & Membership — FR-43–FR-49 *(New — Step 7)*

| ID | Requirement | Source Stakeholder(s) |
|---|---|---|
| FR-43 | An authenticated user with the right to create workspaces (platform admin, or any user if the deployment allows it) shall be able to create a workspace; the creator becomes its owner. | Workspace Owner / Project Manager |
| FR-44 | An owner, admin or project manager shall be able to generate a **join code** and matching **invite link** for the workspace or for one project, choosing the default role, an expiry (1, 7 or 30 days; default 7), a maximum number of uses and whether joining needs approval. A person signs up or signs in and enters the code to join. Codes can be listed, revoked and regenerated; a code can never grant Owner or Admin. Email delivery of the link is optional and post-MVP. *(Amended — SX-02, SX-14, SX-21)* | Workspace Owner; Project Manager; IT/DevOps |
| FR-45 | An owner or admin shall be able to change a member's role or remove a member. Removal revokes access immediately, including open real-time connections; the member's content stays attributed to them as a former member, and their open change requests, approvals and owned requirements are listed for reassignment. *(SX-11)* | Workspace Owner; Legal / Compliance |
| FR-46 | A user shall be able to belong to several workspaces, with a separate role in each, and switch between them. *(SX-06)* | All members |
| FR-47 | A workspace shall contain projects. Each project has its own baseline, documents, channels, analysis thresholds, LLM budget and approval settings, and its own **project context** (FR-103); a project is in *Setup* until that context is confirmed, then *Active*. *(SX-01; amended rev. 5, SX-31)* | Product Owner; Architects |
| FR-48 | Access shall be decided by **permissions**. The system shall provide nine default roles — Owner, Admin, Project Manager, Business Analyst, Developer, QA Engineer, Stakeholder, Compliance Reviewer, Viewer — with the permissions in §1.22, and allow custom roles (FR-78). *(Amended — SX-15)* | IT/DevOps; Legal / Compliance |
| FR-49 | A member shall be able to leave a workspace. The last active owner can leave only after transferring ownership. | Workspace Owner |

### 1.13 Channels & Messaging — FR-50–FR-54 *(New — Step 7)*

| ID | Requirement | Source Stakeholder(s) |
|---|---|---|
| FR-50 | Analysts, admins and owners shall be able to create, rename and archive channels in a project; channels are public (all project members) or private (listed members). Archived channels are read-only. | Project Managers; Business Analysts |
| FR-51 | Members with posting rights shall be able to post messages, reply in threads, @mention members and edit or delete their own chat messages. Requirement posts cannot be edited after submission (DR-14). | All members |
| FR-52 | New messages, analysis results and status changes shall be delivered to connected members of the channel in real time; history is available with cursor pagination, and a client that reconnects can catch up on missed events. | All members |
| FR-53 | Members shall be able to search messages, requirements and findings across the projects they can access, with results limited to their permissions. *Post-MVP (deferred in rev. 3).* | Business Analysts; QA Engineers |
| FR-54 | Uploading an SRS from within a channel shall create a document in that project through the same pipeline as FR-01, with the progress shown in the channel. | Business Analysts |

### 1.14 Live Requirement Intake — FR-55–FR-61 *(New — Step 7)*

| ID | Requirement | Source Stakeholder(s) |
|---|---|---|
| FR-55 | A member with `req.propose` shall be able to post a structured requirement, from the composer (FR-81) or a channel: statement (required), type (functional, non-functional, constraint), priority (MoSCoW), stakeholder group, rationale, and optional acceptance criteria. It creates a requirement in state Proposed. | Stakeholder Contributors; Business Analysts |
| FR-56 | Every new or changed requirement shall be analysed **incrementally** against the project's Approved baseline and its open proposals, using the same pre-filter, classification and single-requirement checks as document analysis (FR-07–FR-17), without re-analysing the whole project. *(ADR-16)* | Business Analysts; Architects |
| FR-101 | In addition to similarity-filtered AI classification, the system shall run **rule-based cross-checks** on structured attributes extracted from requirements (entity, metric, numeric value and unit, comparison, actor, condition, negation, modality) across all requirements that share an entity or metric, **regardless of embedding similarity**: conflicting numeric limits, "shall" versus "shall not", the same action assigned to different actors, overlapping conditions with different responses. Their findings carry source **Rule** and the rule that fired, and are never dropped because the LLM disagrees. *(New — rev. 4, SX-28)* | Business Analysts; Architects |
| FR-57 | The analysis result shall be posted in the requirement's thread as a result card listing each finding with category, confidence, severity, rationale, involved requirement IDs and any clarification question; if analysis fails or waits for budget, the card says so. | Stakeholder Contributors |
| FR-58 | When enabled for a project, the system may detect requirement-like statements in ordinary chat messages and suggest promoting them to requirement posts. Nothing becomes a requirement without confirmation by the message author or an analyst. Disabled by default. *(SX-04, ADR-19)* | Business Analysts; Legal / Compliance |
| FR-59 | Every requirement shall have an owner (a member) and a stakeholder group; analysts and admins can reassign them. | Project Managers; Business Analysts |
| FR-60 | The system shall record each requirement's origin (document, post or change request), the originating message or document, and its author. *(Resolves G-1)* | Business Analysts; Legal / Compliance |
| FR-61 | Requirements shall follow the lifecycle Proposed → Under Review → Approved / Rejected, then Approved → Implemented → Deprecated, with transitions limited by role. Only Approved and Implemented requirements form the baseline (DR-13). | Product Owner; Business Analysts |

### 1.15 Change Requests & Consequence Analysis — FR-62–FR-68 *(New — Step 7)*

| ID | Requirement | Source Stakeholder(s) |
|---|---|---|
| FR-62 | A member with `rcr.open` shall be able to open a change request against an Approved requirement, proposing new text or deprecation, with a reason, optionally linking issues it resolves. The change request records the requirement's **base version**. *(SX-03, SX-20)* | Stakeholder Contributors; Project Managers |
| FR-63 | Before any decision, the system shall produce a **consequence report** for the proposal containing: (a) new or resolved conflicts, duplicates, dependencies and ambiguity; (b) directly and transitively affected requirements, each with the reason for the link; (c) the owners and stakeholder groups of those requirements; (d) linked work items and their recorded estimates; (e) severities and an overall risk level computed by documented rules; (f) an AI-generated summary of trade-offs and resolution options, citing requirement IDs and labelled as AI-generated. Nothing in the baseline changes while the report is built. *(SX-12, ADR-17)* | Project Managers; Architects |
| FR-99 | Every consequence report shall begin with a **findings delta** computed by re-evaluating the changed requirement and its directly related requirements: findings **resolved** by the change, **new** findings it creates, findings on affected requirements that **remain open**, and checks that **must re-run** before approval. A change shall never be presented as safe merely because it resolves the issue that prompted it. No full-project analysis is required. *(New — rev. 4, SX-26)* | Project Managers; Architects |
| FR-64 | If the baseline changes after a consequence report was produced, the report shall be marked stale and regenerated before a decision is allowed. If the changed requirement itself has moved past the base version, the change request is **needs update** (FR-89). *(Amended — SX-20)* | Project Managers |
| FR-65 | The system shall determine reviewers from the project's **decision rules** (FR-100): the matching rule names the **decision owner** and the required and optional reviewers; the owner of the changed requirement and owners of requirements in **direct conflict** are always required; owners of transitively affected requirements are optional; a compliance reviewer is required when a protected requirement is involved. Required reviewers are requested automatically. The proposer can never approve their own change request, and votes or approval counts alone never satisfy a rule. *(Amended — SX-13, SX-19, SX-27)* | Product Owner; Legal / Compliance |
| FR-66 | Reviewers shall be able to approve, request changes or comment, with a rationale. A member with `rcr.merge` shall be able to **merge** only when the policy is satisfied, no reviewer's "request changes" is outstanding and the checks are current. Merging creates a new requirement version, increments the baseline revision, closes linked issues, marks findings that involve the requirement as stale and re-analyses them. A closed (rejected) request leaves the baseline untouched and is kept for audit. *(Amended — SX-19)* | Project Managers; Business Analysts |
| FR-98 | **Agreement rules.** A requirement or change becomes agreed only when, for the exact text being decided: (1) an analysis run has completed on that text and its checks are current; (2) for a change request, its base version is still the requirement's current version; (3) the decision owner and all required reviewers have approved **this proposal revision** — any edit to the proposal creates a new revision and dismisses earlier approvals; (4) no High-severity finding on it is open unless the decision owner recorded an accepted risk with a reason; (5) no reviewer's "request changes" is outstanding. Merge re-verifies (1)–(5) inside one transaction. The same rules govern Proposed → Approved, Approved → new version, and Approved → Deprecated. *(New — rev. 4, SX-25)* | Product Owner; Legal / Compliance |
| FR-100 | Each project shall have **decision rules** that map a finding category, label, stakeholder group, requirement type or the protected flag to a **decision owner** (a role or a named person) and required and optional reviewers; the most specific matching rule applies, and a default rule always exists. Every finding, issue and change request shows its decision owner and the rule that chose them. Rule changes are audited. *(New — rev. 4, SX-27)* | Project Managers; Legal / Compliance |
| FR-67 | Users shall be able to link a requirement to work items (an internal reference or an external URL) with an optional title and estimate in points, so consequences can name the work touched. *Post-MVP (deferred in rev. 5 with US-48, SX-33).* | Project Managers |
| FR-68 | For **every finding** the system shall propose up to three **resolution suggestions** suited to its category — compromise wordings or keep-one options for Conflicting; a merged wording for Duplicate; a measurable rewrite for Ambiguous; the missing parts, with invented values marked `[TBD — confirm]`, for Incomplete; the link and implementation order for Dependent — each with its trade-off and confidence, labelled as AI. Suggestions are shown on the finding, the result card, the conflict issue and next to failing change-request checks. A member can accept, edit then accept, reject with a reason, rate, or regenerate with an instruction. Accepting never changes a requirement directly: it opens a pre-filled change request (or a superseding post for the member's own Proposed requirement). *(Amended — rev. 3, SX-22)* | Business Analysts; requirement owners |

### 1.16 Notifications & Activity — FR-69–FR-72 *(New — Step 7)*

| ID | Requirement | Source Stakeholder(s) |
|---|---|---|
| FR-69 | The system shall notify members of: @mentions; analysis results that involve requirements they own; consequence reports that name them as affected owners; review requests; issue assignments; decisions and merges on their change requests; join requests awaiting their approval; and activity on anything they watch (FR-90). *(Amended)* | All members |
| FR-70 | The system shall provide a notification centre with unread counts, delivered in real time, from which each notification links to its subject. | All members |
| FR-71 | Members shall be able to set notification preferences per kind, and opt in to a daily or weekly email digest. Emails contain IDs, titles and links, not requirement text. *Post-MVP (SX-05, SX-21).* | Project Managers |
| FR-72 | Each requirement shall have an activity timeline showing, in order, its posts, analysis runs, findings, clarifications, change requests, decisions and versions. | Business Analysts; Legal / Compliance |

### 1.17 Baselines, Knowledge & Analytics — FR-73–FR-76 *(New — Step 7)*

| ID | Requirement | Source Stakeholder(s) |
|---|---|---|
| FR-73 | Analysts and admins shall be able to freeze a labelled baseline snapshot (e.g., "v1.0 sign-off") and compare two snapshots, showing added, changed and deprecated requirements. | Product Owner; Legal / Compliance |
| FR-74 | The system shall export a baseline snapshot, or the current baseline, as an SRS document (DOCX or PDF) with an IEEE 830 / 29148-style structure, preserving requirement IDs and grouping by type and stakeholder group. The export shall contain **only** Approved and Implemented requirements and state on its first page what was excluded; everything unresolved goes into the open-items report (FR-102). In revision 5 this template export is the fallback when no published updated SRS (FR-107) exists or the LLM budget is used up. *(Amended — rev. 4, SX-29; rev. 5, SX-32)* | Business Analysts; Client / Product Owner |
| FR-102 | Alongside any baseline export, the system shall produce an **open-items report** for the same baseline revision: proposed requirements, open findings by source and severity, open issues with their decision owners, closed or rejected change requests with reasons, and accepted risks. The Baselines screen shows the excluded counts before export. *(New — rev. 4, SX-29)* | Product Owner; Project Managers |
| FR-75 | Members shall be able to ask natural-language questions about a project's baseline; answers use only retrieved requirements, cite their IDs, and state "not found in the baseline" when nothing relevant is retrieved. *Post-MVP (deferred in revision 2).* | Business Analysts; QA Engineers |
| FR-76 | The system shall show project analytics computed from recorded data: requirement volatility (changes per requirement over time), conflict hotspots, a stakeholder-group contention matrix (which groups' requirements conflict most), and time from proposal to decision. | Project Managers; Product Owner |

### 1.18 Joining and Roles — FR-77–FR-79 *(New — Step 7 revision 2)*

| ID | Requirement | Source Stakeholder(s) |
|---|---|---|
| FR-77 | When a join code requires approval, entering it shall create a **join request** that members with `members.manage` can approve (optionally changing the role) or deny; the requester is told the outcome. Pending requests expire after 14 days. *(SX-14)* | Project Managers; IT/DevOps |
| FR-78 | Members with `roles.manage` shall be able to create, edit and delete **custom roles** as named sets of permissions from the permission catalogue (§1.22). Default roles cannot be edited or deleted; a role in use cannot be deleted until its members are reassigned. *(SX-15)* | Workspace Owner; Project Managers |
| FR-79 | A project manager shall be able to choose which workspace members belong to a project and give a member a **project-level role** that overrides their workspace role inside that project (never above the PM's own permissions). *(SX-15)* | Project Managers |

### 1.19 Requirement Authoring and Actions — FR-80–FR-83, FR-90, FR-91, FR-93 *(New — Step 7 revision 2)*

| ID | Requirement | Source Stakeholder(s) |
|---|---|---|
| FR-80 | For every requirement, the system shall offer each member exactly the actions their permissions allow: propose, save draft, comment, support or oppose, watch, link, open an issue, open a change request, review, merge, request ownership, review findings, mark implemented, protect, view on map, view timeline (summary in `IT314_RCD_Scope_Extension_v5.md` §3.1). Actions without permission are not shown. | All stakeholders |
| FR-81 | The requirement composer shall offer the five **EARS templates** (ubiquitous, event-driven, state-driven, unwanted behaviour, optional feature) with named slots, a live sentence preview and a free-text option, plus the fields of FR-55 and Given/When/Then acceptance criteria. Drafts are autosaved privately. | Business Analysts; Stakeholder Contributors |
| FR-82 | While a requirement is being written, the system shall show a **live quality lint** using the recognised-pattern catalogue (DR-07) — vague terms, weak verbs, missing actor, missing measurable value, "and/or", multiple "shall" — and a quality indicator, without calling an LLM. Lint results are advisory and never block submission (DR-18). | QA Engineers; Business Analysts |
| FR-83 | While a requirement is being written, the system shall show the most similar existing requirements (embedding similarity only), and on request run a **pre-flight check**: the incremental analysis of FR-56 in dry-run mode, showing likely findings and a preview on the map, saving nothing. Pre-flight counts against the project's LLM budget. | Business Analysts; Stakeholder Contributors |
| FR-90 | Members shall be able to **support or oppose** a requirement or change request with an optional reason, and **watch** a requirement, issue or change request to be notified of its activity. Vote tallies are shown to reviewers and never decide anything (DR-17). | All members |
| FR-91 | Members with `req.link` shall be able to assert links between requirements — *depends on*, *refines*, *related to* — which are used by impact analysis and shown separately from AI-detected relationships (DR-19). | Architects; Business Analysts |
| FR-93 | In the composer and the change editor, the system may suggest a clearer EARS rewrite of the statement, shown as a diff and labelled as AI; it is applied only if the member accepts it. | Stakeholder Contributors |
| FR-94 | The system shall record every response to an AI suggestion as one structured outcome — **accepted as suggested**, **accepted after editing** (with the final text), **rejected: changes the intended meaning**, **rejected: infeasible**, **rejected: AI missed important context**, **deferred: not yet decided** — plus regenerations with their instruction, together with the suggestion, prompt version and model. This feedback shall be used **first for evaluation and prompt improvement by the team** and shown to reviewers of the related change request. Acceptance shall not be treated as proof of correctness. Re-using accepted suggestions as prompt examples is an experiment, off by default, enabled only if evaluation shows it improves expert-rated quality, and only within the same project (SX-23, SX-30). The product shall not claim that the AI learns or trains itself. *(Amended — rev. 4)* | Business Analysts; Architects; Product Owner |

### 1.20 Live Requirements Map — FR-84, FR-85, FR-95, FR-96 *(New — Step 7 revisions 2 and 3)*

| ID | Requirement | Source Stakeholder(s) |
|---|---|---|
| FR-84 | Each project shall have a **live requirements map**: requirements as nodes (shape by type, border by state) and relationships as edges (conflict, duplicate, dependency, human link), with badges for open issues and change requests. Whenever a requirement is added, changed, merged, reviewed or linked, or an analysis run completes, the change shall reach every member viewing the map without a page reload; changed elements are highlighted and the actor is named. The map is built from stored results and never triggers re-analysis of the whole project. *(SX-16)* | All stakeholders |
| FR-85 | The map shall support layers — Baseline, Proposed and Preview (a pre-flight draft or an open change request shown as ghost elements) — grouping by stakeholder group, type or owner, a focus mode around a selected node, filters, search, a **time slider** showing the baseline at any revision or snapshot, and an equivalent table view. *(SX-17)* | Product Owner; Project Managers |
| FR-95 | Beside the map, the system shall show a **written change log**: one sentence per change, generated from the graph delta, naming the time, the actor, what changed and its effect (e.g. findings created or resolved, issues opened, change requests merged). Entries are filterable by person, requirement, kind and time, highlight the matching map elements when selected, and follow the time slider. *(New — rev. 3)* | All stakeholders |
| FR-96 | On request, the system shall produce a **written summary of changes** since a chosen snapshot, date or the member's last visit: counts computed from data, a list of the significant changes, and an optional AI narrative labelled as AI; it shall also explain each relationship of a focused node in a sentence. Summaries can be copied as Markdown or exported. *(New — rev. 3)* | Project Managers; Product Owner |

### 1.21 Issues and PR-Style Change Requests — FR-86–FR-89, FR-92 *(New — Step 7 revision 2)*

| ID | Requirement | Source Stakeholder(s) |
|---|---|---|
| FR-86 | Members with `issue.open` shall be able to open a **requirement issue** with title, description, labels, assignees and one or more linked requirements; comment on it; and close or reopen it (`issue.manage`, or the author). Issues are numbered per project (ISS-n). | All stakeholders |
| FR-87 | When a Conflicting or Duplicate finding of Medium or High severity involves requirements owned by **two or more different members**, the system shall open one **conflict issue** assigned to all those owners, showing both requirements side by side, the AI rationale and the clarification question as the first comment. It closes automatically when the finding is resolved or dismissed, or when a linked change request merges. *(SX-18)* | Project Managers; Business Analysts |
| FR-97 | Any member with `issue.open` shall be able to **raise a concern**: a finding with source **Person**, a category (one of the five or Other), the involved requirements, an explanation and an optional external reference. Human-raised findings follow the same workflow as AI findings (severity, clarification, optional AI suggestions, review, change requests, decision owner) and can be closed only by the decision owner with a reason; an AI result of "no conflict" is shown as information and is never a reason to close. The source of every finding — **AI**, **Rule** or **Person** — is always shown and filterable. *(New — rev. 4, SX-24)* | All stakeholders; Legal / Compliance |
| FR-88 | A change request shall be presented like a pull request: Conversation, a word-level **Diff** of every changed field with inline review comments, **Checks** (the consequence report of FR-63, each item marked pass, warning, fail or information), a **Map preview**, the reviewers with their state, the approval progress, linked issues, labels and votes. | Project Managers; Architects |
| FR-89 | If the requirement's current version differs from a change request's base version, the change request shall be marked **needs update**, shown with a three-way view (base, current, proposed), and cannot be merged until the proposer updates it and the checks re-run. *(SX-20)* | Project Managers |
| FR-92 | Change requests may also split one requirement into several, merge several into one, or carry a reviewer's **counter-proposal** as an alternative text. *Post-MVP (US-54).* | Business Analysts |

### 1.22 Permission Catalogue and Default Roles (FR-48, FR-78)

Roles: **Own**er · **Adm**in · **PM** Project Manager · **BA** Business Analyst · **Dev**eloper · **QA** Engineer · **Stk** Stakeholder (client or domain expert) · **Comp**liance Reviewer · **View**er.

| Permission | What it allows | Own | Adm | PM | BA | Dev | QA | Stk | Comp | View |
|---|---|---|---|---|---|---|---|---|---|---|
| `workspace.manage` | Workspace settings, transfer ownership, delete | ✓ | | | | | | | | |
| `roles.manage` | Create and edit custom roles | ✓ | ✓ | | | | | | | |
| `members.manage` | Change roles, remove members, approve join requests (PM: own projects) | ✓ | ✓ | ✓ | | | | | | |
| `joincode.manage` | Create and revoke join codes (PM: own projects) | ✓ | ✓ | ✓ | | | | | | |
| `project.manage` | Create projects, edit settings, budget, approvals | ✓ | ✓ | ✓ | | | | | | |
| `project.context` | Write or edit the project brief and context; confirm AI-drafted fields (rev. 5) | ✓ | ✓ | ✓ | | | | | | |
| `srs.generate` | Generate an updated SRS draft; edit and accept its sections (rev. 5) | ✓ | ✓ | ✓ | ✓ | | | | | |
| `srs.publish` | Publish an SRS version; override the readiness checklist with a reason (rev. 5) | ✓ | ✓ | ✓ | | | | | | |
| `channel.manage` | Create, rename, archive channels | ✓ | ✓ | ✓ | ✓ | | | | | |
| `message.post` | Post, reply, mention | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | |
| `req.propose` | Propose requirements, drafts, lint, pre-flight | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | | |
| `req.comment` | Comment on requirements | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | |
| `req.vote` | Support or oppose | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | | |
| `req.link` | Assert links between requirements | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | | | |
| `doc.upload` | Upload SRS as proposals | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | | |
| `baseline.manage` | Upload SRS as baseline, freeze snapshots, approve Proposed requirements | ✓ | ✓ | ✓ | ✓ | | | | | |
| `issue.open` | Open issues, comment on issues | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | |
| `issue.manage` | Assign, label, close any issue | ✓ | ✓ | ✓ | ✓ | | | | | |
| `rcr.open` | Open change requests | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | | |
| `rcr.review` | Review when requested (approval counts if eligible under FR-65) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | |
| `rcr.merge` | Merge an approved change request | ✓ | ✓ | ✓ | ✓ | | | | | |
| `finding.review` | Confirm, dismiss, merge, reclassify findings | ✓ | ✓ | ✓ | ✓ | | | | protected only | |
| `req.protect` | Mark requirements protected | ✓ | ✓ | | | | | | ✓ | |
| `protected.signoff` | Sign off findings and changes on protected requirements | | | | | | | | ✓ | |
| `req.implement` | Mark Approved → Implemented | ✓ | ✓ | ✓ | ✓ | ✓ | | | | |
| `audit.export` | Export the audit trail | ✓ | ✓ | | | | | | ✓ | |
| `view` | See dashboards, map, analytics, timelines; export reports | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

- A member's **owned** requirements: the owner is always a required reviewer of change requests on them, but never approves their own change request (SX-13).
- Join codes can grant any role **except** Owner and Admin (SX-14).
- Private channels are visible only to listed members, whatever their role.

### 1.23 Project Context and the Updated SRS — FR-103–FR-107 *(New — rev. 5)*

Requirements cannot be classified well without knowing what the product is, who uses it and what its terms mean. Revision 5 therefore makes project context compulsory before any analysis, and closes the loop at the end by turning the clarified baseline back into an updated SRS.

| ID | Requirement | Source Stakeholder(s) |
|---|---|---|
| FR-103 | A project shall not be analysed until it has **confirmed project context**. When creating a project, the Project Manager shall either upload an **initial SRS** (or another requirements document: DOCX, PDF or Markdown) or complete a **project brief**, or both. Required brief fields: purpose and problem statement; scope (in scope and out of scope); user classes and actors; operating environment and domain. Optional: glossary, constraints and assumptions, quality goals, applicable regulations, reference links. Until the context is confirmed the project is in **Setup**: members can join and chat, but the composer, document analysis and change requests are disabled, with a message naming the missing fields. *(SX-31)* | Project Manager; Business Analysts |
| FR-104 | When an initial SRS is uploaded, the system shall (a) extract its requirements as in FR-01–FR-06, imported as baseline or as proposals, and (b) draft the brief fields from its introduction and overall-description sections with the LLM. Every drafted field is labelled *AI-drafted* until the Project Manager confirms or edits it; the project becomes **Active** only after confirmation. *(SX-31)* | Project Manager |
| FR-105 | Every LLM call made for a project (classification, clarification, suggestions, consequence narrative, AI wording, pre-flight and SRS drafting) shall include a bounded **context pack** built from the confirmed context: a summary of the brief, the actors, the glossary entries whose terms appear in the inputs, and up to three of the most relevant initial-SRS sections, at most 1,500 tokens in all. Findings, suggestions and generated sections record the `context_version` they used. Editing the context needs `project.context`, creates a new version with author and reason, and offers to re-run analysis of open findings; it never changes a requirement. *(SX-31)* | Business Analysts; Software Architects |
| FR-106 | A member with `srs.generate` shall be able to **generate an updated SRS draft** from the current baseline or a snapshot. A readiness checklist is shown first: open clarification questions, open High findings without accepted risk, open change requests and open issues on included requirements. Generation is allowed when nothing is blocking, or after a Project Manager override with a recorded reason, in which case the open-items report (FR-102) is attached. The draft follows the ISO/IEC/IEEE 29148 outline (introduction, overall description, specific requirements, appendices). The **system** inserts every requirement statement verbatim with its ID, priority and owner; the **LLM writes only the narrative**: purpose, scope, definitions from the glossary, product perspective, user classes, assumptions, a change summary since the previous SRS version (from the change log, FR-95) and a decisions appendix (resolved conflicts with the chosen option and decision owner). *(SX-32)* | Business Analysts; Project Manager; Client / Product Owner |
| FR-107 | The SRS draft shall be reviewed **section by section**: accept, edit, or regenerate with an instruction. AI-written text stays labelled until accepted. A member with `srs.publish` publishes the SRS once every section is accepted and the fidelity check (DR-25) passes. Published SRS versions are numbered (SRS v1.0, v1.1, …), immutable, linked to their baseline revision, comparable with the previous version, and exportable as **DOCX, PDF and Markdown**, with the open-items report alongside. The template export of FR-74 remains as the no-LLM fallback. *(SX-32)* | Business Analysts; Client / Product Owner |

---

## 2. Non-Functional Requirements (NFR)

| ID | Category | Requirement |
|---|---|---|
| NFR-01 | Performance | Complete analysis of a standard-size SRS (about 100 pages / 150–300 requirements) in under 5 minutes for 90% of jobs, via the async job queue, with LLM calls in parallel up to a configurable concurrency. Measured on the benchmark at Checkpoint 1; time lost to provider outages and retries is reported separately. *(Amended — CR-07)* |
| NFR-02 | Performance | Synchronous API requests (login, list, status, detail, post message) shall respond within 2 s for 95% of requests. Analysis is asynchronous and governed by NFR-01, NFR-25 and NFR-26. *(Clarified — CR-07)* |
| NFR-03 | Performance | The dashboard shall load and render initial results within 3 s on a standard broadband connection. |
| NFR-04 | Scalability | The queue shall accept at least 50 concurrent jobs; MVP target 5 document jobs in parallel plus live analysis on a separate high-priority queue; industry target 50 or more. *(Amended — CR-07, CR-08)* |
| NFR-05 | Scalability | The embedding pre-filter shall reduce LLM classification calls by at least 70% versus all-pairs comparison. |
| NFR-06 | Scalability | *Post-MVP (with FR-40).* The API shall scale to the request volumes agreed with third-party consumers. *(Scoped — CR-08)* |
| NFR-07 | Reliability | Retry failed LLM API calls up to 3 times with exponential backoff before marking a classification failed; handle extraction, embedding, vector-search, real-time and email failures gracefully with actionable status. |
| NFR-08 | Reliability | Industry target: 99.5% uptime. MVP: best effort, observed through the health endpoints. *(Scoped — CR-08)* |
| NFR-09 | Reliability | Automated backup and recovery for requirement data, messages and audit logs. MVP: the managed database's automated backups plus a documented restore procedure. *(Scoped — CR-08)* |
| NFR-10 | Security | All data shall be encrypted at rest and in transit (TLS 1.2+), including WebSocket traffic (WSS). |
| NFR-11 | Security | Enforce role-based access control tied to authenticated identity **and active workspace membership**, re-checked on every REST request and every WebSocket subscription, so users see only the workspaces, projects and channels they are entitled to. *(Amended — SX-06)* |
| NFR-12 | Security | Protect credentials, join codes and external AI-service API keys from source-control, log and client-side exposure; store join codes only as hashes (NFR-35). |
| NFR-13 | Security | All access to protected compliance-critical requirements shall be logged for audit purposes. |
| NFR-14 | Compliance & Data Residency | Where a regulation is identified (DR-12), the deployment shall support its data-residency, retention and right-to-erasure needs: requirement text, message text and finding content can be erased while the pseudonymised audit record is kept (FR-36). Requirement text sent to the LLM provider is a disclosed data flow; chat text is sent only when chat detection is enabled (NFR-30). *(Amended — CR-04, SC-2, SX-04)* |
| NFR-15 | Usability | Clarification questions, flag explanations and consequence reports shall be understandable to a QA engineer, BA or contributor without knowledge of the underlying AI model. |
| NFR-16 | Usability | MVP: one dashboard with role-appropriate default filters; a simplified executive view belongs to FR-32 (post-MVP). *(Scoped — CR-12)* |
| NFR-17 | Explainability | Every AI-generated finding, suggestion, summary and answer shall carry evidence or citations and be visibly distinguishable from human-authored or approved information. |
| NFR-18 | Maintainability | Detection criteria, thresholds, risk-rule thresholds and approval settings shall be configurable without code changes; new input formats addable via the parser registry. |
| NFR-19 | Maintainability | Ingestion, embedding, classification, consequence analysis, real-time delivery and presentation shall be separate modules with narrow interfaces. |
| NFR-20 | Interoperability | *Post-MVP (with FR-39/FR-40).* Standard, documented protocols for third-party integrations. *(Scoped — CR-08)* |
| NFR-21 | Accuracy | False-positive rate for conflict/duplicate detection below an agreed threshold, validated on a labelled benchmark (precision/recall/F1 per category), reported separately for document-style and post-style requirements. |
| NFR-22 | Accuracy | The confidence score shall be calibrated and periodically re-validated against user feedback. |
| NFR-23 | Portability | The system shall run identically in local development and production via Docker Compose / containers. |
| NFR-24 | Performance (real-time) | A message shall reach other connected members of its channel within 1 s at p95, with 50 concurrent connected users per workspace (MVP target). *(New — SX-07)* |
| NFR-25 | Performance (live analysis) | The result card for a requirement post shall appear within 60 s for 90% of posts, against a baseline of up to 500 requirements, excluding time spent waiting for budget. *(New)* |
| NFR-26 | Performance (consequences) | A consequence report shall be ready within 90 s for 90% of change requests, against a baseline of up to 500 requirements. *(New)* |
| NFR-27 | Security (tenant isolation) | Removing a member or downgrading a role shall take effect on the next REST request and close that member's affected WebSocket connections within 5 s. Another tenant's resource always returns 404. *(New — SX-11, ADR-12)* |
| NFR-28 | Cost & abuse control | Rate limits per user and per workspace on posts, join-code attempts, pre-flight checks and change requests; a monthly LLM-call budget per project, with visible usage; analysis that exceeds the budget waits rather than failing. *(New — SX-10)* |
| NFR-29 | Accessibility | Core flows (sign-in, channels, posting, findings, change requests, notifications) shall meet WCAG 2.1 AA; severity and category are never conveyed by colour alone. *(New)* |
| NFR-30 | Privacy | Chat message text shall not be sent to an external LLM unless chat detection (FR-58) is enabled for that project; the setting shows the disclosure. *(New — SX-04)* |
| NFR-31 | Usability (onboarding) | A newly invited contributor shall be able to join, find their channel and post their first requirement within 5 minutes without training, validated in a usability session. *(New)* |
| NFR-32 | Performance (live map) | A change to the map's data shall be visible on every connected viewer's map within 2 s at p95 after the triggering commit or analysis completion. *(New — SX-16)* |
| NFR-33 | Performance (map size) | The map shall stay responsive (no interaction frame longer than 100 ms on a mid-range laptop) with 500 nodes and 2,000 edges; above 300 nodes it may default to a clustered view. *(New)* |
| NFR-34 | Performance (lint) | Lint feedback shall appear within 300 ms after typing pauses; similar-requirement hints within 1 s. *(New)* |
| NFR-35 | Security (join codes) | Join codes shall be random with at least 40 bits of entropy (e.g. 8 characters from a 32-character alphabet), stored only as hashes and shown in full only when created; code attempts are limited to 5 per minute per IP and per account; expired, used-up or revoked codes are rejected with one generic message. *(New — SX-14)* |
| NFR-36 | AI quality (suggestions) | The distribution of suggestion outcomes (FR-94) shall be reported per category at CP2 and in the final report, together with an **expert-rated correctness** score on a sample of at least 30 suggestions, because acceptance is not correctness. Suggestions for a finding shall appear within 30 s for 90% of findings, generated asynchronously so they never delay the finding itself. *(Amended — rev. 4)* |
| NFR-37 | Detection recall | Recall per category shall be measured at CP1 and CP2 on the labelled benchmark, which must include conflicts worded differently enough to fall **below the similarity threshold**; the report shows how many known conflicts each layer caught (similarity + AI, rule checks) and how many were missed. In use, the share of human-raised findings that the AI and rules had not flagged ("AI misses") shall be tracked per category. *(New — rev. 4, SX-28)* |
| NFR-38 | Performance & cost (SRS generation) | An updated SRS draft for 300 requirements shall be ready within 5 minutes for 90% of runs, using at most one LLM call per narrative section (about 12) plus explicit regenerations, all counted against the project budget. *(New — rev. 5)* |
| NFR-39 | AI quality (context) | The benefit of the context pack shall be measured: precision and recall per category on the benchmark with and without the context pack, reported at CP1 and in the final report. *(New — rev. 5)* |

## 3. Domain Requirements (DR)

| ID | Requirement |
|---|---|
| DR-01 | The system shall classify requirement issues using the **five** categories adopted by the team (ADR-02) — Conflicting, Duplicate, Ambiguous, Incomplete, Dependent — grounded in requirements-engineering practice. *(Amended — CR-01)* |
| DR-02 | The system shall process SRS documents structured according to common industry templates (IEEE 830 / ISO/IEC/IEEE 29148): extraction tolerates their headings, numbering and front matter; template-specific parsers are not part of the MVP. *(Scoped — G-5)* |
| DR-03 | The system shall preserve unique requirement identifiers present in the source document rather than regenerating its own numbering scheme. |
| DR-04 | The system shall not silently delete, merge, or alter a requirement's original text; any suggested resolution must be presented for human approval — automated tools assist but do not replace human sign-off. |
| DR-05 | Requirements marked compliance-critical shall be exempt from automatic duplicate-removal suggestions and routed to mandatory manual review; they are still analysed and flagged. *(Clarified — CR-03)* |
| DR-06 | The system shall support bidirectional traceability from a finding back to the exact source requirement(s) and their origin — document version, post or change request. |
| DR-07 | Ambiguity detection shall be grounded in recognized linguistic ambiguity patterns, not generic LLM judgment alone. |
| DR-08 | The system shall maintain a full change history for every requirement, consistent with configuration-management practice. |
| DR-09 | A conflict exists when two or more requirements cannot reasonably be satisfied together under the same stated context; similarity alone is insufficient evidence of conflict or duplication. |
| DR-10 | Semantic similarity search is a retrieval/filtering mechanism used to generate candidate pairs; it is not itself the business definition of any category. |
| DR-11 | Requirements may originate from different stakeholder groups; provenance shall be preserved and is relevant when analysing conflicts, priorities, dependencies and resolution paths. |
| DR-12 | Compliance and regulatory rules are scenario-dependent and shall not be assumed unless the analysed SRS or engagement identifies them. |
| DR-13 | Only Approved (and Implemented) requirements form the baseline. Proposed requirements are analysed against the baseline but never change it. *(New — SX-08)* |
| DR-14 | After approval, a requirement's text changes only through an approved change request; it is never edited in place. *(New — SX-03)* |
| DR-15 | Conversation is not requirements: chat messages are context, and only confirmed requirement posts or approved imports become requirements. *(New — SX-04)* |
| DR-16 | Consequences describe requirements, owners, stakeholder groups and linked work items recorded in the system; the system shall not claim schedule or cost impact it cannot compute. *(New — SX-12, consistent with CR-11)* |
| DR-17 | Votes, comments and discussion are advisory input; only the approval policy and a merge change the baseline. *(New)* |
| DR-18 | Requirement statements should follow EARS patterns where possible; deviations are flagged by the lint, never blocked. *(New — ADR-23)* |
| DR-19 | Human-asserted links and AI-detected relationships are distinct kinds of evidence; the AI never deletes or overrides a human link, and the map shows them differently. *(New)* |
| DR-20 | AI resolution suggestions are proposals only: a human decides, and every applied change passes through the normal change path (DR-04, DR-14). The final decision and its reason are recorded with the suggestion so that later readers can see what the AI proposed and what people chose. *(New — rev. 3)* |
| DR-21 | Analysis can miss issues. "No issue detected" shall never be presented as "verified", "safe" or "conflict-free"; every clean result offers a way to raise a concern. *(New — rev. 4)* |
| DR-22 | The approved baseline and anything not approved are never mixed: exports, snapshots and the Baseline map layer contain only Approved and Implemented requirements; everything else is reported separately. *(New — rev. 4)* |
| DR-23 | Decisions are made by the designated decision owner under the project's decision rules, never by majority vote or approval count alone. *(New — rev. 4)* |
| DR-24 | Requirements are interpreted within their project’s stated context. A project without confirmed context is not analysed. The context is input to analysis, never a requirement: statements in the brief enter the baseline only if they are posted or imported as requirements. *(New — rev. 5)* |
| DR-25 | A generated SRS shall be faithful to the baseline: each Approved and Implemented requirement appears exactly once with its approved text verbatim and its ID; no Proposed or rejected text appears; narrative sections contain no "shall" or "must" statement that is not a baseline requirement. A fidelity check enforces this before publishing. *(New — rev. 5)* |

## 4. Traceability Notes

- FR-21, FR-65 and NFR-13 jointly ensure protected requirements are never auto-resolved, merged, dismissed or changed without a compliance reviewer's sign-off, while still being analysed and flagged (DR-04, DR-05; CR-03, SX-13).
- FR-13, FR-18, NFR-21 and NFR-22 answer the Business Analysts' question of what would make them trust an automated flag: a visible confidence score plus a periodically re-validated feedback loop.
- FR-56, FR-63, NFR-05 and NFR-28 extend the pre-filter decision (ADR-01, DR-10) to live analysis: each new requirement is compared with its top-*k* neighbours only, under a budget.
- FR-62–FR-66 with DR-14 replace in-place editing (CR-20) with a single, auditable change path; US-11's impact engine is reused inside the consequence report.
- FR-69–FR-72 close the loop the old scope lacked: the people affected by a change are told, and every decision is visible on the requirement's timeline.
- FR-58 and NFR-30 encode the privacy trade-off of chat detection (SX-04) as both a feature switch and a measurable obligation.
- FR-81, FR-82, FR-83 and DR-18 move quality checking to the moment of writing: EARS templates and a deterministic lint prevent many ambiguity findings before any LLM call.
- FR-84, FR-85, NFR-32 and NFR-33 make the graph that used to be the final output of SRS analysis a live, shared view of the project.
- FR-97–FR-102 and DR-21–DR-23 are the trust layer: people can raise problems the AI cannot know, agreement has exact rules, every change shows what it fixed and what it broke, the right person decides, missed conflicts are measured and admitted, and the approved specification never hides open items.
- FR-68, FR-94 and DR-20 put a human in the loop for every AI-proposed solution, and turn people's decisions into examples that improve later suggestions.
- FR-84, FR-95 and FR-96 show every change twice: on the map and in writing.
- FR-103–FR-105, NFR-39 and DR-24 give the LLM the context it needs to classify correctly: no project is analysed until the Project Manager has supplied an initial SRS or a brief, and every prompt carries a bounded context pack.
- FR-106, FR-107, NFR-38 and DR-25 close the loop: once findings are clarified and changes merged, the baseline becomes an updated, reviewed SRS that can be exported, with requirement text never rewritten by the LLM.
- FR-65, FR-87, FR-88 and FR-89 implement the GitHub model for the case where two people's requirements are involved: an issue assigned to both owners, owners as required reviewers, and needs-update when changes compete.

## 5. Stakeholder Elicitation Summary

| Stakeholder | Technique | Status |
|---|---|---|
| Business Analysts / Requirements Engineers | Job Shadowing / Observation | Complete |
| Project Managers | Structured Interviews | Complete; follow-up interview on consequence reports and risk rules (Sprint 1) |
| Software Architects / Senior Developers | JAD Sessions | Complete |
| Client / Product Owner | Interviews + Document Analysis | Complete; confirm Step 7 decisions (Sprint 0) |
| QA / Test Engineers | Prototyping (low-fidelity mockups) | Complete; repeat for the workspace flows (US-22, Sprint 2) |
| Executive Sponsor / Budget Holder | High-level interviews + surveys | Complete; confirm the LLM budget policy (Sprint 0) |
| Legal / Compliance Team | Document Analysis | Complete; confirm chat-detection opt-in and erasure of messages (Sprint 0) |
| IT / DevOps / System Administrators | See Lab 6 | Complete; confirm invite-only registration (Sprint 0) |
| **Workspace Owner / Project Manager** *(new)* | Interviews + competitive analysis of chat tools (Slack) and code-review tools (GitHub) | Planned, Sprint 0 |
| **Stakeholder Contributors** *(new: domain experts who post requirements)* | Usability sessions on low-fidelity prototypes | Planned, Sprint 2 (US-22) |
| End Customers (Indirect) | Feedback mining / surveys | Ongoing by design |
| Third-Party API Consumers | Pilot feedback channel | Ongoing by design |

## 6. Amendment Logs

### 6.1 Step 6 (unchanged)

| Tag | What changed | Requirements touched |
|---|---|---|
| CR-01 | Five categories everywhere | DR-01, FR-11, FR-22, FR-27 |
| CR-02 | Pair-based versus single-requirement categories | FR-09, FR-11 |
| CR-03 | Protected requirements analysed and flagged, never auto-resolved | FR-21, DR-05 |
| CR-04 | Erasure versus immutable audit | NFR-14, FR-19, FR-36 |
| CR-05 | Similarity decides candidates only | FR-12 |
| CR-06 | Segmentation versus preserving wording and IDs | FR-03, FR-04, FR-06 |
| CR-07 | Performance targets made consistent | NFR-01, NFR-02, NFR-04 |
| CR-08 | Industry-grade NFRs scoped | NFR-04, NFR-06, NFR-08, NFR-09, NFR-20 |
| CR-09 | Impact covers requirements only | FR-24 |
| CR-10 | Report channels for the MVP | FR-30 |
| CR-11 | Executive metrics from system data | FR-32 |
| CR-12 | One dashboard in the MVP | NFR-16 |
| CR-13 | Low-fidelity preview is a validation activity | FR-31 |
| CR-14 | Escalation log merged into audit | FR-35, FR-36 |
| CR-15 | Severity defined | FR-42, FR-27 |
| CR-21, CR-22 | Numbering and terminology | §0, FR-37 |
| SC-2, SC-3 | Stakeholder trade-offs | NFR-14, FR-16 |
| G-1, G-3, G-5 | Coverage gaps scoped | FR-05, FR-33, FR-34, DR-02 |

### 6.2 Step 7 — scope extension

| Tag | What changed | Requirements touched |
|---|---|---|
| SX-01 | Project reintroduced under Workspace (reverses CR-22) | FR-38, FR-47 |
| SX-02 | Invite-only registration | FR-37, FR-44 |
| SX-03 | Changes to Approved requirements go through change requests | FR-06, FR-24, FR-25, FR-26, FR-62, DR-14 |
| SX-04 | Chat detection opt-in | FR-58, NFR-14, NFR-30, DR-15 |
| SX-05 | In-app notifications Must, email digest Could (revises CR-10) | FR-30, FR-69–FR-71 |
| SX-06 | Membership table; a role per workspace | FR-46, NFR-11 |
| SX-07 | WebSocket push, REST writes | FR-52, NFR-24 |
| SX-08 | Import as baseline or as proposals | FR-01, FR-61, DR-13 |
| SX-09 | Findings scoped to projects and analysis runs | FR-56 (design only) |
| SX-10 | LLM budget, cache, rate limits | FR-56, NFR-28 |
| SX-11 | Member removal keeps attribution | FR-45, NFR-27 |
| SX-12 | Consequences limited to computable data | FR-63, DR-16 |
| SX-13 | No self-approval; compliance sign-off for protected | FR-21, FR-65 |
| G-1 | Provenance resolved through posts and uploads | FR-05, FR-60 |
| New | Workspace, channels, intake, change requests, notifications, baselines, knowledge, analytics | FR-43–FR-76, NFR-24–NFR-31, DR-13–DR-16 |
| SX-14 | Join codes with expiry, use limit, approval, revocation | FR-44, FR-77, NFR-35 |
| SX-15 | Permission-based roles; 9 defaults; custom and project roles | FR-48, FR-78, FR-79 |
| SX-16 | Live map from stored results via deltas | FR-29, FR-84, NFR-32 |
| SX-17 | Map layers | FR-85 |
| SX-18 | Finding, issue and clarification separated | FR-86, FR-87 |
| SX-19 | Approval separate from merge | FR-65, FR-66, FR-88 |
| SX-20 | Base version and needs update | FR-62, FR-64, FR-89 |
| SX-21 | SMTP out of the MVP | FR-44, FR-71 |
| New (rev. 2) | Action set, EARS composer, lint, pre-flight, votes, watch, links, AI wording | FR-80–FR-83, FR-90, FR-91, FR-93, NFR-34, DR-17–DR-19 |
| SX-22 (rev. 3) | AI resolution suggestions for every finding, human decides | FR-68, FR-94, DR-20 |
| SX-24 (rev. 4) | Human-raised concerns alongside AI findings | FR-97 |
| SX-25 (rev. 4) | Agreement rules; approvals tied to proposal revisions | FR-98 |
| SX-26 (rev. 4) | Findings delta after every change | FR-99 |
| SX-27 (rev. 4) | Decision rules and decision owners, no voting | FR-65, FR-100, DR-23 |
| SX-28 (rev. 4) | Rule-based cross-checks; recall measured; limits stated | FR-101, NFR-37, DR-21 |
| SX-29 (rev. 4) | Approved-only export plus open-items report | FR-74, FR-102, DR-22 |
| SX-30 (rev. 4) | Structured feedback; no self-learning claim | FR-94, NFR-36 |
| SX-23 (rev. 3) | Feedback examples stay inside their project | FR-94 |
| New (rev. 3) | Written change log and summaries for the map | FR-95, FR-96, NFR-36 |
| SX-31 (rev. 5) | Project context compulsory before analysis; context pack in every LLM call | FR-47, FR-103–FR-105, NFR-39, DR-24 |
| SX-32 (rev. 5) | LLM-generated updated SRS, reviewed section by section, published and exported | FR-74, FR-106, FR-107, NFR-38, DR-25 |
| SX-33 (rev. 5) | Work-item links deferred to make room | FR-67 |

## 7. Scope Classification

| Scope | Requirements |
|---|---|
| **MVP** | FR-01–FR-31, FR-36–FR-38, FR-42–FR-52, FR-54–FR-66, FR-69, FR-70, FR-72–FR-74, FR-76–FR-91, FR-93–FR-107, **FR-68**; NFR-01–NFR-03, NFR-05, NFR-07, NFR-10–NFR-13, NFR-15, NFR-17–NFR-19, NFR-21–NFR-39; DR-01–DR-25 (FR-30 report export and FR-58 chat detection are deferred in rev. 4 with US-16 and US-32; FR-76 analytics beyond the dashboard deferred with US-44) |
| **MVP, reduced target** | NFR-04 (5 parallel document jobs), NFR-08 (best effort), NFR-09 (managed backups) |
| **Post-MVP** | FR-32, FR-33, FR-34, FR-39, FR-40, FR-41, FR-71 (email digest), FR-75 (Q&A), FR-92 (structural change requests), FR-53 (workspace search: deferred in rev. 3), FR-67 (work-item links: deferred in rev. 5); NFR-06, NFR-16 (executive view), NFR-20; meeting-transcript intake (US-47); NFR-14 applies only when a regulation is identified (DR-12). See `IT314_RCD_Scope_Extension_v5.md` §12 |
