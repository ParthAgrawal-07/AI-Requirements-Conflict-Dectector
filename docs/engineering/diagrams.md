# UML Diagrams

**Class, Sequence, State & Activity Diagrams (Design Stage)**

> Status: Design diagrams — no code exists yet; these describe planned structure.
> These render natively as diagrams in GitHub's markdown viewer (Mermaid fenced code blocks) — no extra tooling needed.

A hand-drawn activity diagram for the core pipeline workflow was submitted with Lab 6 as a separate photograph. Diagram 4 below is a typed Mermaid re-expression of that same workflow for repo documentation purposes.

---

## 1. Class Diagram — Core Data Model

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

```mermaid
sequenceDiagram
  actor Analyst
  participant API as FastAPI
  participant Queue as Celery/Redis
  participant Ingest as Ingestion Module
  participant Embed as Embedding Module
  participant LLM as Classification Module
  participant DB as Postgres/pgvector

  Analyst->>API: POST /documents (upload)
  API->>DB: create Document (status=queued)
  API->>Queue: enqueue analyze_document job
  API-->>Analyst: 202 Accepted (document_id)
  Queue->>Ingest: extract & segment requirements
  Ingest->>DB: persist Requirement rows
  Queue->>Embed: generate embeddings
  Embed->>DB: store vectors (pgvector)
  Embed->>DB: rank candidate pairs by similarity
  Queue->>LLM: classify candidate pairs
  LLM->>DB: persist Finding (category, confidence, rationale)
  API-->>Analyst: GET /documents/:id/findings (poll or push)
```

## 3. State Diagram — Finding Lifecycle

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

## 4. Activity Diagram — Conflict-Detection Pipeline

Typed re-expression of the Lab 6 hand-drawn diagram: upload → validate → extract/segment → embed → rank candidates → threshold check → protected-requirement check → LLM classify → validate output/retry → persist finding → clarification/graph/audit trail → shown to analyst.

```mermaid
flowchart TD
  A[Upload document] --> B{Valid format & size?}
  B -- No --> B1[Reject with error]
  B -- Yes --> C[Extract & segment requirements]
  C --> D[Generate embeddings]
  D --> E[Rank candidate pairs by similarity]
  E --> F{Above similarity threshold?}
  F -- No --> G[Discard pair, no LLM call]
  F -- Yes --> H{Protected requirement involved?}
  H -- Yes --> H1[Route to mandatory manual review]
  H -- No --> I[LLM classification: 5 categories]
  I --> J{Schema-valid output?}
  J -- No --> J1[Retry up to 3x, then flag failure]
  J -- Yes --> K[Persist finding + confidence + rationale]
  K --> L[Generate clarification question if flagged]
  K --> M[Update dependency/conflict graph]
  K --> N[Write audit-trail entry]
  L --> O[Shown to analyst on dashboard]
  M --> O
  N --> O
```
