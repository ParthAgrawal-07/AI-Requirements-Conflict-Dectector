"""Change requests (Bansil — US-33, FR-62, FR-65, FR-89, FR-98; migration 0007a; §7.2).

A change request (RCR-n, numbered per project) proposes new text for one requirement, or its
deprecation, the way a pull request proposes a change to code. It is written against
``base_version``; ``proposal_revision`` counts edits of the proposal so approvals and checks bind
to exact text. Every revision is kept in ``change_request_revisions``; "Resolves ISS-n" links
live in ``change_request_issues``.
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

from app.models.base import Base, UUIDPrimaryKeyMixin

MODIFY, DEPRECATE = "modify", "deprecate"
DRAFT, OPEN, NEEDS_UPDATE, APPROVED = "draft", "open", "needs_update", "approved"
MERGED, CLOSED, WITHDRAWN = "merged", "closed", "withdrawn"
STATUSES = (DRAFT, OPEN, NEEDS_UPDATE, APPROVED, MERGED, CLOSED, WITHDRAWN)
ACTIVE = (DRAFT, OPEN, NEEDS_UPDATE, APPROVED)  # not decided yet
_STATUS_LIST = ", ".join(f"'{s}'" for s in STATUSES)


class ChangeRequest(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "change_requests"
    __table_args__ = (
        CheckConstraint("kind IN ('modify', 'deprecate')", name="kind_values"),
        CheckConstraint(f"status IN ({_STATUS_LIST})", name="status_values"),
        CheckConstraint("(kind = 'deprecate') = (proposed_body IS NULL)", name="body_matches_kind"),
        CheckConstraint("base_version >= 1", name="base_version_positive"),
        CheckConstraint("proposal_revision >= 1", name="proposal_revision_positive"),
        CheckConstraint("number >= 1", name="number_positive"),
        UniqueConstraint("project_id", "number"),
        Index("ix_change_requests_requirement_id_status", "requirement_id", "status"),
        Index("ix_change_requests_project_id_status", "project_id", "status"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    requirement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("requirements.id", ondelete="CASCADE")
    )
    number: Mapped[int]  # RCR-<number>
    proposer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    kind: Mapped[str] = mapped_column(String(16), default=MODIFY, server_default=MODIFY)
    status: Mapped[str] = mapped_column(String(16), default=OPEN, server_default=OPEN)
    base_version: Mapped[int]
    proposal_revision: Mapped[int] = mapped_column(default=1, server_default=text("1"))
    proposed_body: Mapped[str | None] = mapped_column(Text)  # NULL for a deprecation
    # The composer fields of the proposed text (template, slots…), when it was written in one.
    proposed_fields: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    reason: Mapped[str] = mapped_column(Text)
    # What the consequence checks last ran on (FR-98): merge needs both to be current.
    checks_proposal_revision: Mapped[int | None]
    checks_base_version: Mapped[int | None]
    merged_version: Mapped[int | None]  # the requirement version the merge wrote
    merged_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    merged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    close_reason: Mapped[str | None] = mapped_column(Text)
    # The AI suggestion it was pre-filled from (US-45, migration 0008); people wrote the rest.
    source_suggestion_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("suggestions.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ChangeRequestRevision(UUIDPrimaryKeyMixin, Base):
    """One proposal revision as written; never updated."""

    __tablename__ = "change_request_revisions"
    __table_args__ = (UniqueConstraint("change_request_id", "revision"),)

    change_request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("change_requests.id", ondelete="CASCADE")
    )
    revision: Mapped[int]
    proposed_body: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    author_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChangeRequestIssue(Base):
    __tablename__ = "change_request_issues"
    __table_args__ = (Index("ix_change_request_issues_issue_id", "issue_id"),)

    change_request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("change_requests.id", ondelete="CASCADE"), primary_key=True
    )
    issue_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("issues.id", ondelete="CASCADE"), primary_key=True
    )
