# UML Diagrams

**Class, Sequence, State & Activity Diagrams**

> Status: Diagrams 1–3 are the original design-stage diagrams; the implemented domain model is in `object-design.md` §2, which supersedes Diagram 1. Diagrams 4–6 reflect the revision 5 scope ([`IT314_RCD_Design_Update_v5.md`](../planning/v5/IT314_RCD_Design_Update_v5.md) §7, §12).
> These render natively as diagrams in GitHub's markdown viewer (Mermaid fenced code blocks) — no extra tooling needed.

A hand-drawn activity diagram for the core pipeline workflow was submitted with Lab 6 as a separate photograph. Diagram 4 below is a typed Mermaid re-expression of that same workflow for repo documentation purposes.

---

## 1. Class Diagram — Core Data Model (original, superseded)

*Superseded by `object-design.md` §2: requirements now belong to a workspace and a project, findings to a project and an analysis run (SX-09), and roles are permission sets (ADR-20).*

```mermaid
classDiagram
  class Document {
    +uuid id
    +string filename
    +string format
    +string status
    +datetime uploaded_at
  }
  class Requirement {
    +uuid id
    +string source_req_id
    +text body
    +string stakeholder_group
    +int version
  }
  class Embedding {
    +uuid id
    +uuid requirement_id
    +vector_384 embedding
  }
  class CandidatePair {
    +uuid id
    +uuid requirement_a_id
    +uuid requirement_b_id
    +float similarity_score
  }
  class Finding {
    +uuid id
    +string category
    +float confidence
    +text rationale
    +string status
  }
  class Clarification {
    +uuid id
    +uuid finding_id
    +text question
    +text resolution
  }
  class AuditLogEntry {
    +uuid id
    +string actor
    +string action
    +datetime at
  }
  Document "1" --> "many" Requirement
  Requirement "1" --> "1" Embedding
  Requirement "1" --> "many" CandidatePair
  CandidatePair "1" --> "many" Finding
  Finding "1" --> "0..1" Clarification
  Finding "1" --> "many" AuditLogEntry
```

## 2. Sequence Diagram — Upload to Classification

*Updated for projects: the upload goes to `POST /projects/{p}/documents`, and classification starts only once the project is `active` (FR-103).*

```mermaid
sequenceDiagram
  actor Analyst
  participant API as FastAPI
  participant Queue as Celery/Redis
  participant Ingest as Ingestion Module
  participant Embed as Embedding Module
  participant LLM as Classification Module
  participant DB as Postgres/pgvector

  Analyst->>API: POST /projects/{p}/documents (upload)
  API->>DB: create Document (status=queued)
  API->>Queue: enqueue analyze_document job
  API-->>Analyst: 202 Accepted (document_id)
  Queue->>Ingest: extract & segment requirements
  Ingest->>DB: persist Requirement rows
  Queue->>Embed: generate embeddings
  Embed->>DB: store vectors (pgvector)
  Embed->>DB: rank candidate pairs by similarity
  Note over Queue,LLM: only if project.status = active (ContextGate)
  Queue->>LLM: classify candidate pairs (+ context pack)
  LLM->>DB: persist Finding (category, confidence, rationale)
  API-->>Analyst: findings via REST, pushed as WebSocket events (ADR-15)
```

## 3. State Diagram — Finding Lifecycle (original)

*The finding lifecycle for the extended scope (AI, Rule and Person sources; issues separate from findings, SX-18) is designed in `object-design.md` §5.2.*

```mermaid
stateDiagram-v2
  [*] --> Flagged: LLM classification
  Flagged --> UnderReview: analyst opens finding
  UnderReview --> Confirmed: analyst confirms issue
  UnderReview --> Dismissed: analyst marks false positive
  UnderReview --> Merged: analyst merges duplicate pair
  UnderReview --> Reclassified: analyst changes category
  Confirmed --> ClarificationRequested: FR-22 auto-generates question
  ClarificationRequested --> Resolved: analyst attaches resolution (FR-23)
  Dismissed --> [*]
  Merged --> [*]
  Resolved --> [*]
  note right of UnderReview
    Protected requirements (DR-05) skip
    auto-merge and require manual review
  end note
```

