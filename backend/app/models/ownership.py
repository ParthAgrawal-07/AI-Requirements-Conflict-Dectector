"""Ownership requests (Bansil — US-36, FR-59; migration 0006f).

A member who may propose asks to own a requirement; its current owner or a manager accepts (the
requester becomes the owner) or declines. Owners are who conflicts, change reviews and
notifications reach (US-31, US-35, US-38, US-52), so ownership never changes silently: every
change is audited.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin

PENDING, ACCEPTED, DECLINED = "pending", "accepted", "declined"


class OwnershipRequest(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "ownership_requests"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'accepted', 'declined')", name="status_values"),
        Index("ix_ownership_requests_requirement_id_status", "requirement_id", "status"),
        Index(
            "uq_ownership_requests_one_pending",
            "requirement_id",
            "requester_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
    )

    requirement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("requirements.id", ondelete="CASCADE")
    )
    requester_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(16), default=PENDING, server_default=PENDING)
    note: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
