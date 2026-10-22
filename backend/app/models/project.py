"""Project model (Parth — US-24, FR-47, ADR-14).

A workspace contains projects; each project has its own baseline, documents, thresholds, LLM
budget and approval settings. A project starts in ``setup`` and becomes ``active`` only when
its context is confirmed (FR-103, US-60); no analysis may run before that (ContextGate,
``app.services.projects.ensure_project_active``).

Columns added by later migrations: ``graph_revision`` (0006), ``baseline_revision`` (0007),
``use_feedback_examples`` (0010b). The context itself lives in ``project_contexts`` (0011,
Bansil, ``app.models.context``).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column
from app.models.enums import ProjectStatus

if TYPE_CHECKING:
    from app.models.membership import ProjectMember
    from app.models.workspace import Workspace


class Project(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("workspace_id", "name"),
        CheckConstraint("similarity_threshold BETWEEN 0 AND 1", name="similarity_threshold_range"),
        CheckConstraint("confidence_threshold BETWEEN 0 AND 1", name="confidence_threshold_range"),
        CheckConstraint("llm_budget_monthly_calls >= 0", name="llm_budget_non_negative"),
        CheckConstraint("required_approvals BETWEEN 1 AND 3", name="required_approvals_range"),
        CheckConstraint("context_version >= 0", name="context_version_non_negative"),
        Index("ix_projects_workspace_id_status", "workspace_id", "status"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT")
    )
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)

    # FR-103: ``setup`` until the context is confirmed, then ``active``.
    status: Mapped[ProjectStatus] = mapped_column(
        enum_column(ProjectStatus, "project_status"),
        default=ProjectStatus.SETUP,
        server_default=ProjectStatus.SETUP.value,
    )
    # Current confirmed context version (FR-105). 0 = none yet. Owned by app/context (Bansil);
    # the column lives here because it is part of the project row Parth creates.
    context_version: Mapped[int] = mapped_column(default=0, server_default=text("0"))

    # Per-project analysis settings (FR-47, US-06). Defaults are team-tunable starting points.
    similarity_threshold: Mapped[float] = mapped_column(
        Float, default=0.75, server_default=text("0.75")
    )
    confidence_threshold: Mapped[float] = mapped_column(
        Float, default=0.5, server_default=text("0.5")
    )
    llm_budget_monthly_calls: Mapped[int] = mapped_column(default=2000, server_default=text("2000"))
    chat_detection_enabled: Mapped[bool] = mapped_column(
        default=False, server_default=text("false")
    )  # SX-04, NFR-30: chat text goes to the LLM only if a manager switches this on
    required_approvals: Mapped[int] = mapped_column(default=1, server_default=text("1"))

    # Users are deactivated, never deleted, so SET NULL only matters for odd cleanup scripts.
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    workspace: Mapped[Workspace] = relationship(back_populates="projects")
    members: Mapped[list[ProjectMember]] = relationship(
        back_populates="project", passive_deletes=True
    )
