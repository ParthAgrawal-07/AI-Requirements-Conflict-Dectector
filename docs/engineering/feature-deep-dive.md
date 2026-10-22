# Feature Documentation

**Per-Feature Deep Dive — the Stories on the Protected Demo Paths**

| | |
|---|---|
| **Scope** | US-60, US-01, US-02, US-05, US-31, US-14, US-34, US-35, US-45, US-61: the never-cut stories that carry the most risk or the most value |
| **Source** | Cards copied from [`IT314_RCD_Product_Backlog_v5.md` §3](../planning/v5/IT314_RCD_Product_Backlog_v5.md#3-detailed-story-cards); if they differ, the backlog wins |
| **Full backlog** | `feature-catalog.md` lists all 61 stories with status |

---

## 1. US-60 — Project Context Required Before Analysis

*Path: Document path*

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

> **Status:** backend delivered on `main` (PR #27): versioned `project_contexts`, AI-drafted brief, `setup → active` gate, `GET/PUT /projects/{p}/context`. Still to do: the setup wizard UI (Abhijeet) and the context pack in every prompt (Keval).

## 2. US-01 — Upload SRS Document into a Project

*Path: Document path*

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

> **Status:** backend delivered on `main` (PRs #7, #26): upload into a project as baseline or proposals, validation, two-phase storage. UI not started.

## 3. US-02 — Automatic Requirement Extraction

*Path: Document path*

| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Must | 5 | S1 | Bansil | FR-03, FR-04 |

*As a Business Analyst, I want the document split automatically into individual requirement statements, so that I don't enumerate hundreds of requirements by hand.*

**AC**
- Raw text is extracted from PDF/DOCX and segmented along the document's own boundaries; wording is never rewritten (CR-06).
- Printed IDs are preserved; an item with no printed ID is stored without one.
- Non-requirement content (TOC, headers, footers, prose) is excluded.
- Extraction failures or low-confidence segments are surfaced for manual review, never silently dropped.

> **Status:** delivered on `main` (PR #8): segmentation along the document's own boundaries, printed IDs kept (including one-letter suffixes such as `REQ-001-A`), section headings, and `needs_review` / `review_reasons` for uncertain items.

## 4. US-05 — Detect Requirement Issues (5-Category Classification)

*Path: Document path · core value*

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

> **Note:** the riskiest story, split into tasks 5a/5b/5c with milestones on days 4, 7 and 9 of Sprint 2. Midpoint rule: if 5a is not done by day 5, US-07, US-49 and US-22 move to Sprint 3.

## 5. US-31 — Live Analysis of a Posted Requirement

*Path: Collaboration path*

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

## 6. US-14 — Live Requirements Map

*Path: Collaboration path*

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

## 7. US-34 — Consequence Checks for a Change Request

*Path: Collaboration path*

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

## 8. US-35 — Review and Merge

*Path: Collaboration path*

| Priority | Pts | Sprint | Owners | Trace |
|---|---|---|---|---|
| Must | 5 | S4 | Parth (policy, merge), Abhijeet (UI) | FR-21, FR-65, FR-66, FR-88, DR-04 |

*As a Product Owner, I want changes reviewed by the right people and merged only when they agree, so that the baseline changes only by agreement — especially when the change touches someone else's requirement.*

**AC**
- Reviewers come from the project's **decision rules** (US-57): the matching rule names the **decision owner** and required reviewers; the owners of the changed requirement and of requirements in direct conflict are always required; transitively affected owners are optional. The proposer never counts as an approver (SX-13), and votes never count.
- Reviewers approve, request changes or comment, including inline comments on the diff; each decision carries a rationale.
- **Merge** (members with `rcr.merge`) is enabled only when, for the **current proposal revision**: the base version is still the requirement's current version, the checks have re-run since the last base or proposal change, the decision owner and all required reviewers approved, and no "request changes" is outstanding. The merge re-verifies all of this inside one transaction; otherwise it shows exactly which condition is missing (FR-98).
- On merge: new version, baseline revision incremented, linked issues closed, affected findings marked stale and re-analysed, the map updated, everyone involved notified, all audited. Closing without merge leaves the baseline untouched.

## 9. US-45 — AI Resolution Suggestions with Human Feedback

*Path: Collaboration path*

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

## 10. US-61 — Generate the Updated SRS with the LLM and Review It

*Path: Document path*

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
