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
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin, enum_column
from app.models.enums import FindingCategory, FindingStatus, Severity
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
        Index("ix_candidate_pairs_requirement_b_id", "requirement_b_id"),
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
    )

    # Denormalised from the pair/requirement so "findings for a document" (FR-27) and
    # workspace scoping (FR-38) don't need joins through three tables.
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
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
