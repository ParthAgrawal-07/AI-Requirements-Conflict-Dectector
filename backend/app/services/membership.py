"""Membership service (Parth — US-27, FR-43, FR-45, FR-46, SX-06).

``add_member`` is the one place a membership is created: workspace creation (the Owner), joining
with a code (Madhav's ``join_codes.redeem``, Sprint 1) and approved join requests all go
through it, so the rules below hold everywhere:

* at most one *active* membership per (user, workspace) — enforced here and by a partial
  unique index;
* the role must be a platform default or belong to the same workspace;
* every addition is audited, with identifiers only (CR-04);
* a join code never grants a privileged role (``via_join_code=True`` — see below).

Sprint 2 adds the US-26/US-49 changes: :func:`change_role`, :func:`remove_member`, :func:`leave`
and :func:`set_project_role`. Each checks, in this order: the target is an active member (else 404);
the caller may hand out both the old and the new role (``app.core.permissions.may_assign``, else
403); the workspace keeps at least one Owner (else 409 ``last_owner``). Removal and leaving end the
membership (history stays), drop the person's project-team rows and private-channel listings, and
close their open sockets via a ``membership.revoked`` event published after the commit.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.core.permissions import (
    WORKSPACE_LEVEL_ONLY_PERMISSIONS,
    DefaultRole,
    may_assign,
    role_allowed_via_code,
)
from app.models import (
    AuditAction,
    AuditLog,
    Channel,
    ChannelMember,
    Membership,
    Project,
    ProjectMember,
    Requirement,
    Role,
    RolePermission,
    User,
)
from app.realtime import bus
from app.realtime.events import membership_revoked
from app.services.access import AccessContext, active_membership

__all__ = [
    "active_membership",
    "add_member",
    "add_project_member",
    "change_role",
    "ensure_role_allowed_via_code",
    "get_default_role",
    "get_role",
    "leave",
    "list_active_memberships",
    "list_members",
    "list_project_members",
    "needs_reassignment",
    "remove_member",
    "set_project_role",
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
            Role.deleted_at.is_(None),  # a deleted custom role is never assigned again
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


# ── US-26: members, role changes, removal, leaving ──────────────────────────────────────────
@dataclass(frozen=True)
class ReassignmentItem:
    """A requirement still owned by someone who is no longer a member (SX-11)."""

    requirement_id: uuid.UUID
    project_id: uuid.UUID
    label: str | None
    former_owner_id: uuid.UUID
    former_owner_name: str


def list_members(db: Session, workspace_id: uuid.UUID) -> list[Membership]:
    """Active members with user and role loaded, by name."""
    return list(
        db.scalars(
            select(Membership)
            .join(User, User.id == Membership.user_id)
            .where(Membership.workspace_id == workspace_id, Membership.ended_at.is_(None))
            .options(joinedload(Membership.user), joinedload(Membership.role))
            .order_by(User.full_name, User.id)
        ).unique()
    )


def _target(db: Session, workspace_id: uuid.UUID, user_id: uuid.UUID) -> Membership:
    membership = active_membership(db, user_id, workspace_id)
    if membership is None:
        raise NotFoundError("This person is not a member of the workspace")
    return membership


def _ensure_may_assign(ctx: AccessContext, role: Role) -> None:
    if not may_assign(ctx.permissions, role.permission_names):
        raise ForbiddenError(f"You cannot give out or take away the role {role.name!r}")


def _owner_count(db: Session, workspace_id: uuid.UUID) -> int:
    """Active members holding ``workspace.manage``. The rows are locked so two Owners cannot
    remove each other at the same moment and leave the workspace without one."""
    owners = db.scalars(
        select(Membership.id)
        .join(RolePermission, RolePermission.role_id == Membership.role_id)
        .where(
            Membership.workspace_id == workspace_id,
            Membership.ended_at.is_(None),
            RolePermission.permission == "workspace.manage",
        )
        .with_for_update(of=Membership)
    ).all()
    return len(owners)


def _ensure_not_last_owner(db: Session, membership: Membership, *, keeps: Role | None) -> None:
    """Refuse a change that would leave the workspace without an Owner (FR-49)."""
    if "workspace.manage" not in membership.role.permission_names:
        return
    if keeps is not None and "workspace.manage" in keeps.permission_names:
        return
    if _owner_count(db, membership.workspace_id) <= 1:
        raise ConflictError(
            "The workspace needs another Owner first: make someone else Owner, then try again",
            code="last_owner",
        )


def change_role(
    db: Session, *, ctx: AccessContext, user_id: uuid.UUID, role_id: uuid.UUID
) -> Membership:
    """Give a member another workspace role. Applies on their next request."""
    membership = _target(db, ctx.workspace_id, user_id)
    role = get_role(db, ctx.workspace_id, role_id)
    if role.id == membership.role_id:
        return membership
    _ensure_may_assign(ctx, membership.role)
    _ensure_may_assign(ctx, role)
    _ensure_not_last_owner(db, membership, keeps=role)
    previous = membership.role_id
    membership.role_id = role.id
    db.add(
        AuditLog(
            workspace_id=ctx.workspace_id,
            actor_id=ctx.user.id,
            action=AuditAction.MEMBER_ROLE_CHANGED,
            details={
                "user_id": str(user_id),
                "from_role_id": str(previous),
                "to_role_id": str(role.id),
            },
        )
    )
    db.commit()
    db.refresh(membership, ["role"])
    return membership


def _end(db: Session, membership: Membership) -> None:
    """End a membership. History stays; project-team rows and private-channel listings go, so
    rejoining later never brings back elevated access."""
    membership.ended_at = datetime.now(UTC)
    projects = select(Project.id).where(Project.workspace_id == membership.workspace_id)
    db.execute(
        delete(ProjectMember).where(
            ProjectMember.user_id == membership.user_id, ProjectMember.project_id.in_(projects)
        )
    )
    channels = select(Channel.id).where(Channel.project_id.in_(projects))
    db.execute(
        delete(ChannelMember).where(
            ChannelMember.user_id == membership.user_id, ChannelMember.channel_id.in_(channels)
        )
    )


def remove_member(db: Session, *, ctx: AccessContext, user_id: uuid.UUID) -> None:
    """Remove someone from the workspace (US-26). Their content stays, attributed to a former
    member; their sockets close; every later request of theirs is a 404."""
    if user_id == ctx.user.id:
        raise ConflictError("To remove yourself, leave the workspace", code="use_leave")
    membership = _target(db, ctx.workspace_id, user_id)
    _ensure_may_assign(ctx, membership.role)
    _ensure_not_last_owner(db, membership, keeps=None)
    _end(db, membership)
    db.add(
        AuditLog(
            workspace_id=ctx.workspace_id,
            actor_id=ctx.user.id,
            action=AuditAction.MEMBER_REMOVED,
            details={"user_id": str(user_id), "role_id": str(membership.role_id)},
        )
    )
    db.commit()
    bus.publish(membership_revoked(workspace_id=ctx.workspace_id, user_id=user_id))


def leave(db: Session, *, user: User, workspace_id: uuid.UUID) -> None:
    """Leave a workspace. The last Owner must hand ownership to someone else first."""
    membership = _target(db, workspace_id, user.id)
    _ensure_not_last_owner(db, membership, keeps=None)
    _end(db, membership)
    db.add(
        AuditLog(
            workspace_id=workspace_id,
            actor_id=user.id,
            action=AuditAction.MEMBER_LEFT,
            details={"user_id": str(user.id), "role_id": str(membership.role_id)},
        )
    )
    db.commit()
    bus.publish(membership_revoked(workspace_id=workspace_id, user_id=user.id))


def needs_reassignment(db: Session, workspace_id: uuid.UUID) -> list[ReassignmentItem]:
    """Requirements owned by people who left or were removed (SX-11). Change requests and
    approvals join this list when they exist (Sprint 4)."""
    still_member = (
        select(Membership.id)
        .where(
            Membership.user_id == Requirement.owner_id,
            Membership.workspace_id == workspace_id,
            Membership.ended_at.is_(None),
        )
        .exists()
    )
    rows = db.execute(
        select(
            Requirement.id,
            Requirement.project_id,
            Requirement.source_req_id,
            User.id,
            User.full_name,
        )
        .join(Project, Project.id == Requirement.project_id)
        .join(User, User.id == Requirement.owner_id)
        .where(Project.workspace_id == workspace_id, ~still_member)
        .order_by(Requirement.project_id, Requirement.order_index)
    ).all()
    return [ReassignmentItem(*row) for row in rows]


# ── US-49: project-level roles ──────────────────────────────────────────────────────────────
def list_project_members(db: Session, project: Project) -> list[ProjectMember]:
    """The project team, limited to people who are still workspace members, by name."""
    return list(
        db.scalars(
            select(ProjectMember)
            .join(User, User.id == ProjectMember.user_id)
            .join(
                Membership,
                (Membership.user_id == ProjectMember.user_id)
                & (Membership.workspace_id == project.workspace_id)
                & Membership.ended_at.is_(None),
            )
            .where(ProjectMember.project_id == project.id)
            .options(joinedload(ProjectMember.user), joinedload(ProjectMember.role_override))
            .order_by(User.full_name, User.id)
        ).unique()
    )


def set_project_role(
    db: Session,
    *,
    ctx: AccessContext,
    project: Project,
    user_id: uuid.UUID,
    role_id: uuid.UUID | None,
) -> ProjectMember:
    """Put a workspace member on the project team with a project-level role (FR-79), or with
    ``role_id=None`` with their workspace role. Never a role beyond what the caller may give out:
    a Project Manager never grants more than they hold (``may_assign``)."""
    membership = _target(db, project.workspace_id, user_id)
    member = db.get(ProjectMember, (project.id, user_id))
    current = member.role_override if member and member.role_override else membership.role
    _ensure_may_assign(ctx, current)
    role: Role | None = None
    if role_id is not None:
        role = get_role(db, project.workspace_id, role_id)
        if not WORKSPACE_LEVEL_ONLY_PERMISSIONS.isdisjoint(role.permission_names):
            raise ConflictError("Ownership cannot be granted for a single project")
        _ensure_may_assign(ctx, role)

    new_override = role.id if role else None
    if member is None:
        member = ProjectMember(project_id=project.id, user_id=user_id)
        db.add(member)
    elif member.role_override_id == new_override:
        return member
    member.role_override_id = new_override
    db.add(
        AuditLog(
            workspace_id=project.workspace_id,
            actor_id=ctx.user.id,
            action=AuditAction.PROJECT_MEMBER_SET,
            details={
                "project_id": str(project.id),
                "user_id": str(user_id),
                "role_override_id": str(new_override) if new_override else None,
            },
        )
    )
    db.commit()
    db.refresh(member)
    return member
