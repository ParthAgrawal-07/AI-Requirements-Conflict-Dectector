# Feature Documentation

**Per-Feature Deep Dive — Highest-Risk & Core Stories**

| | |
|---|---|
| **Scope** | US-01, US-02, US-05, US-07, US-09, US-11, US-19 — the MVP-critical and highest-uncertainty stories |
| **Source** | Story text and acceptance criteria are copied from [`../product-backlog.md`](../product-backlog.md), which wins if the two disagree. The Sprint column, *Implementation* lines and notes are added here. |
| **Full backlog** | See `feature-catalog.md` for all 23 stories |

---

## 1. US-01 — Upload SRS Document (Multi-Format)

| Stakeholder | Priority | Points | FR trace | Sprint |
|---|---|---|---|---|
| Business Analyst | Must | 5 | FR-01, FR-02, FR-04 | Sprint 1 |

*As a Business Analyst, I want to upload an SRS document in PDF or Word (.docx) format, so that I can begin analysis without manually reformatting or re-entering my team's existing documents.*

**Acceptance Criteria**
- Given a supported file (.pdf or .docx) is uploaded, when submitted, the system accepts it and returns a document ID with initial processing status.
- Given an unsupported or corrupted file, when upload is attempted, the system rejects it with a clear, specific error message.
- Given a file exceeding the configured size limit, when uploaded, the system rejects it before processing begins.

