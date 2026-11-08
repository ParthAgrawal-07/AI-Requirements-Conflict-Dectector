"""Roles (Parth — US-27, US-49, FR-48, FR-78, ADR-20).

The roles a workspace can assign: the nine platform defaults plus the workspace's own custom
roles. Owners and Admins (``roles.manage``) create, edit and delete custom roles by ticking
catalogue permissions. Rules:

* **Defaults are immutable.** They are platform-wide, so ``/roles/{id}`` only ever resolves a
  custom role; a default role's id there is a 404 (see :func:`_role_scope`).
* **No escalation.** A custom role holds only permissions its author holds, and never
  ``workspace.manage`` (ownership is the Owner role's alone, so "the last owner" stays countable).
* **No surprise privilege.** A role that an active join code hands out cannot gain the permissions
  a code may never grant (FR-44).
* **In use, not deletable.** A role held by an active member, a project-level override, an active
  join code or a pending join request is a 409 until they are reassigned. Otherwise the role is
  deleted *softly*: history rows keep pointing at it, it disappears from every list and can never
  be assigned again.

Changes apply on each member's next request — access re-reads the role every time — and are
audited with ids and permission names only.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.errors import BadRequestError, ConflictError, ForbiddenError
from app.core.permissions import (
    JOIN_CODE_FORBIDDEN_PERMISSIONS,
    DefaultRole,
    role_allowed_via_code,
    unknown_permissions,
)
from app.models import (
    AuditAction,
    AuditLog,
    JoinCode,
    JoinCodeStatus,
    JoinRequest,
    JoinRequestStatus,
    Membership,
    ProjectMember,
    Role,
    RolePermission,
    User,
)
from app.services.access import Scope, register_scope_resolver

_DEFAULT_NAMES = frozenset(name.value.casefold() for name in DefaultRole)


def list_roles(db: Session, workspace_id: uuid.UUID) -> list[Role]:
    """Default roles first, then the workspace's live custom roles, each group by name."""
    return list(
        db.scalars(
            select(Role)
            .where(
                Role.workspace_id.is_(None)
                | ((Role.workspace_id == workspace_id) & Role.deleted_at.is_(None))
            )
            .options(selectinload(Role.permissions))
            .order_by(Role.is_default.desc(), Role.name)
        )
    )


def grantable_by_join_code(role: Role) -> bool:
    """May a join code hand out this role? Decided on permissions, so custom roles count too."""
    return role_allowed_via_code(role.permission_names)


def _check_permissions(permissions: set[str], held_by_author: frozenset[str]) -> None:
    unknown = unknown_permissions(permissions)
    if unknown:
        raise BadRequestError(
            f"Unknown permissions: {', '.join(unknown)}", code="unknown_permission"
        )
    if "workspace.manage" in permissions:
        raise ConflictError(
            "Only the Owner role can manage the workspace", code="ownership_not_grantable"
        )
    beyond = sorted(permissions - held_by_author)
    if beyond:
        raise ForbiddenError(f"You cannot grant permissions you do not hold: {', '.join(beyond)}")


def _workspace_of(role: Role) -> uuid.UUID:
    if role.workspace_id is None:  # /roles/{id} never resolves a default role; defensive
        raise ForbiddenError("Default roles cannot be changed")
    return role.workspace_id


def _check_name(name: str) -> str:
    cleaned = name.strip()
    if cleaned.casefold() in _DEFAULT_NAMES:
        raise ConflictError("A default role already has this name")
    return cleaned


def create_role(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    actor: User,
    actor_permissions: frozenset[str],
    name: str,
    description: str | None,
    permissions: set[str],
) -> Role:
    _check_permissions(permissions, actor_permissions)
    role = Role(
        workspace_id=workspace_id,
        name=_check_name(name),
        description=description,
        is_default=False,
        permissions=[RolePermission(permission=p) for p in sorted(permissions)],
    )
    try:
        with db.begin_nested():
            db.add(role)
            db.flush()
    except IntegrityError:
        raise ConflictError("This workspace already has a role with this name") from None
    _audit(db, workspace_id, actor, AuditAction.ROLE_CREATED, role, permissions=permissions)
    db.commit()
    return role


