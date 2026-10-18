"""JoinCode and JoinRequest models (Role 4 / Role 5 — US-25, FR-37)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column
from app.models.enums import JoinCodeStatus, JoinRequestStatus, Role

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.workspace import Workspace


class JoinCode(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A workspace invite/join code stored as a peppered SHA-256 hash (US-25).

    Plaintext codes are never stored in the database.
    """

    __tablename__ = "join_codes"
    __table_args__ = (
        CheckConstraint("use_count >= 0", name="use_count_non_negative"),
        CheckConstraint("max_uses IS NULL OR max_uses > 0", name="max_uses_positive"),
        # Security invariant: join codes can never grant admin privileges
        CheckConstraint("role != 'admin'", name="non_admin_role"),
        Index("ix_join_codes_workspace_status", "workspace_id", "status"),
    )

    code_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True, nullable=False
    )
    role: Mapped[Role] = mapped_column(enum_column(Role, "join_code_role"), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    max_uses: Mapped[int | None] = mapped_column(Integer, nullable=True)
    use_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[JoinCodeStatus] = mapped_column(
        enum_column(JoinCodeStatus, "join_code_status"),
        default=JoinCodeStatus.ACTIVE,
        server_default=JoinCodeStatus.ACTIVE.value,
        nullable=False,
        index=True,
    )
    requires_approval: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    revoked_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    workspace: Mapped[Workspace] = relationship()
    creator: Mapped[User] = relationship(foreign_keys=[created_by])
    revoker: Mapped[User | None] = relationship(foreign_keys=[revoked_by])
    join_requests: Mapped[list[JoinRequest]] = relationship(
        back_populates="join_code", passive_deletes=True
    )

    @property
    def masked_code(self) -> str:
        """Non-sensitive prefix representation safe for admin listings."""
        if self.code_hash:
            return f"{self.code_hash[:4].upper()}****"
        return "****"

    def __repr__(self) -> str:
        # Never expose code_hash in repr / logs
        return f"JoinCode(id={self.id}, workspace_id={self.workspace_id}, role={self.role.value}, status={self.status.value})"


class JoinRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A user's pending request to join a workspace via an approval-gated join code."""

    __tablename__ = "join_requests"
    __table_args__ = (Index("ix_join_requests_workspace_status", "workspace_id", "status"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    join_code_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("join_codes.id", ondelete="CASCADE"), index=True, nullable=False
    )
    status: Mapped[JoinRequestStatus] = mapped_column(
        enum_column(JoinRequestStatus, "join_request_status"),
        default=JoinRequestStatus.PENDING,
        server_default=JoinRequestStatus.PENDING.value,
        nullable=False,
        index=True,
    )
    assigned_role: Mapped[Role] = mapped_column(
        enum_column(Role, "join_request_role"), nullable=False
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    workspace: Mapped[Workspace] = relationship()
    user: Mapped[User] = relationship(foreign_keys=[user_id])
    join_code: Mapped[JoinCode] = relationship(back_populates="join_requests")
    reviewer: Mapped[User | None] = relationship(foreign_keys=[reviewed_by])

    @property
    def user_email(self) -> str | None:
        return self.user.email if self.user else None

    @property
    def user_full_name(self) -> str | None:
        return self.user.full_name if self.user else None

    def __repr__(self) -> str:
        return f"JoinRequest(id={self.id}, workspace_id={self.workspace_id}, user_id={self.user_id}, status={self.status.value})"
