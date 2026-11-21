"""Reviews of change requests (Parth — US-35, FR-65, FR-66, FR-98; migration 0007c).

``ReviewRequest`` — who was asked to review and why; ``Review`` — a decision bound to the exact
proposal revision and base version it was given on (an older revision's review is *dismissed*);
``ReviewComment`` — an inline comment on part of the proposal. A database trigger refuses an
approving review by the proposer (SX-13); ``app.services.reviews`` refuses it first, with a
clear message.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin

APPROVE, REQUEST_CHANGES, COMMENT = "approve", "request_changes", "comment"
REASONS = (
    "owner",
    "direct_conflict",
    "merge_quota",
    "compliance",
    "transitive",
    "requested",
    "decision_owner",  # US-57: named by a decision rule
    "decision_rule",
)


class ReviewRequest(Base):
    __tablename__ = "review_requests"
    __table_args__ = (
        CheckConstraint(
            "reason IN ('owner', 'direct_conflict', 'merge_quota', 'compliance', 'transitive', "
            "'requested', 'decision_owner', 'decision_rule')",
            name="reason_values",
        ),
        Index("ix_review_requests_reviewer_id", "reviewer_id"),
    )

    change_request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("change_requests.id", ondelete="CASCADE"), primary_key=True
    )
    reviewer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    required: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    reason: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Review(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "reviews"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('approve', 'request_changes', 'comment')", name="decision_values"
        ),
        CheckConstraint(
            "decision <> 'request_changes' OR rationale IS NOT NULL",
            name="request_changes_has_rationale",
        ),
        Index("ix_reviews_change_request_id_created_at", "change_request_id", "created_at"),
    )

    change_request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("change_requests.id", ondelete="CASCADE")
    )
    reviewer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    decision: Mapped[str] = mapped_column(String(16))
    rationale: Mapped[str | None] = mapped_column(Text)
    proposal_revision: Mapped[int]
    reviewed_base_version: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReviewComment(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "review_comments"
    __table_args__ = (
        CheckConstraint(
            "start_offset IS NULL OR (start_offset >= 0 AND end_offset >= start_offset)",
            name="offsets_valid",
        ),
        Index("ix_review_comments_review_id", "review_id"),
    )

    review_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reviews.id", ondelete="CASCADE"))
    field: Mapped[str] = mapped_column(String(32))  # "statement", "priority"…
    start_offset: Mapped[int | None]
    end_offset: Mapped[int | None]
    body: Mapped[str] = mapped_column(Text)
