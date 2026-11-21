"""Requirement attributes (Heet — US-58, FR-101, ADR-27; migration 0010b; design update §11.1).

The structured reading of one requirement **version** that rule-based cross-checks compare:
written by ``app.search.rule_checker`` from Keval's ``AttributeExtractor``. A new version gets a
new row; older rows stay as history and are never compared.
"""

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, Float, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin


class RequirementAttribute(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "requirement_attributes"
    __table_args__ = (
        UniqueConstraint("requirement_id", "version_no"),
        CheckConstraint("extractor IN ('rules', 'llm')", name="extractor_values"),
        CheckConstraint(
            "comparison IS NULL OR comparison IN ('<=', '>=', '=')", name="comparison_values"
        ),
        CheckConstraint("confidence BETWEEN 0 AND 1", name="confidence_range"),
        CheckConstraint("version_no >= 1", name="version_positive"),
        Index("ix_requirement_attributes_project_id_entity", "project_id", "entity"),
        Index("ix_requirement_attributes_project_id_metric", "project_id", "metric"),
    )

    requirement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("requirements.id", ondelete="CASCADE")
    )
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    version_no: Mapped[int]
    entity: Mapped[str | None] = mapped_column(String(120))
    metric: Mapped[str | None] = mapped_column(String(80))
    value: Mapped[float | None] = mapped_column(Float)  # in the base unit (seconds, bytes…)
    unit: Mapped[str | None] = mapped_column(String(16))
    comparison: Mapped[str | None] = mapped_column(String(2))
    actor: Mapped[str | None] = mapped_column(String(120))
    action: Mapped[str | None] = mapped_column(String(120))
    condition: Mapped[str | None] = mapped_column(String(200))
    negated: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    modality: Mapped[str | None] = mapped_column(String(16))
    extractor: Mapped[str] = mapped_column(String(8))
    confidence: Mapped[float] = mapped_column(Float)
