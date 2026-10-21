"""Project context models (Bansil — US-60, FR-103 to FR-105, ADR-28; migration ``0011``).

``project_contexts`` is versioned and append-only: every save is a new row with its author and
reason, so the history of what the AI was told is never lost. ``projects.context_version`` points
at the newest version whose required fields are all confirmed (0 while the project is in Setup).

``document_sections`` keeps each heading of an uploaded document with the verbatim text under it.
The brief drafter reads the introduction and overall description from it (FR-104); the context
pack picks the most relevant sections per LLM call (FR-105, Keval) once Heet's embedding stage
fills ``embedding``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin
from app.models.embedding import EMBEDDING_DIM


class ProjectContext(UUIDPrimaryKeyMixin, Base):
    """One immutable version of a project's brief (see ``app.context.brief`` for the fields)."""

    __tablename__ = "project_contexts"
    __table_args__ = (
        UniqueConstraint("project_id", "version"),
        CheckConstraint("version >= 1", name="version_positive"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    version: Mapped[int]

    purpose: Mapped[str | None] = mapped_column(Text)
    scope_in: Mapped[str | None] = mapped_column(Text)
    scope_out: Mapped[str | None] = mapped_column(Text)
    actors: Mapped[list[str] | None] = mapped_column(JSONB)
    environment: Mapped[str | None] = mapped_column(Text)
    glossary: Mapped[list[dict[str, str]] | None] = mapped_column(JSONB)  # [{term, meaning}]
    constraints: Mapped[str | None] = mapped_column(Text)
    quality_goals: Mapped[str | None] = mapped_column(Text)
    regulations: Mapped[str | None] = mapped_column(Text)
    references: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)  # [{title, url}]

    # The initial SRS the AI draft came from, if any (FR-104).
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL")
    )
    # Per brief field: "ai_drafted" or "confirmed". Empty fields have no entry.
    field_status: Mapped[dict[str, str]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    # At most 300 words; set when every required field is confirmed (design update §12.1).
    summary: Mapped[str | None] = mapped_column(Text)

    # NULL for the AI draft written by the processing worker.
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DocumentSection(UUIDPrimaryKeyMixin, Base):
    """A heading of an uploaded document and the verbatim text under it."""

    __tablename__ = "document_sections"
    __table_args__ = (
        CheckConstraint("order_index >= 0", name="order_non_negative"),
        Index("ix_document_sections_document_id_order_index", "document_id", "order_index"),
        Index("ix_document_sections_project_id", "project_id"),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    # Denormalised from the document, like requirements.project_id (ADR-14).
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    heading: Mapped[str | None] = mapped_column(Text)  # NULL: text before the first heading
    body: Mapped[str] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(Text)
    order_index: Mapped[int]
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
