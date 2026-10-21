"""Membership service (Parth — US-27, FR-43, FR-45, FR-46, SX-06).

``add_member`` is the one place a membership is created: workspace creation (the Owner), joining
with a code (Madhav's ``join_codes.redeem``, Sprint 1) and approved join requests all go
through it, so the rules below hold everywhere:

* at most one *active* membership per (user, workspace) — enforced here and by a partial
  unique index;
* the role must be a platform default or belong to the same workspace;
* every addition is audited, with identifiers only (CR-04);
* a join code never grants a privileged role (``via_join_code=True`` — see below).

``change_role`` / ``remove_member`` / leaving belong to US-26 (Sprint 2) and are added there.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.errors import ConflictError, NotFoundError
from app.core.permissions import (
    WORKSPACE_LEVEL_ONLY_PERMISSIONS,
    DefaultRole,
    role_allowed_via_code,
)
from app.models import AuditAction, AuditLog, Membership, Project, ProjectMember, Role, User
from app.services.access import active_membership

__all__ = [
    "active_membership",
    "add_member",
    "add_project_member",
    "ensure_role_allowed_via_code",
    "get_default_role",
    "get_role",
    "list_active_memberships",
]


def get_default_role(db: Session, name: DefaultRole) -> Role:
    """A platform default role by name. For *assigning* roles only — never for authorisation."""
    role = db.scalar(select(Role).where(Role.workspace_id.is_(None), Role.name == name.value))
    if role is None:  # the seed migration did not run: a deployment error, not a client error
        raise RuntimeError(f"Default role {name.value!r} is missing — run `alembic upgrade head`")
    return role


def get_role(db: Session, workspace_id: uuid.UUID, role_id: uuid.UUID) -> Role:
    """A role a membership in ``workspace_id`` may have: a default role or one of its own."""
    role = db.scalar(
        select(Role).where(
            Role.id == role_id,
            (Role.workspace_id.is_(None)) | (Role.workspace_id == workspace_id),
        )
    )
    if role is None:
        raise NotFoundError("Role not found")
    return role


def ensure_role_allowed_via_code(role: Role) -> None:
    """Refuse a role a join code must never grant (FR-44, SX-14, NFR-35).

    Decided on the role's **permissions**, so a custom role with ``roles.manage`` or
    ``workspace.manage`` is refused exactly like Owner and Admin.
    """
    if not role_allowed_via_code(role.permission_names):
        raise ConflictError("A join code can never grant this role")


def list_active_memberships(db: Session, user_id: uuid.UUID) -> list[Membership]:
    """The user's active memberships, oldest first, with workspace and role loaded."""
    return list(
        db.scalars(
            select(Membership)
            .where(Membership.user_id == user_id, Membership.ended_at.is_(None))
            .options(joinedload(Membership.workspace), joinedload(Membership.role))
            .order_by(Membership.joined_at, Membership.id)
        ).unique()
    )


def add_member(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    role_id: uuid.UUID,
    stakeholder_group: str | None = None,
    actor_id: uuid.UUID | None = None,
    via_join_code: bool = False,
    commit: bool = True,
) -> Membership:
    """Make ``user_id`` an active member of the workspace with the given role.

    ``actor_id`` is who caused it (the inviter, or the user themself when joining); it defaults
    to the new member. Raises :class:`ConflictError` if they are already a member.
    ``via_join_code=True`` **must** be passed by the join-code service: it refuses privileged
    roles (Owner, Admin and anything with their permissions). ``commit=False`` flushes only, for
    callers (sign-up) that must stay atomic with other writes.
    """
    role = get_role(db, workspace_id, role_id)
    if via_join_code:
        ensure_role_allowed_via_code(role)
    if active_membership(db, user_id, workspace_id) is not None:
        raise ConflictError("The user is already a member of this workspace")

    membership = Membership(
        user_id=user_id,
        workspace_id=workspace_id,
        role_id=role.id,
        stakeholder_group=stakeholder_group,
    )
    try:
        with db.begin_nested():
            db.add(membership)
            db.flush()
    except IntegrityError:  # lost a race with a concurrent join: the unique index held
        raise ConflictError("The user is already a member of this workspace") from None

    db.add(
        AuditLog(
            workspace_id=workspace_id,
            actor_id=actor_id or user_id,
            action=AuditAction.MEMBER_ADDED,
            details={"user_id": str(user_id), "role_id": str(role.id)},
        )
    )
    if commit:
        db.commit()
    else:
        db.flush()
    return membership


def add_project_member(
    db: Session,
    *,
    project: Project,
    user: User,
    role_override_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
    via_join_code: bool = False,
    commit: bool = True,
) -> ProjectMember:
    """List ``user`` on the project team, optionally with a project-level role (FR-79).

    * The user must be an **active member of the project's workspace** — a project team is a
      subset of the workspace, never a way in.
    * ``role_override_id`` must be a default role or one of *this* workspace's custom roles, can
      never carry ``workspace.manage`` (ownership is not per-project), and with
      ``via_join_code=True`` can never be a privileged role. Who may *choose* an override, and the
      "never above the PM's own permissions" limit, is the caller's rule (``PUT
      /projects/{p}/members/{u}``, Sprint 2); this function only guarantees a valid role.
    * Idempotent: an existing team entry is returned unchanged unless a *different* override is
      given. Every change is audited with identifiers only (CR-04).
    """
    if active_membership(db, user.id, project.workspace_id) is None:
        raise NotFoundError("This user is not a member of the workspace")

    role: Role | None = None
    if role_override_id is not None:
        role = get_role(db, project.workspace_id, role_override_id)
        if not WORKSPACE_LEVEL_ONLY_PERMISSIONS.isdisjoint(role.permission_names):
            raise ConflictError("Ownership cannot be granted for a single project")
        if via_join_code:
            ensure_role_allowed_via_code(role)

    member = db.get(ProjectMember, (project.id, user.id))
    if member is not None and (role is None or member.role_override_id == role.id):
        return member  # nothing to change

    if member is None:
        member = ProjectMember(
            project_id=project.id, user_id=user.id, role_override_id=role.id if role else None
        )
        db.add(member)
    else:
        member.role_override_id = role.id if role else None

    db.add(
        AuditLog(
            workspace_id=project.workspace_id,
            actor_id=actor_id or user.id,
            action=AuditAction.PROJECT_MEMBER_SET,
            details={
                "project_id": str(project.id),
                "user_id": str(user.id),
                "role_override_id": str(role.id) if role else None,
            },
        )
    )
    if commit:
        db.commit()
    else:
        db.flush()
    return member
