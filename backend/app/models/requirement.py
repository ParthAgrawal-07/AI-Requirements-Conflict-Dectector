"""Requirement and RequirementVersion models (Role 5) — FR-04, FR-05, FR-21, FR-26."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.embedding import Embedding


class Requirement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One extracted requirement statement.

    Maps from ``app.ingestion.models.Requirement``: ``id`` -> ``source_req_id``,
    ``raw_text`` -> ``body``, ``location`` -> ``location``.
    """

    __tablename__ = "requirements"
    __table_args__ = (
        CheckConstraint("current_version >= 1", name="version_positive"),
        CheckConstraint("order_index >= 0", name="order_non_negative"),
        Index("ix_requirements_document_id_order_index", "document_id", "order_index"),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    # The ID printed in the source document ("REQ-014"), when there was one (FR-04, DR-03).
    # Not unique: real SRS documents contain duplicate IDs, which is itself a finding.
    source_req_id: Mapped[str | None] = mapped_column(String(64))
    body: Mapped[str] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(64))  # e.g. "page 3", "paragraph 12"
    order_index: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    stakeholder_group: Mapped[str | None] = mapped_column(String(120))  # FR-05, DR-11
    # Compliance-critical: never auto-resolved, all access audited (FR-21, DR-05, NFR-13).
    is_protected: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    current_version: Mapped[int] = mapped_column(default=1, server_default=text("1"))

    document: Mapped[Document] = relationship(back_populates="requirements")
    versions: Mapped[list[RequirementVersion]] = relationship(
        back_populates="requirement", passive_deletes=True, order_by="RequirementVersion.version_no"
    )
    embedding: Mapped[Embedding | None] = relationship(
        back_populates="requirement", passive_deletes=True
    )


class RequirementVersion(UUIDPrimaryKeyMixin, Base):
    """Immutable snapshot of a requirement's text at a given version (FR-26, DR-08)."""

    __tablename__ = "requirement_versions"
    __table_args__ = (
        UniqueConstraint("requirement_id", "version_no"),
        CheckConstraint("version_no >= 1", name="version_positive"),
    )

    requirement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("requirements.id", ondelete="CASCADE")
    )
    version_no: Mapped[int]
    body_snapshot: Mapped[str] = mapped_column(Text)
    # NULL for the initial extraction, which is performed by the system rather than a person.
    changed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    requirement: Mapped[Requirement] = relationship(back_populates="versions")
