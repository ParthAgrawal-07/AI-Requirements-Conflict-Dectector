"""User model (Role 5) — identity for authentication (FR-37, NFR-11).

A user no longer carries a role or a workspace (SX-06): workspace roles live on
``memberships``. The only account-level role is ``platform_role`` (platform admin / service).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column
from app.models.enums import PlatformRole

if TYPE_CHECKING:
    from app.models.membership import Membership


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("email = lower(email)", name="email_lowercase"),)

    # Always stored lower-cased (enforced by the CHECK above) so uniqueness is case-insensitive.
    email: Mapped[str] = mapped_column(String(320), unique=True)
    full_name: Mapped[str] = mapped_column(String(200))
    hashed_password: Mapped[str] = mapped_column(String(255))
    # NULL for ordinary users. ``platform_admin`` is created by the CLI only (FR-37).
    platform_role: Mapped[PlatformRole | None] = mapped_column(
        enum_column(PlatformRole, "user_platform_role")
    )
    # Users are deactivated, never deleted: audit_log and provenance columns reference them.
    is_active: Mapped[bool] = mapped_column(server_default=text("true"), default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    memberships: Mapped[list[Membership]] = relationship(back_populates="user")

    @property
    def is_platform_admin(self) -> bool:
        return self.platform_role is PlatformRole.PLATFORM_ADMIN

    def __repr__(self) -> str:  # never include hashed_password
        return f"User(id={self.id}, email={self.email!r})"
