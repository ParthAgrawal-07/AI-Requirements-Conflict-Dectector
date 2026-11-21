"""Baseline snapshots (Parth — US-40, FR-73, DR-08; migration 0010c).

A baseline freezes, under a label ("v1.0 sign-off"), every Approved and Implemented requirement of
a project with its version and text at that moment. Snapshots are immutable — a database trigger
refuses UPDATE and DELETE — and audited when frozen.
"""

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin


class Baseline(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "baselines"
    __table_args__ = (
        UniqueConstraint("project_id", "label"),
        CheckConstraint("length(trim(label)) > 0", name="label_not_blank"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    label: Mapped[str] = mapped_column(String(80))
    note: Mapped[str | None] = mapped_column(Text)
    baseline_revision: Mapped[int]  # the project's baseline revision when it was frozen
    requirement_count: Mapped[int]
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class BaselineItem(Base):
    __tablename__ = "baseline_items"

    baseline_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("baselines.id", ondelete="CASCADE"), primary_key=True
    )
    requirement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("requirements.id", ondelete="CASCADE"), primary_key=True
    )
    version_no: Mapped[int]
    label: Mapped[str | None] = mapped_column(String(64))  # the printed ID then, e.g. "REQ-014"
    state: Mapped[str] = mapped_column(String(32))
    body: Mapped[str] = mapped_column(Text)  # the text at that version, frozen with the baseline