## 4. Activity Diagram — Conflict-Detection Pipeline (revision 5)

Re-expression of the Lab 6 hand-drawn diagram, extended with the context gate (FR-103), rule-based cross-checks (FR-101), the context pack (FR-105) and the live map (FR-84).

```mermaid
flowchart TD
  A[Upload document into a project] --> B{Valid format & size?}
  B -- No --> B1[Reject with error, nothing stored]
  B -- Yes --> C[Extract & segment requirements, keep printed IDs]
  C --> CG{Project context confirmed?}
  CG -- No --> CG1[Project stays in Setup; analysis waits for the PM to confirm the brief]
  CG -- Yes --> D[Generate embeddings]
  D --> E[Rank candidate pairs by similarity]
  D --> R[Rule-based cross-checks on extracted attributes]
  E --> F{Above similarity threshold?}
  F -- No --> G[No LLM call for this pair]
  F -- Yes --> I[LLM classification: 5 categories + context pack]
  I --> J{Schema-valid output?}
  J -- No --> J1[Retry up to 3x, then record failure]
  J -- Yes --> K[Persist finding: source, confidence, severity, context_version]
  R --> K
  K --> H{Protected requirement involved?}
  H -- Yes --> H1[Never auto-resolved; compliance sign-off required]
  H -- No --> L
  H1 --> L[Clarification question; AI suggestions async]
  K --> M[Graph delta: live map + written change log]
  K --> N[Audit entry: IDs and actions only]
  L --> O[Shown on findings, map, issues]
  M --> O
  N --> O
```

## 5. State Diagram — Requirement Lifecycle (revision 5)

From [`IT314_RCD_Design_Update_v5.md` §7.1](../planning/v5/IT314_RCD_Design_Update_v5.md#71-requirement-lifecycle). Only Approved and Implemented requirements form the baseline (DR-13); after approval, text changes only through a change request (DR-14).

```mermaid
stateDiagram-v2
  [*] --> Proposed : requirement post, or import as proposals
  [*] --> Approved : import as baseline (baseline.manage)
  Proposed --> Under_Review : analyst starts review
  Under_Review --> Approved : approval policy satisfied
  Under_Review --> Rejected : rejected with rationale
  Proposed --> Rejected : withdrawn by author
  Approved --> Approved : approved change request creates version n+1
  Approved --> Implemented : linked work done (manual)
  Approved --> Deprecated : approved deprecation request
  Implemented --> Deprecated : approved deprecation request
  Rejected --> [*]
  Deprecated --> [*]
```

## 6. State Diagram — Change Request Lifecycle (revision 5)

From [`IT314_RCD_Design_Update_v5.md` §7.2](../planning/v5/IT314_RCD_Design_Update_v5.md#72-change-request-lifecycle-rev-2-pull-request-style). Checks are a property of the open request, not a state; merge re-verifies the agreement rules in one transaction (FR-98).

```mermaid
stateDiagram-v2
  [*] --> draft
  draft --> open : submitted, checks start, reviewers requested
  open --> open : review, comment, checks re-run after update
  open --> needs_update : requirement moved past base version, or checks stale
  needs_update --> open : proposer updates, checks re-run
  open --> approved : review policy satisfied, no outstanding request-changes
  approved --> open : new request-changes, or update by proposer
  approved --> needs_update : competing merge
  approved --> merged : merge by a member with rcr.merge
  open --> closed : closed without merge (rejected)
  draft --> withdrawn
  open --> withdrawn : by proposer
  merged --> [*]
  closed --> [*]
  withdrawn --> [*]
```
