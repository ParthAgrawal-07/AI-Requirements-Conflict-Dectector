"""AuditLog model (Role 5) — append-only compliance trail (FR-19, FR-36, NFR-13)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class AuditLog(UUIDPrimaryKeyMixin, Base):
    """One immutable row per auditable action.

    Immutability is enforced **in the database** (a trigger created by the initial
    migration rejects UPDATE, DELETE and TRUNCATE), not just by application convention.
    Foreign keys use ``RESTRICT`` on purpose: a finding, requirement or user that has audit
    history can't be hard-deleted out from under its trail.
    """

    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_workspace_id_at", "workspace_id", "at"),
        Index("ix_audit_log_finding_id", "finding_id"),
        Index("ix_audit_log_requirement_id", "requirement_id"),
        Index("ix_audit_log_actor_id", "actor_id"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT")
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    finding_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("findings.id", ondelete="RESTRICT")
    )
    # Direct requirement reference so viewing a *protected requirement* can be logged even
    # when no finding is involved (NFR-13).
    requirement_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("requirements.id", ondelete="RESTRICT")
    )
    action: Mapped[str] = mapped_column(String(64))  # see enums.AuditAction for known values
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
