"""Requirement transitions and finding reviews (Parth — US-37, US-10; migration 0006e).

Both are append-only history written by ``app.services.lifecycle`` and
``app.services.review_state``: who moved which requirement to which state on which version and
why, and who decided what about which finding. The audit log records the same actions with ids
only (CR-04); these tables keep the human reasons the timeline shows.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin, enum_column
from app.models.enums import FindingCategory, FindingStatus, RequirementState

REVIEW_ACTIONS = ("confirm", "dismiss", "merge", "reclassify", "reopen", "escalate")


class RequirementTransition(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "requirement_transitions"
    __table_args__ = (
        CheckConstraint("from_state <> to_state", name="changes_state"),
        Index(
            "ix_requirement_transitions_requirement_id_created_at", "requirement_id", "created_at"
        ),
    )

    requirement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("requirements.id", ondelete="CASCADE")
    )
    # Each enum column has its own name: two columns named alike would share one CHECK name.
    from_state: Mapped[RequirementState] = mapped_column(
        enum_column(RequirementState, "transition_from_state")
    )
    to_state: Mapped[RequirementState] = mapped_column(
        enum_column(RequirementState, "transition_to_state")
    )
    version: Mapped[int]  # the text that was decided (FR-98: approvals are for one exact text)
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    reason: Mapped[str | None] = mapped_column(Text)
    # Approved with a High-severity finding still open: the decision owner accepted the risk.
    accepted_risk: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FindingReview(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "finding_reviews"
    __table_args__ = (
        CheckConstraint(
            "action IN ('confirm', 'dismiss', 'merge', 'reclassify', 'reopen', 'escalate')",
            name="action_values",
        ),
        Index("ix_finding_reviews_finding_id_created_at", "finding_id", "created_at"),
    )

    finding_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("findings.id", ondelete="CASCADE"))
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    action: Mapped[str] = mapped_column(String(16))
    from_status: Mapped[FindingStatus] = mapped_column(
        enum_column(FindingStatus, "review_from_status")
    )
    to_status: Mapped[FindingStatus] = mapped_column(enum_column(FindingStatus, "review_to_status"))
    from_category: Mapped[FindingCategory] = mapped_column(
        enum_column(FindingCategory, "review_from_category")
    )
    to_category: Mapped[FindingCategory] = mapped_column(
        enum_column(FindingCategory, "review_to_category")
    )
    reason: Mapped[str | None] = mapped_column(Text)
    merged_into_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("findings.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
