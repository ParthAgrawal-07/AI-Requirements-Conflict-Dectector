"""CandidatePair, Finding and Clarification models (Role 5 schema; written by Roles 2/3/4)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin, enum_column
from app.models.enums import (
    AnalysisRunStatus,
    AnalysisScope,
    ClassificationStatus,
    FindingCategory,
    FindingStatus,
    Severity,
)
from app.models.requirement import Requirement


class CandidatePair(UUIDPrimaryKeyMixin, Base):
    """Two requirements the embedding pre-filter judged similar enough to send to the LLM.

    Pairs are stored **once**, in canonical order (``requirement_a_id < requirement_b_id``).
    Use :meth:`ordered` so (A, B) and (B, A) can't both exist.
    """

    __tablename__ = "candidate_pairs"
    __table_args__ = (
        UniqueConstraint("requirement_a_id", "requirement_b_id"),
        CheckConstraint("requirement_a_id < requirement_b_id", name="canonical_order"),
        CheckConstraint("similarity_score BETWEEN -1 AND 1", name="similarity_range"),
        CheckConstraint("attempts >= 0", name="attempts_non_negative"),
        Index("ix_candidate_pairs_requirement_b_id", "requirement_b_id"),
        Index("ix_candidate_pairs_classification_status", "classification_status"),
    )

    requirement_a_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("requirements.id", ondelete="CASCADE")
    )
    requirement_b_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("requirements.id", ondelete="CASCADE")
    )
    similarity_score: Mapped[float] = mapped_column(Float)  # cosine similarity (FR-09, FR-10)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # Per-pair classification status (gap G1, migration 0006). ``a_version``/``b_version`` are
    # the requirement versions last classified, so an unchanged pair is never paid for twice.
    classification_status: Mapped[ClassificationStatus] = mapped_column(
        enum_column(ClassificationStatus, "classification_status"),
        default=ClassificationStatus.PENDING,
        server_default=ClassificationStatus.PENDING.value,
    )
    attempts: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    # Machine-readable reason of the last failure (e.g. "invalid_output"); never model text.
    last_error: Mapped[str | None] = mapped_column(String(64))
    classified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    a_version: Mapped[int | None]
    b_version: Mapped[int | None]

    requirement_a: Mapped[Requirement] = relationship(foreign_keys=[requirement_a_id])
    requirement_b: Mapped[Requirement] = relationship(foreign_keys=[requirement_b_id])

    @staticmethod
    def ordered(first: uuid.UUID, second: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
        """Return the two ids in the canonical order required by the CHECK constraint."""
        if first == second:
            raise ValueError("A requirement cannot be paired with itself")
        return (first, second) if first < second else (second, first)


class Finding(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An issue detected by the LLM classifier and reviewed by a human (FR-13, FR-14, FR-18)."""

    __tablename__ = "findings"
    __table_args__ = (
        # A finding is about a pair (Conflicting/Duplicate/Dependent) or about a single
        # requirement (Incomplete/Ambiguous) — exactly one of the two references is set.
        CheckConstraint("num_nonnulls(candidate_pair_id, requirement_id) = 1", name="subject"),
        CheckConstraint("confidence BETWEEN 0 AND 1", name="confidence_range"),
        Index("ix_findings_document_id_status", "document_id", "status"),
        Index("ix_findings_document_id_category", "document_id", "category"),
        Index("ix_findings_project_id_status", "project_id", "status"),
        # Idempotent classification (migration 0006c): one live finding per pair. A finding made
        # stale by an edit (S4) no longer counts. Single-requirement checks are kept idempotent
        # by ``requirements.single_checked_version``.
        Index(
            "uq_findings_live_pair",
            "candidate_pair_id",
            unique=True,
            postgresql_where=text("candidate_pair_id IS NOT NULL AND NOT is_stale"),
        ),
    )

    # Every finding belongs to the project of its requirements (migration 0006c).
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    # Denormalised from the pair/requirement so "findings for a document" (FR-27) needs no join.
    # NULL when the requirements were posted rather than extracted (US-30).
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE")
    )
    analysis_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="SET NULL")
    )
    candidate_pair_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("candidate_pairs.id", ondelete="CASCADE")
    )
    requirement_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("requirements.id", ondelete="CASCADE"), index=True
    )
    category: Mapped[FindingCategory] = mapped_column(
        enum_column(FindingCategory, "finding_category")
    )
    confidence: Mapped[float] = mapped_column(Float)
    rationale: Mapped[str] = mapped_column(Text)
    # US-07: the plain-language explanation shown on the finding card (built by
    # ``app.classification.explain`` from the model output), and the quoted clauses located in
    # the requirement text: [{"requirement_id", "label", "quote", "start", "end"}].
    explanation: Mapped[str | None] = mapped_column(Text)
    evidence_spans: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    prompt_version: Mapped[str | None] = mapped_column(String(16))
    # Set when a requirement it is about changes (US-34, Sprint 4); stale findings are history.
    is_stale: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    status: Mapped[FindingStatus] = mapped_column(
        enum_column(FindingStatus, "finding_status"),
        default=FindingStatus.FLAGGED,
        server_default=FindingStatus.FLAGGED.value,
    )
    severity: Mapped[Severity | None] = mapped_column(enum_column(Severity, "finding_severity"))
    # Verbatim classifier output — kept even after a human corrects the finding (FR-20).
    original_ai_output: Mapped[dict[str, Any]] = mapped_column(JSONB)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The project context version the classifier was given (FR-105, migration 0011).
    context_version: Mapped[int | None]

    candidate_pair: Mapped[CandidatePair | None] = relationship()
    requirement: Mapped[Requirement | None] = relationship()
    clarification: Mapped[Clarification | None] = relationship(
        back_populates="finding", passive_deletes=True
    )


