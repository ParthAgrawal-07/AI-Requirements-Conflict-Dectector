"""Notifications (Madhav — US-38, FR-69, FR-70; migration 0008; design update §4.1).

One row per person and subject that needs them. ``payload`` holds IDs, printed keys and titles
only — never requirement or message text (CR-04). An unread notification of the same kind about
the same subject is *refreshed* rather than repeated, so the inbox shows "RCR-3: review requested"
once however many times it is asked.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

REVIEW_REQUESTED = "review_requested"
ASSIGNED = "assigned"
MENTIONED = "mentioned"
WATCHING = "watching"
RESULTS = "results"
JOIN_REQUEST = "join_request"
DECISION = "decision"
MERGED = "merged"
KINDS = (REVIEW_REQUESTED, ASSIGNED, MENTIONED, WATCHING, RESULTS, JOIN_REQUEST, DECISION, MERGED)
_KIND_LIST = ", ".join(f"'{k}'" for k in KINDS)


class Notification(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(f"kind IN ({_KIND_LIST})", name="kind_values"),
        Index("ix_notifications_user_id_updated_at", "user_id", "updated_at"),
        Index(
            "ix_notifications_user_id_unread",
            "user_id",
            "kind",
            postgresql_where=text("read_at IS NULL"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(String(32))
    subject_type: Mapped[str] = mapped_column(String(32))  # change_request, issue, finding…
    subject_id: Mapped[uuid.UUID]
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
