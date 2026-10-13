# Clarification Questions & Change-Impact Analysis Design Document (Sprint 0)

**Role 4 — Clarification & Impact Analysis**  
**Author:** Madhav Bhatt  
**Traces to:** US-09, US-11, US-12 · FR-17, FR-22, FR-23, FR-24, FR-25, FR-26, FR-27 · DR-04, DR-05, DR-08 · NFR-15, NFR-17, NFR-21  
**Status:** Sprint 0 Deliverable (Design & Data Modeling Specification)  

---

## 1. Executive Summary & Purpose

In the **AI Requirements Conflict Detector** platform, automated detection is only the first half of the value chain. Once potential ambiguities or contradictions are flagged, requirements engineers and QA teams must **resolve** them efficiently without endless cross-team meetings, and project managers must understand the **ripple effects** before any requirement text is modified.

This design document establishes the architectural foundation and data models for two core capabilities owned by Role 4:

1. **Clarification Question Workflow (US-09 / FR-22, FR-23)**:
   Automatically formulates precise, domain-grounded questions for findings classified as **Ambiguous** or **Conflicting**. Questions are framed so that a business analyst (BA) or QA engineer can review, answer, and attach resolution text directly within the platform.
2. **Change-Impact Analysis Engine (US-11 / FR-24, FR-25, FR-26)**:
   Analyzes the dependency and conflict graph whenever a requirement is edited or proposed for modification. It computes both direct and transitive impacts, distinguishes **potential** impacts (AI-inferred) from **confirmed** impacts (human-verified), handles cycles safely, and maintains an immutable version history for full traceability.

---

## 2. Requirements & Domain Context

### 2.1 Traceability Matrix

The table below traces this module to the official project requirements. Exact wording is transcribed directly from [`docs/engineering/requirements-spec.md`](engineering/requirements-spec.md) and [`docs/engineering/feature-deep-dive.md`](engineering/feature-deep-dive.md):

| Requirement ID | Type | Source Requirement Wording | Owning Task |
|---|---|---|---|
| **US-09** | User Story | *As a QA Engineer, I want a clarification question generated for every Ambiguous or Conflicting finding, so that I can resolve the issue without further discussion.* | T25, T26 (Sprint 3) |
| **US-11** | User Story | *As a Project Manager, I want to see everything a requirement edit might affect before I save it, so that I don't introduce a new conflict without realizing it.* | T31, T32 (Sprint 3) |
| **US-12** | User Story | *As a Software Architect, I want a version history maintained for every requirement, so that I can compare changes and audit past edits.* | T34 (Sprint 3) |
| **FR-17** | Functional | The system shall allow authorized users to define and adjust the criteria that qualify two requirements as "dependent" on one another. | T19, T31 |
| **FR-22** | Functional | For every requirement flagged as Ambiguous or Conflicting, the system shall generate a clarification question sufficient for a QA engineer to resolve the issue without further discussion. | T25 |
| **FR-23** | Functional | The system shall allow a user to mark a clarification question as answered and attach the resolution text. | T26 |
| **FR-24** | Functional | Whenever a requirement is modified, the system shall perform a change-impact analysis identifying all requirements, related design elements, or test cases affected. | T31 |
| **FR-25** | Functional | The system shall present the list of potentially impacted requirements before a proposed change is saved. | T32 |
| **FR-26** | Functional | The system shall maintain a version history for every requirement, including prior text, edits, and resolution status, to support change comparison and audit. | T34 |
| **FR-27** | Functional | The system shall display a summary dashboard showing counts of flagged issues by type (Conflict / Duplicate / Ambiguous / Dependent). | T36 |
| **DR-04** | Domain Rule | The system shall not silently delete, merge, or alter a requirement's original text; any suggested resolution must be presented for human approval — automated tools assist but do not replace human sign-off. | Core Architecture |
| **DR-05** | Domain Rule | Requirements explicitly marked compliance-critical or regulatory (e.g., HIPAA, GDPR) shall be exempt from automatic duplicate-removal suggestions and routed to mandatory manual review instead. | Core Architecture |
| **DR-08** | Domain Rule | The system shall maintain a full change history for every requirement, consistent with configuration-management practice, so any resolved conflict can be audited later. | Data Layer |
| **NFR-15** | Non-Functional | Clarification questions and flag explanations shall be understandable to a QA engineer or BA without needing to know the underlying AI/NLP model. | Prompt / LLM |
| **NFR-17** | Non-Functional | Every AI-generated finding shall carry evidence/rationale and be clearly distinguishable from human-authored/approved information. | Core Architecture |
| **NFR-21** | Non-Functional | False-positive rate for conflict/duplicate detection shall remain below an agreed threshold, validated against a labeled benchmark set (precision/recall/F1). | Testing / Evaluation |

