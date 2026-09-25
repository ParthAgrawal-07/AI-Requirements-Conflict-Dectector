# Architecture Decision Records

**7 ADRs — LLM Gateway, pgvector, and Key Trade-offs**

> Status: Planning-stage decisions — recorded before implementation begins

---

## ADR-01: Embedding Pre-Filter Before LLM Classification

**Status:** Accepted

**Context:** Cross-checking every requirement pair for conflicts is an O(n²) problem. A ~200-requirement SRS has ~20,000 candidate pairs; running every pair through an LLM is slow and expensive.

**Decision:** Generate a Sentence-Transformers embedding per requirement, store it in pgvector, and only send pairs above a configurable similarity threshold to the LLM classifier.

**Consequences**
- Expected to cut LLM calls by 70%+ versus brute-force all-pairs comparison (NFR-05).
- Encoded as a domain rule too (DR-10): similarity is a filter, not itself proof of conflict or duplication — a true conflict can exist between dissimilar-sounding requirements, which this pre-filter may miss.
- The similarity threshold must be tunable without a code change (FR-10, US-06) since an over-tight threshold silently drops true conflicts.

## ADR-02: 5-Category Issue Taxonomy (Adding "Incomplete")

**Status:** Accepted

**Context:** Seven independent team drafts of the requirements were merged. Three drafts used a 4-category taxonomy (Conflicting, Duplicate, Ambiguous, Dependent); one draft plus the official project brief text explicitly included a 5th category, Incomplete.

**Decision:** 5 categories were adopted as authoritative: Conflicting, Duplicate, Ambiguous, Incomplete, Dependent.

**Consequences**
- The Lab 6 submission's DR-01 still states the 4-category framing and has not yet been corrected — tracked as an open item in `requirements-spec.md`.
- Classification stories that some drafts split into 3–4 separate stories were merged into a single epic (US-05) to match how the pipeline actually executes.

## ADR-03: PostgreSQL + pgvector Over a Dedicated Vector DB

**Status:** Accepted

**Context:** Vector similarity search is needed for the embedding pre-filter, but the system also needs standard relational data (documents, requirements, findings, audit logs) with strong consistency guarantees.

**Decision:** Use PostgreSQL with the pgvector extension rather than a separate dedicated vector database (e.g., Pinecone, Weaviate).

**Consequences**
- One database to operate, back up, and reason about transactionally — simpler for a 7-person, one-semester team.
- pgvector indexing (IVFFlat/HNSW) is less specialized than a purpose-built vector DB; acceptable at the semester's expected data scale.

## ADR-04: Async Job Queue (Celery + Redis) for the Analysis Pipeline

**Status:** Accepted

**Context:** Full-document analysis (extraction → embedding → classification) can take minutes for a large SRS and must not block the upload request.

**Decision:** Run the pipeline as a Celery task backed by Redis; the API returns immediately with a document ID and status, and the frontend polls/subscribes for progress (US-03).

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
- Keeps auth scope inside one sprint (Sprint 2) rather than expanding into an enterprise-identity integration project.
- US-20 (REST API) and US-21 (Jira/Confluence/GitHub) remain deferred for the same reason — they depend on a more complete auth/integration story than JWT-only supports.

---

## Open Decision: Advanced ML/DL Depth

Not yet an ADR because the team has not committed to it. The current architecture (embedding pre-filter + LLM classification) is solid engineering but light on "real" ML/DL — a general AI agent could largely approximate this by uploading documents directly to an LLM.

Recommended next step (pending team decision): fine-tune a domain-specific Sentence-Transformer embedding model on labeled requirement pairs. This upgrades Role 2's existing scope rather than adding a new role. A custom NER/structured-slot extractor for catching quantitative conflicts (e.g., "30 days" vs. "90 days") is an optional stretch goal on top of that.

**Explicitly advised against for this semester:** a GNN for impact prediction (insufficient labeled data), fine-tuning a custom LLM from scratch, RLHF, and multimodal support — all flagged as scope-creep risks for a 14-week timeline.
