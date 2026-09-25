# Feature Documentation

**Per-Feature Deep Dive — Highest-Risk & Core Stories**

| | |
|---|---|
| **Scope** | US-01, US-02, US-05, US-07, US-09, US-11, US-19 — the MVP-critical and highest-uncertainty stories |
| **Full backlog** | See `feature-catalog.md` for all 23 stories; full front/back cards in the team's Consolidated Product Backlog source document |

---

## 1. US-01 — Upload SRS Document (Multi-Format)

| Stakeholder | Priority | Points | FR trace | Sprint |
|---|---|---|---|---|
| Business Analyst | Must | 5 | FR-02, FR-04 | Sprint 1 |

*As a Business Analyst, I want to upload an SRS document in PDF, Word, plain text, or ReqIF format, so that I can begin analysis without manually reformatting or re-entering my team's existing documents.*

**Acceptance Criteria**
- Given a supported file (.pdf, .docx, .txt, ReqIF) is uploaded, when submitted, the system accepts it and returns a document ID with initial processing status.
- Given an unsupported or corrupted file, when upload is attempted, the system rejects it with a clear, specific error message.
- Given a file exceeding the configured size limit, when uploaded, the system rejects it before processing begins.

> **Note:** Exact size limit and supported-format list still need to be finalized with the BA/Architect group — open elicitation item.

## 2. US-02 — Automatic Requirement Extraction

| Stakeholder | Priority | Points | FR trace | Sprint |
|---|---|---|---|---|
| Business Analyst | Must | 5 | FR-03, FR-04 | Sprint 1 |

*As a Business Analyst, I want the uploaded document automatically parsed and split into individual, distinct requirement statements, so that I don't have to enumerate hundreds of requirements by hand.*

**Acceptance Criteria**
- Raw text is extracted from PDF/Word sources and segmented into distinct requirement units.
- Each requirement is stored with a unique ID and source location; existing REQ-IDs are preserved where present.
- Non-requirement content (TOC, headers/footers) is excluded from extraction.
- Extraction failures or low-confidence segmentation are surfaced for manual review, not silently dropped.

## 3. US-05 — Detect Requirement Issues (5-Category Classification)

| Stakeholder | Priority | Points | FR trace | Sprint |
|---|---|---|---|---|
| Business Analyst, Project Manager | Must | 13 | FR-07, FR-09, FR-10, FR-11, FR-12 | Sprint 2 (core) |

*As a Business Analyst, I want candidate requirement pairs automatically classified as Conflicting, Duplicate, Ambiguous, Incomplete, or Dependent, so that I can resolve issues before development begins without manually cross-referencing every requirement pair.*

**Acceptance Criteria**
- Candidate pairs are produced via the embedding similarity pre-filter before detailed classification, not brute-force all-pairs comparison.
- Each classification uses one of the five supported categories, is never based on textual similarity alone, and identifies all requirements involved — not just the first pair found.
- Both requirements in a flagged pair are shown side by side, with the specific conflicting/ambiguous clause highlighted where possible.
- An Incomplete classification indicates the specific missing information where determinable.

> **Note:** This is the system's core value proposition and must be protected first if the schedule slips. It is also the single riskiest, highest-uncertainty story in the backlog — should be split into sub-tasks during refinement (detect-conflicts, detect-duplicates+ambiguous, detect-incomplete+dependent).

## 4. US-07 — Explain Findings with Confidence Score & Context

| Stakeholder | Priority | Points | FR trace | Sprint |
|---|---|---|---|---|
| Business Analyst | Must | 5 | FR-13, FR-15, FR-16 | Sprint 2 |

*As a Business Analyst, I want every flagged issue to include a plain-language explanation, a confidence score, and supporting context (related IDs, source section), so that I can judge reliability before acting on it, without digging through the original SRS.*

**Acceptance Criteria**
- Every finding shows a confidence score (0–100%) alongside its classification.
- Findings below a configurable confidence threshold are marked "low confidence — recommend manual review."
- A natural-language rationale and related requirement IDs/source section accompany every flag.

> **Note:** Safest item to push into Sprint 3 if Sprint 2 is trending late — US-05 without US-07 still produces a usable, if less polished, result.

## 5. US-09 — Generate Clarification Questions

| Stakeholder | Priority | Points | FR trace | Sprint |
|---|---|---|---|---|
| Business Analyst, QA Engineer | Must | 5 | FR-22, FR-23 | Sprint 3 |

*As a QA Engineer, I want a clarification question generated for every Ambiguous or Conflicting finding, so that I can resolve the issue without further discussion.*

**Acceptance Criteria**
- Every finding flagged Ambiguous or Conflicting has an auto-generated clarification question.
- A user can mark a clarification as answered and attach the resolution text.
- The question is understandable without knowledge of the underlying AI/NLP model (NFR-15).

## 6. US-11 — Run Change-Impact Analysis on Requirement Edit

| Stakeholder | Priority | Points | FR trace | Sprint |
|---|---|---|---|---|
| Project Manager, Software Architect | Must | 8 | FR-24, FR-25 | Sprint 3 |

*As a Project Manager, I want to see everything a requirement edit might affect before I save it, so that I don't introduce a new conflict without realizing it.*

**Acceptance Criteria**
- Editing a requirement triggers a change-impact analysis identifying affected requirements.
- The impacted list is shown before the change is saved, not only after.
- A version history entry is created for every edit (FR-26).

> **Note:** One of the two features explicitly named as first to cut if the Week 7 checkpoint slips.

## 7. US-19 — Authenticate via JWT (SSO Path for Later)

| Stakeholder | Priority | Points | FR trace | Sprint |
|---|---|---|---|---|
| System Administrator, All Users | Must | 5 | FR-37, FR-38 | Sprint 2 |

*As a System Administrator, I want users to authenticate before accessing any document or dashboard, so that requirement data stays scoped to the right workspace.*

**Acceptance Criteria**
- All API endpoints except login require a valid JWT.
- Documents and analysis results are scoped to the uploading user's workspace (FR-38).
- The design leaves an SSO/LDAP integration point for a future enterprise deployment without requiring it for MVP.
