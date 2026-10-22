# Architecture Decision Records

**ADR-01 to ADR-29 — pre-filter, taxonomy, tenancy, real-time, trust layer, context and updated SRS**

| | |
|---|---|
| **ADR-01–ADR-07** | Accepted during planning (below, in full) |
| **ADR-08–ADR-13** | Made during Sprint 0–1 implementation; detail in `system-design.md` §11 |
| **ADR-14–ADR-29** | Proposed by the Step 7 scope extension, revisions 1–5 ([`IT314_RCD_Scope_Extension_v5.md` §9](../planning/v5/IT314_RCD_Scope_Extension_v5.md#9-proposed-architecture-decisions-adr-14-to-adr-29)); each is confirmed by its owner in the sprint that builds it |

---

## ADR-01: Embedding Pre-Filter Before LLM Classification

**Status:** Accepted

**Context:** Cross-checking every requirement pair for conflicts is an O(n²) problem. A ~200-requirement SRS has ~20,000 candidate pairs; running every pair through an LLM is slow and expensive.

**Decision:** Generate a Sentence-Transformers embedding per requirement, store it in pgvector, and only send pairs above a configurable similarity threshold to the LLM classifier.

**Consequences**
- Expected to cut LLM calls by 70%+ versus brute-force all-pairs comparison (NFR-05).
- Encoded as a domain rule too (DR-10): similarity is a filter, not itself proof of conflict or duplication — a true conflict can exist between dissimilar-sounding requirements, which this pre-filter may miss. **Revision 4** answers that gap with rule-based cross-checks that run regardless of similarity (ADR-27, FR-101) and with recall measured below the threshold (NFR-37).
- The similarity threshold must be tunable without a code change (FR-10, US-06) since an over-tight threshold silently drops true conflicts.

## ADR-02: 5-Category Issue Taxonomy (Adding "Incomplete")

**Status:** Accepted

**Context:** Seven independent team drafts of the requirements were merged. Three drafts used a 4-category taxonomy (Conflicting, Duplicate, Ambiguous, Dependent); one draft plus the official project brief text explicitly included a 5th category, Incomplete.

**Decision:** 5 categories were adopted as authoritative: Conflicting, Duplicate, Ambiguous, Incomplete, Dependent.

**Consequences**
- DR-01 was corrected to the five categories in the Step 6 conflict review (CR-01); the canonical numbering is now `requirements-spec.md` (CR-21).
- Conflicting, Duplicate and Dependent are pair-based; Ambiguous and Incomplete are assessed per requirement (CR-02, FR-11).
- Classification stories that some drafts split into 3–4 separate stories were merged into a single epic (US-05) to match how the pipeline actually executes.

## ADR-03: PostgreSQL + pgvector Over a Dedicated Vector DB

**Status:** Accepted

**Context:** Vector similarity search is needed for the embedding pre-filter, but the system also needs standard relational data (documents, requirements, findings, audit logs) with strong consistency guarantees.

**Decision:** Use PostgreSQL with the pgvector extension rather than a separate dedicated vector database (e.g., Pinecone, Weaviate).

**Consequences**
- One database to operate, back up, and reason about transactionally — simpler for a small, one-semester team.
- pgvector indexing (IVFFlat/HNSW) is less specialized than a purpose-built vector DB; acceptable at the semester's expected data scale.

## ADR-04: Async Job Queue (Celery + Redis) for the Analysis Pipeline

**Status:** Accepted

**Context:** Full-document analysis (extraction → embedding → classification) can take minutes for a large SRS and must not block the upload request.

**Decision:** Run the pipeline as a Celery task backed by Redis; the API returns immediately with a document ID and status, and the frontend polls/subscribes for progress (US-03).

**Update (Step 7, SX-07):** clients no longer rely on polling alone — events are pushed over WebSocket (ADR-15), with polling kept as the fallback.

**Consequences**
- Meets NFR-01 (target completion time) and NFR-04 (concurrent job support) without a synchronous request timing out.
- Adds operational complexity (a worker process, a broker) that Sprint 0 must account for in the Docker Compose setup.

## ADR-05: Precision/Recall/F1 Over an Arbitrary Agreement Target

**Status:** Accepted

**Context:** An early draft proposed an "80% agreement" accuracy target for classification, which is not a standard, benchmarkable metric in a classification system.

**Decision:** Standardize on precision, recall, and F1 per category, validated against a labeled benchmark set (NFR-21, NFR-22).

**Consequences**
- Requires building a labeled benchmark set of requirement pairs before the Week 7 checkpoint — see `test-plan.md`.
- Makes the false-positive/false-negative trade-off explicit and tunable per category rather than hidden in a single aggregate number.

## ADR-06: Human-in-the-Loop by Domain Rule, Not Just UX Choice

**Status:** Accepted

**Context:** An AI classification system that silently edits or removes requirements is a serious risk in a requirements-engineering context — false positives compound if left unchecked, and compliance-critical text must never be altered without sign-off.

**Decision:** Encode "no silent delete/merge/alter" and "protected requirements require manual review" as domain requirements (DR-04, DR-05), not merely as default UI behavior that could later be bypassed.

**Consequences**
- Every resolution path (confirm/dismiss/merge/reclassify, US-10) requires an explicit human action, logged for audit (FR-19, NFR-13).
- AI-generated content must remain visually distinguishable from human-approved content (NFR-17) — a frontend requirement, not just a backend one.

## ADR-07: JWT-Only Auth for MVP; SSO Deferred

**Status:** Accepted

**Context:** FR-37 allows for "the organization's existing SSO/LDAP where applicable," but implementing real SSO federation is a significant, deployment-specific effort not required to demonstrate the core value proposition.

**Decision:** Ship JWT-based authentication only for the semester MVP (US-19); leave the SSO/LDAP integration point named in the requirement but unimplemented.

**Consequences**
- Keeps auth scope inside one sprint (Sprint 1 in the rev. 5 plan) rather than expanding into an enterprise-identity integration project.
- **Step 7 (SX-02):** an account can be created only with a valid join code or invite link; the CLI only creates the first platform admin.
- US-20 (REST API) and US-21 (Jira/Confluence/GitHub) remain deferred for the same reason — they depend on a more complete auth/integration story than JWT-only supports.

---

## ADR-08 to ADR-13: Implementation Decisions (Sprint 0–1)

Recorded in `system-design.md` §11; summarised here so the log is complete.

| # | Decision | Why |
|---|---|---|
| ADR-08 | Modular monolith with one image run as API and worker | Fits team size and timeline; module boundaries keep a later split cheap |
| ADR-09 | Services own transactions; routes are thin; `get_db` never commits | A failed request cannot leave partial writes; business rules live in one testable layer |
| ADR-10 | Enums as `VARCHAR` + `CHECK` | The taxonomy may evolve; `CHECK`s migrate cleanly, native enums do not |
| ADR-11 | Two-phase file storage, storage keys not paths, a body-size guard before parsing | No orphan files, no traversal, and no gigabyte writes before a size check |
| ADR-12 | Cross-workspace access returns 404 | Does not reveal that another tenant's row exists |
| ADR-13 | Worker tasks are idempotent and claim-based | Required by `acks_late`; makes duplicate delivery and crash recovery safe |

## ADR-14 to ADR-29: Extended-Scope Decisions (Step 7, proposed)

| # | Decision | Why | Consequence | Status |
|---|---|---|---|---|
| **ADR-14** | Tenancy: Workspace → Project → Channel, with a **Membership** table | Multi-workspace membership | Sprint 0 migration | Workspace → Project and `memberships` implemented in `0004`; channels ⬜ |
| **ADR-15** | Real-time: WebSocket in the API process, fan-out via **Redis pub/sub**, REST the only write path | One validated write path | No sticky sessions | Proposed |
| **ADR-16** | **Incremental analysis runs** per new or changed requirement | Live feedback at bounded cost | `analysis_runs` table | Proposed |
| **ADR-17** | Requirements change **only through change requests**; risk level is **rule-based** | Trust, DR-04 | Risk rules tested by a case table | Proposed |
| **ADR-18** | Notifications are rows plus a WebSocket push | No mail service needed | Email deferred | Proposed |
| **ADR-19** | Chat detection is **opt-in per project** | Privacy, cost | Off by default | Proposed |
| **ADR-20** | **Permission-based RBAC**: code checks permissions; roles are named permission sets, seeded with 9 defaults; project-level role override | "Many roles" without code changes | `roles`, `role_permissions` tables; tests iterate the permission catalogue | Implemented in `0004` (`roles`, `role_permissions`, `require_permission`) |
| **ADR-21** | **Graph deltas**: the server derives `graph.delta` events (nodes and edges added, changed, removed) from committed data; the client keeps a graph store; node positions are persisted per project so the layout stays stable | Live map without re-analysis or a jumping layout | Graph API `GET /projects/{p}/graph?revision=` plus delta events | Proposed |
| **ADR-22** | **GitHub-style collaboration objects**: Issue and Change Request (with base version, reviews, checks, merge) are first-class entities | Familiar workflow; clean two-owner handling | `issues`, `change_requests.base_version`, `reviews`, `review_comments` | Proposed |
| **ADR-23** | **EARS templates and a deterministic lint** in the composer; the LLM is used only for pre-flight and wording suggestions | Better requirements at the source; no cost per keystroke | Pattern catalogue shared by the lint and DR-07 | Proposed |
| **ADR-24** | **Suggestions as a separate asynchronous step** after a finding is stored, with a `suggestions` and `suggestion_feedback` store; prompts include up to 5 recent accepted or edited examples from the same project; **change sentences are templated from graph deltas**, and only the optional summary paragraph uses the LLM | Findings never wait for suggestions; feedback improves results without fine-tuning; written changes are exact and free | Two tables and a `SuggestionService`; NFR-36 measured | Proposed |
| **ADR-25** | **One finding model, three sources**: `findings.source` = ai, rule or person; one review workflow, one issue model | Human concerns and rule hits are first-class; AI misses become measurable | `source`, `raised_by`, `external_ref`, `rule_id` columns | Proposed |
| **ADR-26** | **Decision rules engine**: rules per project keyed on category, label, group, type, protected; most specific wins; the merge transaction checks the decision owner's approval on the current proposal revision | Explicit authority; no voting; no stale approvals | `decision_rules` table; `proposal_revision` on change requests and reviews | Proposed |
| **ADR-27** | **Rule-based cross-checks outside the similarity filter** on extracted attributes (entity, metric, value, unit, comparison, actor, condition, negation, modality), indexed by entity and metric | Catches differently worded conflicts deterministically and cheaply | `requirement_attributes` table; one rule module per check | Proposed |
| **ADR-28** | **Versioned project context and a context-pack builder** shared by every LLM call: `project_contexts` (one row per version) and `ContextPackBuilder` that selects brief summary, actors, matched glossary terms and top-3 SRS sections by embedding similarity under a token cap | Correct classification needs the product's context; one builder keeps prompts consistent and cost bounded | `project_contexts` table, `projects.status`, `context_version` on findings and suggestions | Partly implemented: `projects.status` (`0004`), `project_contexts`, `document_sections`, `findings.context_version` (`0011`); `ContextPackBuilder` ⬜ |
| **ADR-29** | **Updated SRS as a stored, sectioned document**: `srs_documents` and `srs_sections`; requirement sections are rendered by the system from baseline items, narrative sections by the LLM one call per section; a `FidelityChecker` gates publishing | Keeps the LLM away from requirement text; section review and regeneration are cheap | Migration `0012_srs_documents`; export reads the published version | Proposed |

**Risk-level rule (ADR-17, tune at CP2):** **High** if any new High-severity Conflicting finding, a protected requirement affected, or more than 10 requirements affected; **Medium** if any Medium-severity finding or 3 to 10 affected; **Low** otherwise.

---

## Open Decision: Advanced ML/DL Depth

Not yet an ADR because the team has not committed to it. The current architecture (embedding pre-filter + LLM classification) is solid engineering but light on "real" ML/DL — a general AI agent could largely approximate this by uploading documents directly to an LLM.

Recommended next step (pending team decision, gap D6): fine-tune a domain-specific Sentence-Transformer embedding model on labeled requirement pairs. This upgrades the embeddings owner's (Heet's) scope rather than adding a new role. It is listed as extension 6 in [`IT314_RCD_Scope_Extension_v5.md` §12](../planning/v5/IT314_RCD_Scope_Extension_v5.md#12-extensions-after-this-semester). The structured-slot extractor once listed as a stretch goal is now in scope as the attribute extraction behind rule-based cross-checks (US-58, ADR-27).

**Explicitly advised against for this semester:** a GNN for impact prediction (insufficient labeled data), fine-tuning a custom LLM from scratch, RLHF, and multimodal support — all flagged as scope-creep risks for a 14-week timeline.
