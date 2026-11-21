"""The updated SRS: drafts, sections and published versions (Bansil — US-61, FR-106, FR-107,
DR-25, ADR-29; migration 0012a; design update §12.1).

``srs_documents`` — one row per draft or published version. It freezes the requirements it is
built from (``requirements``: each Approved and Implemented requirement of the chosen baseline
with its printed ID, version, text, priority, owner, type and group), so review, the fidelity
check and publishing all compare against the same list even if the baseline moves on. A
published document is immutable (a trigger refuses UPDATE and DELETE).

``srs_sections`` — the ISO/IEC/IEEE 29148 outline, one row per section: ``kind`` narrative,
requirements or appendix; ``source`` llm (AI text, labelled until accepted), template (the
no-LLM fallback text), system (requirement sections, inserted verbatim and never editable) or
edited (a person rewrote it); ``status`` pending or accepted.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

SRS_STATUSES = ("generating", "draft", "published", "discarded")
SECTION_KINDS = ("narrative", "requirements", "appendix")
SECTION_SOURCES = ("llm", "template", "system", "edited")
SECTION_STATUSES = ("pending", "generating", "accepted")


def _values(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class SrsDocument(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "srs_documents"
    __table_args__ = (
        CheckConstraint(_values("status", SRS_STATUSES), name="status_values"),
        CheckConstraint(
            "status <> 'published' OR (published_at IS NOT NULL AND version_label IS NOT NULL)",
            name="published_has_version",
        ),
        Index(
            "uq_srs_documents_project_id_version_label",
            "project_id",
            "version_label",
            unique=True,
            postgresql_where=text("status = 'published'"),
        ),
        Index("ix_srs_documents_project_id_created_at", "project_id", "created_at"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    # The labelled baseline it was built from (US-40), or NULL for "the current baseline".
    baseline_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("baselines.id", ondelete="SET NULL")
    )
    baseline_revision: Mapped[int]
    version_label: Mapped[str | None] = mapped_column(String(16))  # "v1.1": set when published
    status: Mapped[str] = mapped_column(String(16), default="generating")
    context_version: Mapped[int | None]
    requirements: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    readiness: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    override_reason: Mapped[str | None] = mapped_column(Text)
    # The open-items report attached when a PM overrode the readiness checklist (US-59).
    open_items: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    fidelity_report: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    llm_calls: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    published_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SrsSection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "srs_sections"
    __table_args__ = (
        UniqueConstraint("srs_id", "key"),
        CheckConstraint(_values("kind", SECTION_KINDS), name="kind_values"),
        CheckConstraint(_values("source", SECTION_SOURCES), name="source_values"),
        CheckConstraint(_values("status", SECTION_STATUSES), name="status_values"),
        # DR-25: requirement sections are inserted by the system and never edited.
        CheckConstraint("kind <> 'requirements' OR source = 'system'", name="requirements_system"),
    )

    srs_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("srs_documents.id", ondelete="CASCADE"))
    key: Mapped[str] = mapped_column(String(48))  # "1.2_scope"
    order: Mapped[int]
    title: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(16))
    body: Mapped[str] = mapped_column(Text, default="", server_default="")
    source: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    regenerations: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    instruction: Mapped[str | None] = mapped_column(Text)
    llm_calls: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    llm_model: Mapped[str | None] = mapped_column(String(80))
    note: Mapped[str | None] = mapped_column(Text)  # e.g. why the template text is shown
    accepted_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