> **Decided (CR-16):** the size limit is 25 MB by default and configurable (`MAX_UPLOAD_SIZE_MB`). Supported formats for this iteration are PDF and DOCX. Plain text is a Could (post-MVP); ReqIF is deferred with the tool integrations (US-21).
>
> **Implementation:** upload endpoint, validation and storage in review (PR #7).

## 2. US-02 — Automatic Requirement Extraction

| Stakeholder | Priority | Points | FR trace | Sprint |
|---|---|---|---|---|
| Business Analyst | Must | 5 | FR-03, FR-04 | Sprint 1 |

*As a Business Analyst, I want the uploaded document automatically parsed and split into individual, distinct requirement statements, so that I don't have to enumerate hundreds of requirements by hand.*

**Acceptance Criteria**
- Raw text is extracted from PDF/Word sources and segmented into distinct requirement units.
- Each requirement is stored with a unique ID and source location; existing REQ-IDs are preserved where present.
- Non-requirement content (TOC, headers/footers) is excluded from extraction.
- Extraction failures or low-confidence segmentation are surfaced for manual review, not silently dropped. Segmentation follows the document's own requirement boundaries and never rewrites wording; an item with no printed ID is stored without one, and no provisional marker is shown as a source ID.

> **Implementation:** PDF/DOCX parsers merged in Sprint 0. Segmentation pipeline in review (PR #8). Design: [`../ingestion-design.md`](../ingestion-design.md).

## 3. US-05 — Detect Requirement Issues (5-Category Classification)

| Stakeholder | Priority | Points | FR trace | Sprint |
|---|---|---|---|---|
| Business Analyst, Project Manager | Must | 13 | FR-07, FR-09, FR-10, FR-11, FR-12, DR-07, DR-09, DR-10 | Sprint 2 (core) |

*As a Business Analyst, I want candidate requirement pairs automatically classified as Conflicting, Duplicate, Ambiguous, Incomplete, or Dependent, so that I can resolve issues before development begins without manually cross-referencing every requirement pair.*

**Acceptance Criteria**
- Candidate pairs are produced via the embedding similarity pre-filter before detailed classification, not brute-force all-pairs comparison.
- Each classification uses one of the five supported categories, is never based on textual similarity alone, and identifies all requirements involved — not just the first pair found. Conflicting, Duplicate and Dependent come from candidate pairs; Ambiguous and Incomplete are assessed on each requirement individually, using recognised ambiguity patterns (DR-07).
- Both requirements in a flagged pair are shown side by side, with the specific conflicting/ambiguous clause highlighted where possible.
- An Incomplete classification indicates the specific missing information where determinable.

> **Note:** This is the core value proposition and must be protected first if the schedule slips. It is also the riskiest story in the backlog, so it is split into tasks T18–T23 (see `task-breakdown.md`). The schema already supports both shapes: a finding points at exactly one of `candidate_pair_id` (pairwise) or `requirement_id` (single), enforced by a CHECK constraint. Accuracy is measured against the labeled benchmark in `sample_docs/planted_conflicts/`.

## 4. US-07 — Explain Findings with Confidence Score & Context

| Stakeholder | Priority | Points | FR trace | Sprint |
|---|---|---|---|---|
| Business Analyst | Must | 5 | FR-13, FR-14, FR-15 | Sprint 2 |

*As a Business Analyst, I want every flagged issue to include a plain-language explanation, a confidence score, and supporting context (related IDs, source section), so that I can judge reliability before acting on it, without digging through the original SRS.*

**Acceptance Criteria**
- Every finding shows a confidence score (0–100%) alongside its classification.
- Findings below a configurable confidence threshold are marked "low confidence — recommend manual review."
- A natural-language rationale and related requirement IDs/source section accompany every flag.

> **Note:** Safest item to push into Sprint 3 if Sprint 2 is trending late. US-05 without US-07 still produces a usable, if less polished, result.

## 5. US-09 — Generate Clarification Questions

| Stakeholder | Priority | Points | FR trace | Sprint |
|---|---|---|---|---|
| Business Analyst, QA Engineer | Must | 5 | FR-22, FR-23 | Sprint 3 |

*As a Business Analyst, I want a specific, context-aware clarification question generated for every Ambiguous, Incomplete, or Conflicting requirement, so that I can take a concrete question directly to the relevant stakeholder without formulating it myself.*

**Acceptance Criteria**
- Every Ambiguous, Incomplete or Conflicting flag has an auto-generated question specific to those requirements, not a generic "please clarify."
- A QA engineer can resolve the ambiguity from the question alone, without needing the original SRS.
- Generic or empty questions are treated as a generation failure and retried.
- The question can be marked Answered with resolution text attached, stored against the requirement's version history.

> **Design:** [`../clarification-impact-design.md`](../clarification-impact-design.md) §3 (proposal: 1:N clarifications per finding and a `ClarificationStatus` enum; the current schema is 1:1 with no status, pending approval).

## 6. US-11 — Run Change-Impact Analysis on Requirement Edit

| Stakeholder | Priority | Points | FR trace | Sprint |
|---|---|---|---|---|
| Project Manager, Software Architect | Must | 8 | FR-24, FR-25 | Sprint 3 |

*As a Project Manager, I want to see everything potentially affected when a requirement changes, so that I can assess schedule, scope, and technical impact before approving the change.*

**Acceptance Criteria**
- Editing a requirement shows, before the change is saved, an impact analysis that lists potentially affected requirements with the reason for each link.
- Direct impact is distinguished from indirect/transitive impact where the relationship model supports it.
- If no downstream impact exists, the system states so explicitly rather than showing an empty section.
- The impact report can be exported (PDF/CSV). Impact covers requirements only in this iteration (design elements and test cases need the tool integrations, US-21). Saving the edit creates a new version (US-12) and never alters earlier versions.

> **Note:** One of the two features named as first to cut if the Week 7 checkpoint slips. Design: [`../clarification-impact-design.md`](../clarification-impact-design.md) §4.

## 7. US-19 — Authenticate via JWT (SSO Path for Enterprise Deployment)

| Stakeholder | Priority | Points | FR trace | Sprint |
|---|---|---|---|---|
| System Administrator, All Users | Must | 5 | FR-37, FR-38, NFR-11 | Sprint 0 (login) / Sprint 2 (scoping) |

*As a user, I want to authenticate securely before accessing any workspace or dashboard, so that my organization's data stays protected and access is limited to authorized users.*

**Acceptance Criteria**
- The system requires JWT-based authentication before granting access to any document or dashboard (semester-scope baseline).
- Role-based access ensures users see only their authorized workspaces.
- (Enterprise extension) SSO/LDAP integration is architecturally accommodated without a core redesign.

> **Implementation:** done in Sprint 0: `POST /api/v1/auth/login` (OAuth2 password form), `GET /api/v1/auth/me`, the five roles, `require_roles(...)`, and every non-auth router mounted behind `get_current_user`. Still open: a shared workspace-scoping helper (T15). Until then each query must filter by `user.workspace_id` explicitly (see `backend/app/core/auth.py`).