def update_role(
    db: Session,
    *,
    role: Role,
    actor: User,
    actor_permissions: frozenset[str],
    name: str | None = None,
    description: str | None = None,
    permissions: set[str] | None = None,
) -> Role:
    workspace_id = _workspace_of(role)
    if name is not None:
        role.name = _check_name(name)
    if description is not None:
        role.description = description or None
    if permissions is not None:
        # Removing permissions the author lacks is fine; adding them is not.
        _check_permissions(permissions - role.permission_names, actor_permissions)
        gains_privilege = not JOIN_CODE_FORBIDDEN_PERMISSIONS.isdisjoint(permissions)
        if gains_privilege and _active_codes(db, role.id):
            raise ConflictError(
                "An active join code grants this role; revoke it before adding "
                "workspace-management permissions",
                code="role_granted_by_code",
            )
        current = {grant.permission: grant for grant in role.permissions}
        for removed in set(current) - permissions:
            role.permissions.remove(current[removed])
        for added in sorted(permissions - set(current)):
            role.permissions.append(RolePermission(permission=added))
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError:
        raise ConflictError("This workspace already has a role with this name") from None
    _audit(
        db,
        workspace_id,
        actor,
        AuditAction.ROLE_UPDATED,
        role,
        permissions=role.permission_names if permissions is not None else None,
    )
    db.commit()
    db.refresh(role)
    return role


def role_usage(db: Session, role_id: uuid.UUID) -> dict[str, int]:
    """Who still holds the role right now — each count must be 0 before it can be deleted."""
    return {
        "members": _count(
            db,
            select(func.count())
            .select_from(Membership)
            .where(Membership.role_id == role_id, Membership.ended_at.is_(None)),
        ),
        "project_overrides": _count(
            db,
            select(func.count())
            .select_from(ProjectMember)
            .where(ProjectMember.role_override_id == role_id),
        ),
        "join_codes": _active_codes(db, role_id),
        "join_requests": _count(
            db,
            select(func.count())
            .select_from(JoinRequest)
            .where(JoinRequest.role_id == role_id, JoinRequest.status == JoinRequestStatus.PENDING),
        ),
    }


def delete_role(db: Session, *, role: Role, actor: User) -> None:
    workspace_id = _workspace_of(role)
    usage = role_usage(db, role.id)
    if any(usage.values()):
        held = ", ".join(f"{n} {what.replace('_', ' ')}" for what, n in usage.items() if n)
        raise ConflictError(
            f"This role is still in use ({held}); reassign them first", code="role_in_use"
        )
    role.deleted_at = datetime.now(UTC)
    _audit(db, workspace_id, actor, AuditAction.ROLE_DELETED, role)
    db.commit()


def _count(db: Session, statement: Select[int]) -> int:
    return db.scalar(statement) or 0


def _active_codes(db: Session, role_id: uuid.UUID) -> int:
    return _count(
        db,
        select(func.count())
        .select_from(JoinCode)
        .where(
            JoinCode.role_id == role_id,
            JoinCode.status == JoinCodeStatus.ACTIVE,
            JoinCode.expires_at > func.now(),
        ),
    )


def _audit(
    db: Session,
    workspace_id: uuid.UUID,
    actor: User,
    action: AuditAction,
    role: Role,
    *,
    permissions: set[str] | frozenset[str] | None = None,
) -> None:
    details: dict[str, object] = {"role_id": str(role.id)}
    if permissions is not None:
        details["permissions"] = sorted(permissions)
    db.add(AuditLog(workspace_id=workspace_id, actor_id=actor.id, action=action, details=details))


def get_custom_role(db: Session, role_id: uuid.UUID) -> Role | None:
    return db.scalar(
        select(Role)
        .where(Role.id == role_id, Role.workspace_id.is_not(None), Role.deleted_at.is_(None))
        .options(selectinload(Role.permissions))
    )


def _role_scope(db: Session, role_id: uuid.UUID) -> Scope | None:
    """``/roles/{role_id}`` addresses live custom roles only: defaults and deleted roles are 404."""
    role = get_custom_role(db, role_id)
    return None if role is None or role.workspace_id is None else Scope(role.workspace_id)


register_scope_resolver("role_id", _role_scope)
