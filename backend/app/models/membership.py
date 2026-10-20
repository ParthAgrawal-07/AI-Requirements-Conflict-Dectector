"""Membership and ProjectMember models (Parth — US-27, FR-45, FR-46, FR-79, ADR-14).

``Membership`` replaces the old global ``users.role`` / ``users.workspace_id`` (SX-06): a user can
belong to several workspaces, with a separate role in each. Access is decided by the *active*
membership (``ended_at IS NULL``), which is re-read on every request so that removing a member
or changing a role takes effect immediately (NFR-27).

``ProjectMember`` lists who belongs to a project and may carry a project-level role that
overrides the workspace role inside that project (FR-79). In the MVP it is not an access gate:
FR-38 restricts access to active members of the *workspace*.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, PrimaryKeyConstraint, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.role import Role
    from app.models.user import User
    from app.models.workspace import Workspace


class Membership(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "memberships"
    __table_args__ = (
        # At most one *active* membership per (user, workspace); history rows (ended_at set)
        # are unlimited so rejoining never needs an UPDATE of an old row.
        Index(
            "uq_memberships_active_user_workspace",
            "user_id",
            "workspace_id",
            unique=True,
            postgresql_where=text("ended_at IS NULL"),
        ),
        Index("ix_memberships_workspace_id_ended_at", "workspace_id", "ended_at"),
        Index("ix_memberships_user_id", "user_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT")
    )
    # RESTRICT: a role referenced by a membership cannot be deleted (design update §4.2).
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id", ondelete="RESTRICT"))
    stakeholder_group: Mapped[str | None] = mapped_column(String(120))  # DR-11
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # NULL while active. Removal sets it (FR-45); content stays attributed to the former member.
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="memberships")
    workspace: Mapped[Workspace] = relationship(back_populates="memberships")
    role: Mapped[Role] = relationship()

    @property
    def is_active(self) -> bool:
        return self.ended_at is None


class ProjectMember(Base):
    __tablename__ = "project_members"
    __table_args__ = (PrimaryKeyConstraint("project_id", "user_id"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    # Overrides the workspace role inside this project only (never above the PM's own rights,
    # enforced by the service that writes it — US-49, Sprint 2).
    role_override_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("roles.id", ondelete="RESTRICT")
    )
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped[Project] = relationship(back_populates="members")
    user: Mapped[User] = relationship()
    role_override: Mapped[Role | None] = relationship()
