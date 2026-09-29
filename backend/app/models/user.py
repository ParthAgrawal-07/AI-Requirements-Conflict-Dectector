"""User model (Role 5) — identity and role for authentication/RBAC (FR-37, NFR-11)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column
from app.models.enums import Role

if TYPE_CHECKING:
    from app.models.workspace import Workspace


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("email = lower(email)", name="email_lowercase"),)

    # Always stored lower-cased (enforced by the CHECK above) so uniqueness is case-insensitive.
    email: Mapped[str] = mapped_column(String(320), unique=True)
    full_name: Mapped[str] = mapped_column(String(200))
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(enum_column(Role, "user_role"), default=Role.ANALYST)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"), index=True
    )
    # Users are deactivated, never deleted: audit_log and provenance columns reference them.
    is_active: Mapped[bool] = mapped_column(server_default=text("true"), default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    workspace: Mapped[Workspace] = relationship(back_populates="users")

    def __repr__(self) -> str:  # never include hashed_password
        return f"User(id={self.id}, email={self.email!r}, role={self.role.value})"
