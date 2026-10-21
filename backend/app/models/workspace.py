"""Workspace model (Role 5) — the tenancy boundary (FR-38, ADR-14).

Workspace -> Project -> Channel. People belong to a workspace through ``memberships``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Float, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.membership import Membership
    from app.models.project import Project


class Workspace(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Access boundary: members only see projects, documents and results of their workspace."""

    __tablename__ = "workspaces"
    __table_args__ = (
        CheckConstraint("similarity_threshold BETWEEN 0 AND 1", name="similarity_threshold_range"),
    )

    # Display name only — *not* unique. A platform-wide unique name would let one tenant learn that
    # another tenant's workspace exists (a 409 on create/rename); workspaces are identified by id.
    name: Mapped[str] = mapped_column(String(120))
    # Legacy workspace-level default (FR-10). Thresholds are per *project* since Sprint 0
    # (``projects.similarity_threshold``); this column is kept so migration 0004 can copy it
    # into the backfilled project and is no longer read by the application.
    similarity_threshold: Mapped[float] = mapped_column(
        Float, server_default=text("0.75"), default=0.75
    )

    memberships: Mapped[list[Membership]] = relationship(back_populates="workspace")
    projects: Mapped[list[Project]] = relationship(back_populates="workspace")
    documents: Mapped[list[Document]] = relationship(back_populates="workspace")
