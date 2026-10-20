"""Role and RolePermission models (Parth — US-27, FR-48, ADR-20).

A role is a named set of permissions. The nine default roles (``is_default``) are platform-wide
(``workspace_id IS NULL``), seeded by migration 0004 and immutable; custom roles (US-49, Sprint 2)
belong to one workspace. Authorisation checks permission *names* from the catalogue in
``app.core.permissions`` — never role names.
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    PrimaryKeyConstraint,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Role(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "roles"
    __table_args__ = (
        # Defaults are global and custom roles are per workspace — never both or neither.
        CheckConstraint(
            "(is_default AND workspace_id IS NULL) OR (NOT is_default AND workspace_id IS NOT NULL)",
            name="default_roles_are_global",
        ),
        # NULLs are distinct in a plain unique index, so default and custom names need one
        # partial unique index each.
        Index(
            "uq_roles_default_name",
            "name",
            unique=True,
            postgresql_where=text("workspace_id IS NULL"),
        ),
        Index(
            "uq_roles_workspace_id_name",
            "workspace_id",
            "name",
            unique=True,
            postgresql_where=text("workspace_id IS NOT NULL"),
        ),
    )

    # NULL for the platform defaults; the owning workspace for custom roles.
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str | None] = mapped_column(Text)
    is_default: Mapped[bool] = mapped_column(default=False, server_default=text("false"))

    permissions: Mapped[list[RolePermission]] = relationship(
        back_populates="role", passive_deletes=True, cascade="all, delete-orphan"
    )

    @property
    def permission_names(self) -> frozenset[str]:
        return frozenset(grant.permission for grant in self.permissions)

    def __repr__(self) -> str:
        return f"Role(id={self.id}, name={self.name!r}, default={self.is_default})"


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (PrimaryKeyConstraint("role_id", "permission"),)

    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"))
    # A name from the catalogue (app.core.permissions.PERMISSIONS). Validated by the service
    # layer; the catalogue changes by migration + code, so no CHECK list is duplicated here.
    permission: Mapped[str] = mapped_column(String(64))
    # Spec §1.22: the Compliance Reviewer's ``finding.review`` is "protected only" — held, but
    # exercisable only on protected requirements.
    protected_only: Mapped[bool] = mapped_column(default=False, server_default=text("false"))

    role: Mapped[Role] = relationship(back_populates="permissions")