---

## 3. Clarification-Question Data Model (US-09)

### 3.1 Problem Analysis & Cardinality Proposal (1:1 vs. 1:N)

In the initial Sprint 0 schema ([`backend/app/models/analysis.py`](../backend/app/models/analysis.py#L111-L127)), a baseline `Clarification` model was drafted with a unique foreign key:
```python
finding_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("findings.id", ondelete="CASCADE"), unique=True)
```

#### Cardinality Trade-off & Proposal
- **Existing 1:1 Schema (`unique=True`)**:
  - *Limitation*: When a complex conflict involves multiple conflicting parameters (e.g. latency vs throughput tradeoffs) or a requirement contains multiple ambiguous phrases (e.g. "fast response" and "user-friendly"), a single prompt-generated question is frequently insufficient to fully resolve the issue.
- **Proposed 1:N Design (Finding $\rightarrow$ Clarifications)**:
  - Relaxing the `unique=True` constraint on `finding_id` and adding an `order_index` allows a finding to host **multiple targeted questions** where appropriate (e.g. Question 1 addressing threshold values, Question 2 addressing fallback modes).
  - For single questions, $N=1$ behaves identically to a 1:1 relation, making this design backwards-compatible.

> [!IMPORTANT]
> **Status: Proposal Pending Backend / DB Lead Approval (Parth Agrawal)**  
> The 1:N model is presented as a design proposal. Adopting this change requires coordination across shared artifacts before implementation:
> 1. **ORM Model** ([`backend/app/models/analysis.py`](../backend/app/models/analysis.py)): Update `Finding.clarification` from scalar to `Finding.clarifications: Mapped[list[Clarification]] = relationship(back_populates="finding", passive_deletes=True)`.
> 2. **Alembic Migration** ([`backend/alembic/versions/20260928_0001_initial_schema.py`](../backend/alembic/versions/20260928_0001_initial_schema.py)): A new migration must drop `uq_clarifications_finding_id` and add `uq_clarifications_finding_id_order_index`.
> 3. **Documentation & Diagrams**: Update ER diagram in [`docs/engineering/data-model.md`](engineering/data-model.md) from `1:0..1` to `1:N`, and the class diagram in [`docs/engineering/diagrams.md`](engineering/diagrams.md).
> 4. **API Contract** ([`docs/engineering/api-reference.md`](engineering/api-reference.md)): Update `GET /api/v1/findings/{id}/clarification` response contract to return a list `{ "clarifications": [...] }`.
> 5. **Missing Resolution Endpoint (FR-23)**: Currently, `api-reference.md` defines no endpoint for answering a clarification question. We propose adding `PATCH /api/v1/clarifications/{id}` (or `PATCH /api/v1/findings/{id}/clarifications/{cid}`) accepting `{ "resolution": "..." }` to record the human resolution and mark the question answered.
>
> **No shared models or migrations have been modified in Sprint 0.** These changes await Parth's review and sign-off.

### 3.2 Question Lifecycle & State Machine

```mermaid
stateDiagram-v2
    [*] --> PENDING: LLM generates question (FR-22)
    PENDING --> ANSWERED: Analyst / QA attaches resolution (FR-23)
    PENDING --> DISMISSED: Analyst marks question unnecessary
    PENDING --> SUPERSEDED: Requirement text edited before answer
    ANSWERED --> [*]
    DISMISSED --> [*]
    SUPERSEDED --> [*]
```

- **`PENDING`**: Initial state upon generation. Awaiting stakeholder review.
- **`ANSWERED`**: Resolution text provided. Triggers optional requirement update draft.
- **`DISMISSED`**: Finding was deemed acceptable or false positive; question dismissed without altering requirement text.
- **`SUPERSEDED`**: The underlying requirement was modified elsewhere before an answer was attached, rendering this question obsolete.

### 3.3 Database Schema: Proposed `clarifications` Table

Following the conventions established in [`backend/app/models/base.py`](../backend/app/models/base.py), new domain enums belong in [`backend/app/models/enums.py`](../backend/app/models/enums.py):

```python
"""Proposed additions to app.models.enums and app.models.analysis."""

from enum import StrEnum
import uuid
from datetime import datetime
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin, enum_column


# Proposed addition to app.models.enums
class ClarificationStatus(StrEnum):
    """Lifecycle status of a clarification question."""
    PENDING = "pending"
    ANSWERED = "answered"
    DISMISSED = "dismissed"
    SUPERSEDED = "superseded"


# Proposed refinement to app.models.analysis.Clarification
class Clarification(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A clarification question generated for a finding (FR-22, FR-23)."""

    __tablename__ = "clarifications"
    __table_args__ = (
        UniqueConstraint(
            "finding_id", "order_index",
            name="uq_clarifications_finding_id_order_index"
        ),
        Index("ix_clarifications_status", "status"),
    )

    finding_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("findings.id", ondelete="CASCADE"), nullable=False
    )
    
    # 0-based sequence for multiple questions per finding
    order_index: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    
    # The natural-language question generated for QA/BA (NFR-15)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Optional structured choices / suggestions proposed by LLM to accelerate review
    suggested_options: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    
    # Lifecycle state
    status: Mapped[ClarificationStatus] = mapped_column(
        enum_column(ClarificationStatus, "clarification_status"),
        default=ClarificationStatus.PENDING,
        server_default=ClarificationStatus.PENDING.value,
        nullable=False,
    )
    
    # Human resolution text attached per FR-23
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    finding: Mapped["Finding"] = relationship(back_populates="clarifications")
    resolver: Mapped["User | None"] = relationship(foreign_keys=[resolved_by])
```

### 3.4 Pydantic Schemas for Clarification API (Role 4 Contract)

These schemas will live in `backend/app/schemas/clarification.py`, adhering to Pydantic v2 `ConfigDict` and domain enum typing:

```python
from datetime import datetime
import uuid
from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import FindingCategory
from app.models.enums import ClarificationStatus  # proposed domain enum


class ClarificationBase(BaseModel):
    question: str
    suggested_options: list[str] | None = None
    order_index: int = 0


class ClarificationCreate(ClarificationBase):
    finding_id: uuid.UUID


class ClarificationResolutionSubmit(BaseModel):
    """Payload when a QA/BA answers a clarification question (FR-23)."""
    resolution: str = Field(..., min_length=3, description="Resolution text to attach")


class ClarificationResponse(ClarificationBase):
    id: uuid.UUID
    finding_id: uuid.UUID
    status: ClarificationStatus
    resolution: str | None = None
    resolved_by: uuid.UUID | None = None
    resolved_at: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FindingClarificationDetail(BaseModel):
    """Aggregate payload returned when inspecting a finding's clarifications."""
    finding_id: uuid.UUID
    category: FindingCategory
    rationale: str
    involved_requirement_ids: list[str]
    clarifications: list[ClarificationResponse]

    model_config = ConfigDict(from_attributes=True)
```

---

## 4. Change-Impact Analysis Data Model (US-11)

### 4.1 Relationship Semantics: Directed Impact Graph

Change-impact analysis evaluates: *"If Requirement $R_{source}$ is edited, which other requirements $R_{target}$ are affected, why, and how severely?"*

In requirements engineering, impact relationships are **directed** ($R_A \rightarrow R_B$):
- If $R_A$ depends on $R_B$ ("Payment processing requires Validated User Session"), modifying $R_B$ directly impacts $R_A$.
- If $R_A$ and $R_B$ are in conflict ("$R_A$: 2s timeout", "$R_B$: 10s timeout"), modifying $R_A$ impacts $R_B$'s conflict status.

```mermaid
flowchart LR
    subgraph Direct Impact
        R1[Edited Requirement: REQ-014] -->|CONFLICT_PARTNER| R2[REQ-041: Session Timeout]
        R1 -->|DEPENDENCY| R3[REQ-022: Auth Gateway]
    end
    subgraph Transitive Impact
        R3 -->|DEPENDENCY| R4[REQ-055: Single Sign-On]
    end
```

### 4.2 Relationship Taxonomy & Classification

Impact links are categorized into distinct relationship types:

| Relationship Type | Description | Origin | Default Severity |
|---|---|---|---|
| `DIRECT_DEPENDENCY` | $R_{target}$ functionally depends on $R_{source}$ (`FR-17`, `FindingCategory.DEPENDENT`). | Finding or explicit link | `Severity.HIGH` |
| `CONFLICT_PARTNER` | $R_{target}$ contradicts $R_{source}$ (`FindingCategory.CONFLICTING`). Editing one can resolve or worsen the conflict. | Finding | `Severity.HIGH` |
| `SEMANTIC_SIMILARITY` | High cosine similarity via vector store (`pgvector`). Changes in terminology or scope may cause semantic drift. | CandidatePair / Vector pre-filter | `Severity.MEDIUM` |
| `DUPLICATE_OVERLAP` | $R_{target}$ is an identified duplicate (`FindingCategory.DUPLICATE`). Changes must be mirrored or consolidated. | Finding | `Severity.MEDIUM` |
| `SHARED_CONSTRAINT` | Requirements share regulatory/compliance constraints (e.g. HIPAA/GDPR `is_protected = True`). | Domain rule `DR-05` | `Severity.CRITICAL` |

### 4.3 Distinguishing Potential vs. Confirmed Impacts

To build trust (NFR-17, NFR-21), the system must never conflate AI guesses with confirmed facts:
1. **`POTENTIAL` (Inferred Impact)**:
   - Derived from unreviewed AI findings or raw vector similarity above threshold.
   - Tagged as *"Potential impact — based on embedding similarity (score: 0.82)"* or *"Potential impact — unreviewed conflict finding"*.
2. **`CONFIRMED` (Verified Impact)**:
   - Derived from human-confirmed findings (`FindingStatus.CONFIRMED`), explicit dependencies, or compliance tags.
   - High-confidence flag alerting the project manager to mandatory review.

### 4.4 Data Model Options: Persisted Table vs. Dynamic Inferred Graph

Role 4 evaluates two architectural implementation options:

#### Option A: Dedicated Persisted Table (`requirement_impact_links`)
Stores explicit graph edges in PostgreSQL.
- **Pros**: Direct SQL queries, easy to index, enables manual analyst-defined dependency links.
- **Cons**: Requires additional synchronization when findings or embeddings change; introduces extra table maintenance.

#### Option B: Dynamic Graph Query over Existing Tables (`CandidatePair` + `Finding`)
Computes the impact graph dynamically on-demand from existing records.
- **Pros**: Zero data duplication. No synchronization lag. Reuses Parth and Keval's existing tables directly.
- **Cons**: Graph traversal executed in Python memory or recursive Common Table Expressions (CTE).

#### Recommendation: Hybrid Strategy
- **Sprint 0 / Sprint 3 MVP**: Implement **Option B** (Dynamic Graph Engine in `impact_analysis.py`) exposed via Pydantic response models.
- **Sprint 4+ Extension**: Introduce **Option A** (`requirement_impact_links` table, detailed below) if explicit manual dependency linking (FR-17) or persistent edge caching is required.

### 4.5 Schema: `requirement_impact_links` (for Persisted Option)

Reusing the existing [`Severity`](../backend/app/models/enums.py#L48) enum rather than creating a duplicate enum:

```python
"""Proposed schema for explicit impact links (Sprint 4+ extension)."""

from enum import StrEnum
import uuid
from datetime import datetime
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin, enum_column
from app.models.enums import Severity


# Proposed additions to app.models.enums
class ImpactType(StrEnum):
    DIRECT_DEPENDENCY = "direct_dependency"
    CONFLICT_PARTNER = "conflict_partner"
    SEMANTIC_SIMILARITY = "semantic_similarity"
    DUPLICATE_OVERLAP = "duplicate_overlap"
    SHARED_CONSTRAINT = "shared_constraint"


class ImpactStatus(StrEnum):
    POTENTIAL = "potential"      # Heuristic / AI predicted
    CONFIRMED = "confirmed"      # Human verified / domain confirmed


class RequirementImpactLink(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A directed impact link between two requirements (FR-24, FR-25)."""

    __tablename__ = "requirement_impact_links"
    __table_args__ = (
        # Prevent duplicate identical links between the same pair
        UniqueConstraint(
            "source_requirement_id", "target_requirement_id", "link_type",
            name="uq_impact_link_source_target_type"
        ),
        # Self-loops prohibited: a requirement cannot impact itself directly
        CheckConstraint(
            "source_requirement_id != target_requirement_id",
            name="ck_impact_no_self_loop"
        ),
        CheckConstraint("confidence BETWEEN 0 AND 1", name="ck_impact_confidence_range"),
        Index("ix_impact_source_req", "source_requirement_id"),
        Index("ix_impact_target_req", "target_requirement_id"),
    )

    source_requirement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("requirements.id", ondelete="CASCADE"), nullable=False
    )
    target_requirement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("requirements.id", ondelete="CASCADE"), nullable=False
    )
    
    link_type: Mapped[ImpactType] = mapped_column(
        enum_column(ImpactType, "impact_link_type"), nullable=False
    )
    status: Mapped[ImpactStatus] = mapped_column(
        enum_column(ImpactStatus, "impact_link_status"),
        default=ImpactStatus.POTENTIAL,
        server_default=ImpactStatus.POTENTIAL.value,
        nullable=False,
    )
    # Reuses existing Severity enum (low, medium, high, critical)
    severity: Mapped[Severity] = mapped_column(
        enum_column(Severity, "impact_severity"),
        default=Severity.MEDIUM,
        server_default=Severity.MEDIUM.value,
        nullable=False,
    )
    
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Optional link back to the finding that triggered this link
    finding_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("findings.id", ondelete="SET NULL"), nullable=True
    )
    
    verified_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    source_requirement: Mapped["Requirement"] = relationship(
        foreign_keys=[source_requirement_id]
    )
    target_requirement: Mapped["Requirement"] = relationship(
        foreign_keys=[target_requirement_id]
    )
```

#### Canonical Ordering for Symmetric Links
To prevent symmetric relationships (`CONFLICT_PARTNER`, `DUPLICATE_OVERLAP`, `SEMANTIC_SIMILARITY`) from being stored twice as both $A \rightarrow B$ and $B \rightarrow A$:
- **Canonical Ordering Rule**: Consistent with [`CandidatePair.ordered()`](../backend/app/models/analysis.py#L57) (`requirement_a_id < requirement_b_id`), symmetric links are normalized such that `source_requirement_id < target_requirement_id`. Queries for requirement $X$ evaluate both directions: `(source_id = X OR target_id = X) AND link_type IN ('conflict_partner', 'duplicate_overlap', 'semantic_similarity')`.
- **Genuinely Directed Links**: `DIRECT_DEPENDENCY` ($A \text{ depends on } B$) is directional. The canonical ordering rule does NOT apply to `DIRECT_DEPENDENCY`, keeping directionality intact.

### 4.6 Handling Duplicate Links & Cyclic Relationships

1. **Duplicate Links**:
   - Guarded at the database level by `UniqueConstraint("source_requirement_id", "target_requirement_id", "link_type")`.
   - In dynamic traversal, edges are deduplicated via a Python set key: `(source_id, target_id, link_type)`.
2. **Cyclic Relationships & Diamond Graph Distinction**:
   - **Diamond Graphs are Valid DAGs**: In directed graphs, reaching a node $D$ via two distinct paths (such as $A \rightarrow B \rightarrow D$ and $A \rightarrow C \rightarrow D$) is a standard diamond topology and must **never** be flagged as a cycle.
   - **Cycle Definition**: A cycle exists if and only if a directed edge traverses back to an ancestor node that is currently on the active DFS recursion call stack (a true back-edge).
   - **Scope Limitation**: Cycle detection applies **strictly to directed `DIRECT_DEPENDENCY` edges**. Symmetric relationships (`CONFLICT_PARTNER`, `DUPLICATE_OVERLAP`, `SEMANTIC_SIMILARITY`) are non-directional mutual associations and must NOT be treated as cycle-forming edges.
   - **Traversal Algorithm**:
     - Three-state node tracking:
       - `UNVISITED` (white): Node not yet encountered.
       - `VISITING` (gray / active recursion stack): Node is on the active recursion path. An incoming directed dependency edge encountering a `VISITING` node indicates a circular dependency cycle.
       - `VISITED` (black): Node and all its descendants have been fully explored. Traversing into a `VISITED` node safely terminates branch expansion without flagging a cycle.
     - Traversal bound: `max_depth = 3`.
     - When a circular dependency is detected, `has_circular_dependency = True` is set and the cycle path (e.g. `["REQ-014", "REQ-022", "REQ-055", "REQ-014"]`) is returned in the API payload.

### 4.7 Integration with Requirement Versioning (FR-26)

When an analyst modifies a requirement after reviewing its impact:
1. `GET /api/v1/requirements/{id}/impact`: Analyst inspects impacted requirements.
2. `PATCH /api/v1/requirements/{id}`: Analyst confirms and submits updated text.
3. The backend:
   - Increments `Requirement.current_version`.
   - Inserts a new record into [`requirement_versions`](../backend/app/models/requirement.py#L64-L85) capturing `version_no`, `body_snapshot`, `changed_by`, and `changed_at`.
   - Invalidates or re-evaluates linked `POTENTIAL` impact links.

> [!NOTE]
> **Edit Rationale Schema Note (Sprint 3 Proposal)**:  
> The existing [`RequirementVersion`](../backend/app/models/requirement.py#L64-L85) model currently contains columns for `version_no`, `body_snapshot`, `changed_by`, and `changed_at`. It does **not** currently contain an edit rationale column. Persisting an analyst's change reason will require a database migration adding a nullable `change_reason: Mapped[str | None] = mapped_column(Text, nullable=True)` to `requirement_versions` (proposed for Sprint 3, Task T34).

### 4.8 Pydantic Schemas for Impact Analysis API

These schemas will live in `backend/app/schemas/impact.py`, using Pydantic v2 `ConfigDict` and typed domain enums:

```python
from datetime import datetime
import uuid
from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import Severity
from app.models.enums import ImpactType, ImpactStatus  # proposed domain enums


class ImpactItem(BaseModel):
    requirement_id: uuid.UUID
    source_req_id: str | None = None
    body_preview: str
    location: str | None = None
    relationship_type: ImpactType
    status: ImpactStatus
    severity: Severity
    reason: str
    depth: int = 1  # 1 = direct impact, 2+ = transitive impact
    is_protected: bool = False

    model_config = ConfigDict(from_attributes=True)


class ImpactAnalysisResult(BaseModel):
    """Response returned by GET /api/v1/requirements/{id}/impact."""
    source_requirement_id: uuid.UUID
    source_req_id: str | None = None
    source_version: int
    analyzed_at: datetime
    total_impacted_count: int
    has_circular_dependency: bool = False
    circular_dependency_path: list[str] | None = None
    critical_impacts_count: int
    impacted_requirements: list[ImpactItem]

    model_config = ConfigDict(from_attributes=True)
```

---

## 5. Concrete Record Examples

### 5.1 Clarification Record Example

```json
{
  "id": "7b8d4f6c-8e9a-4c2d-9b1e-3f5a7c9d1e2f",
  "finding_id": "c1a2b3c4-d5e6-4f7a-8b9c-0d1e2f3a4b5c",
  "order_index": 0,
  "question": "REQ-014 requires transaction timeout within 2 seconds, but REQ-041 states batch processing allows up to 10 seconds. Under what operational load should the 2-second timeout take precedence?",
  "suggested_options": [
    "Strict 2s timeout for interactive user sessions only; 10s for scheduled background batches.",
    "Global 2s timeout applies to all operations (REQ-041 to be revised).",
    "Configurable timeout per tenant."
  ],
  "status": "pending",
  "resolution": null,
  "resolved_by": null,
  "resolved_at": null,
  "created_at": "2026-10-12T16:30:00Z"
}
```

### 5.2 Impact Analysis Response Example

```json
{
  "source_requirement_id": "9a8b7c6d-5e4f-3a2b-1c0d-9e8f7a6b5c4d",
  "source_req_id": "REQ-014",
  "source_version": 2,
  "analyzed_at": "2026-10-12T16:35:00Z",
  "total_impacted_count": 2,
  "has_circular_dependency": false,
  "circular_dependency_path": null,
  "critical_impacts_count": 1,
  "impacted_requirements": [
    {
      "requirement_id": "1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d",
      "source_req_id": "REQ-041",
      "body_preview": "The system shall complete batch transaction processing within 10 seconds...",
      "location": "Page 14, Section 3.2",
      "relationship_type": "conflict_partner",
      "status": "confirmed",
      "severity": "high",
      "reason": "Direct timing conflict flagged in Finding #c1a2b3c4. Modifying REQ-014 timeout will alter this conflict status.",
      "depth": 1,
      "is_protected": false
    },
    {
      "requirement_id": "5f6e7d8c-9b0a-1c2d-3e4f-5a6b7c8d9e0f",
      "source_req_id": "REQ-098",
      "body_preview": "Audit logs for all patient health data transactions must be preserved in compliance with HIPAA...",
      "location": "Page 28, Section 5.1",
      "relationship_type": "shared_constraint",
      "status": "confirmed",
      "severity": "critical",
      "reason": "Compliance-critical requirement linked to transaction logging pipeline. Requires manual sign-off per DR-05.",
      "depth": 2,
      "is_protected": true
    }
  ]
}
```

---

## 6. Integration Requirements & Interfaces

| Partner Role / Component | Integration Point | Direction | Interface Contract |
|---|---|---|---|
| **Role 1 (Ingestion — Bansil)** | Requirements extraction | Upstream $\rightarrow$ Role 4 | `Requirement` table (`body`, `source_req_id`, `location`). |
| **Role 2 (Embeddings — Keval)** | Similarity retrieval | Upstream $\rightarrow$ Role 4 | Querying `CandidatePair` similarity scores for potential impact links. |
| **Role 3 (Classification — Heet)** | Classification results | Upstream $\rightarrow$ Role 4 | Ingesting `Finding` records where category is `Ambiguous` or `Conflicting`. |
| **Role 5 (Backend / DB — Parth)** | API Routes & Database | Bidirectional | `GET /findings/{id}/clarification` in `backend/app/api/findings.py`; `GET /requirements/{id}/impact` in `backend/app/api/requirements.py`; proposed `PATCH /clarifications/{id}` for FR-23. |
| **Role 6 & 7 (Frontend UI)** | Dashboard & React Flow | Role 4 $\rightarrow$ Downstream | Findings panel renders clarification Q&A; Pre-save modal renders impact warning graph. |

---

## 7. Decisions for Team Alignment (Parth, Keval, Heet)

The following design decisions are documented for team review prior to Sprint 3 development:

| # | Item | Options | Proposed Recommendation | Team Stakeholder |
|---|---|---|---|---|
| **D1** | **Clarification Cardinality** | (A) Strict 1:1 (`unique=True` on `finding_id`)<br>(B) 1:N (`unique` removed, `order_index` added) | **Option B (1:N)**: Enables generating multiple targeted questions for multi-clause conflicts. Marked as a proposal pending Parth's sign-off. | **Parth** (Role 5 Lead) |
| **D2** | **Impact Link Storage** | (A) Explicit `requirement_impact_links` table<br>(B) Dynamic traversal of `CandidatePair` + `Finding` | **Option B for Sprint 3 MVP**, with Option A as a documented schema upgrade if manual dependency editing is needed. | **Parth** (DB schema) |
| **D3** | **Clarification Status Enum** | (A) Infer from `resolution IS NOT NULL`<br>(B) Explicit `ClarificationStatus` enum (`pending`, `answered`, `dismissed`, `superseded`) | **Option B**: Provides clean database indexing and filtering for dashboard metrics (FR-27). | **Parth** (Enums) |
| **D4** | **Impact Pre-filter Threshold** | (A) Use default `SIMILARITY_THRESHOLD_DEFAULT` (0.75)<br>(B) Use relaxed threshold (e.g. 0.65) for transitive impacts | **Option B**: Allows catching subtle indirect dependencies that stricter conflict detection ignores. | **Keval** (Role 2) |
| **D5** | **Structured Clarification Output** | (A) Raw string from LLM<br>(B) JSON schema with `question` + `suggested_options` | **Option B**: Enables interactive radio/dropdown options in UI to accelerate human review. | **Heet** (Role 3 prompts) |
| **D6** | **Impact Graph Edge Styling** | (A) Generic edges in React Flow<br>(B) Color-coded edges by `severity` and dashed for `potential` | **Option B**: Visually distinguishes AI predictions from human-confirmed links. | **Heet / Parth** (Role 7 graph) |
| **D7** | **Missing FR-23 Endpoint** | (A) Embed answer in `PATCH /findings/{id}`<br>(B) Add dedicated `PATCH /api/v1/clarifications/{id}` | **Option B**: Clean resource-oriented API for answering clarification questions. | **Parth** (API Lead) |
| **D8** | **Requirement Version Rationale** | (A) Omit edit rationale<br>(B) Add nullable `change_reason` to `requirement_versions` | **Option B in Sprint 3 (T34)**: Enables capturing rationale during requirement modifications. | **Parth** (DB schema) |

---

## 8. Remaining Work & Sprint 3 Outlook

With the data models and schemas formalized in this document:
- **Sprint 0 Deliverable**: Completed (requirements review, data model design, and architecture documentation).
- **Sprint 1 & 2 Dependencies**: Wait for Role 1 (Ingestion pipeline) and Role 2/3 (Embeddings and LLM Classification pipeline) to populate real requirements and findings.
- **Sprint 3 Implementation Roadmap**:
  - `T25`: Design the LLM prompt for generating clarification questions (`backend/app/clarification/question_gen.py`).
  - `T26`: Implement clarification endpoint and answer submission logic (`backend/app/api/findings.py`).
  - `T31`: Build the change-impact analysis graph traversal engine (`backend/app/clarification/impact_analysis.py`).
  - `T32`: Expose the impacted-requirements API (`GET /requirements/{id}/impact`).
  - `T34`: Implement requirement version history tracking during updates (`RequirementVersion`).