class Clarification(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """The clarification question generated for a finding — 1:1 with findings (FR-22, FR-23)."""

    __tablename__ = "clarifications"

    finding_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("findings.id", ondelete="CASCADE"), unique=True
    )
    question: Mapped[str] = mapped_column(Text)
    resolution: Mapped[str | None] = mapped_column(Text)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    finding: Mapped[Finding] = relationship(back_populates="clarification")


class AnalysisRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One analysis of a document (Sprint 2), a posted requirement (S3) or a change (S4).

        The orchestrator (``app.services.analysis_orchestrator``) creates it, advances ``status`` and
        counts pairs as they are classified, so the UI can say "38 of 40 pairs classified, 2 failed"
        instead of silently showing fewer findings (G1). Single-requirement checks are counted in
    ``checks_*``.
    """

    __tablename__ = "analysis_runs"
    __table_args__ = (
        CheckConstraint(
            "pairs_total >= 0 AND pairs_done >= 0 AND pairs_failed >= 0 AND llm_calls >= 0"
            " AND checks_total >= 0 AND checks_done >= 0 AND checks_failed >= 0",
            name="counts_non_negative",
        ),
        Index("ix_analysis_runs_project_id_created_at", "project_id", "created_at"),
        Index("ix_analysis_runs_subject_id", "subject_id"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    scope: Mapped[AnalysisScope] = mapped_column(enum_column(AnalysisScope, "analysis_scope"))
    subject_id: Mapped[uuid.UUID]  # the document / requirement / change request analysed
    status: Mapped[AnalysisRunStatus] = mapped_column(
        enum_column(AnalysisRunStatus, "analysis_run_status"),
        default=AnalysisRunStatus.QUEUED,
        server_default=AnalysisRunStatus.QUEUED.value,
    )
    pairs_total: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    pairs_done: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    pairs_failed: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    # Single-requirement checks (Ambiguous, Incomplete), counted the same way.
    checks_total: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    checks_done: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    checks_failed: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    llm_calls: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
