"""Issues and comments (Dhavni — US-52, FR-86, FR-87; migration 0007; design update §7.4).

An issue (ISS-n, numbered per project) is a problem people discuss and close: opened by a member,
or **automatically** for a Conflicting finding between requirements of two or more owners
(``app.services.issues.ConflictIssueOpener``). ``open → closed`` with a ``close_reason``;
``closed → open`` again on reopen, or automatically when an auto issue's finding is re-flagged.

``Comment`` is shared by every discussable subject (issues now; requirements and change requests
later), told apart by ``subject_type``.
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
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

OPEN, CLOSED = "open", "closed"
RESOLVED_BY_MERGE, FINDING_RESOLVED, MANUAL = "resolved_by_merge", "finding_resolved", "manual"
CLOSE_REASONS = (RESOLVED_BY_MERGE, FINDING_RESOLVED, MANUAL)


class Issue(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "issues"
    __table_args__ = (
        CheckConstraint("status IN ('open', 'closed')", name="status_values"),
        CheckConstraint(
            "close_reason IS NULL OR close_reason IN "
            "('resolved_by_merge', 'finding_resolved', 'manual')",
            name="close_reason_values",
        ),
        CheckConstraint(
            "(status = 'closed') = (close_reason IS NOT NULL)", name="closed_has_reason"
        ),
        CheckConstraint("number >= 1", name="number_positive"),
        UniqueConstraint("project_id", "number"),
        Index("ix_issues_project_id_status", "project_id", "status"),
        # At most one auto issue per finding (FR-87): a re-run never opens a second one.
        Index(
            "uq_issues_auto_finding_id",
            "finding_id",
            unique=True,
            postgresql_where=text("auto AND finding_id IS NOT NULL"),
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    number: Mapped[int]  # ISS-<number>
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="", server_default="")
    status: Mapped[str] = mapped_column(String(16), default=OPEN, server_default=OPEN)
    close_reason: Mapped[str | None] = mapped_column(String(32))
    auto: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    finding_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("findings.id", ondelete="SET NULL")
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(  # NULL for an auto issue
        ForeignKey("users.id", ondelete="SET NULL")
    )
    labels: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    closed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Who decides, as resolved by the project's decision rules (US-57, migration 0010c);
    # refreshed at the item's next update, never retroactively.
    decision: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class IssueRequirement(Base):
    __tablename__ = "issue_requirements"
    __table_args__ = (Index("ix_issue_requirements_requirement_id", "requirement_id"),)

    issue_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("issues.id", ondelete="CASCADE"), primary_key=True
    )
    requirement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("requirements.id", ondelete="CASCADE"), primary_key=True
    )


class IssueAssignee(Base):
    __tablename__ = "issue_assignees"
    __table_args__ = (Index("ix_issue_assignees_user_id", "user_id"),)

    issue_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("issues.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )


class Comment(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "comments"
    __table_args__ = (
        CheckConstraint(
            "subject_type IN ('requirement', 'issue', 'change_request')",
            name="subject_type_values",
        ),
        CheckConstraint("length(body) > 0", name="body_not_empty"),
        Index(
            "ix_comments_subject_type_subject_id_created_at",
            "subject_type",
            "subject_id",
            "created_at",
        ),
    )

    subject_type: Mapped[str] = mapped_column(String(16))
    subject_id: Mapped[uuid.UUID]
    author_id: Mapped[uuid.UUID | None] = mapped_column(  # NULL: written by the app
        ForeignKey("users.id", ondelete="SET NULL")
    )
    body: Mapped[str] = mapped_column(Text)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
