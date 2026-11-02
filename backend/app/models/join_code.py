"""JoinCode and JoinRequest models (Madhav — US-25, FR-44, FR-77, NFR-35).

A join code lets a person join a workspace (or one project in it) with a preset role, without
anyone creating their account. Only a keyed hash of the code is stored; the code itself is shown
once, when it is created. ``code_hint`` (the last four characters) lets managers tell codes apart
in the list without making the stored data useful for redemption.

A code can never grant Owner, Admin or any role with their permissions. That rule is enforced on
*permissions* by ``app.services.membership`` (``via_join_code=True``) at creation and again at
redemption, so it also covers custom roles; there is no role-name CHECK here on purpose (ADR-20).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column
from app.models.enums import JoinCodeStatus, JoinRequestStatus

if TYPE_CHECKING:
    from app.models.role import Role
    from app.models.user import User


class JoinCode(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "join_codes"
    __table_args__ = (
        CheckConstraint("uses >= 0", name="uses_non_negative"),
        CheckConstraint("max_uses IS NULL OR max_uses > 0", name="max_uses_positive"),
        CheckConstraint("max_uses IS NULL OR uses <= max_uses", name="uses_within_max"),
        Index("ix_join_codes_workspace_id_status", "workspace_id", "status"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    # Set for a project-scoped code: joining also adds the user to this project's team.
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE")
    )
    # HMAC-SHA256 of the canonical code, keyed with JOIN_CODE_PEPPER (hex).
    code_hash: Mapped[str] = mapped_column(String(64), unique=True)
    code_hint: Mapped[str] = mapped_column(String(4))
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id", ondelete="RESTRICT"))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    max_uses: Mapped[int | None]  # NULL = unlimited until expiry
    uses: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    requires_approval: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    status: Mapped[JoinCodeStatus] = mapped_column(
        enum_column(JoinCodeStatus, "join_code_status"),
        default=JoinCodeStatus.ACTIVE,
        server_default=JoinCodeStatus.ACTIVE.value,
    )
    revoked_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    role: Mapped[Role] = relationship()
    creator: Mapped[User] = relationship(foreign_keys=[created_by])

    def __repr__(self) -> str:  # never the hash: it is the next best thing to the code
        return f"JoinCode(id={self.id}, workspace_id={self.workspace_id}, status={self.status})"


class JoinRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "join_requests"
    __table_args__ = (
        # One open request per person and workspace; decided ones are kept as history.
        Index(
            "uq_join_requests_pending_user_workspace",
            "user_id",
            "workspace_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        Index("ix_join_requests_workspace_id_status", "workspace_id", "status"),
    )

    # Denormalised from the code so "pending requests of this workspace" needs no join.
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE")
    )
    join_code_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("join_codes.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    status: Mapped[JoinRequestStatus] = mapped_column(
        enum_column(JoinRequestStatus, "join_request_status"),
        default=JoinRequestStatus.PENDING,
        server_default=JoinRequestStatus.PENDING.value,
    )
    # The role the member gets if approved: the code's role unless the manager picks another.
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id", ondelete="RESTRICT"))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(foreign_keys=[user_id])
    role: Mapped[Role] = relationship()
