"""Access resolution (Parth — US-27, FR-38, NFR-11, NFR-27, ADR-12, ADR-20).

Given a signed-in user and the resource a request is about, answer one question: *what may this
user do here?* The answer is an :class:`AccessContext` holding the user's **effective permission
set**; ``app.core.auth.require_permission`` turns a missing permission into a 403.

Rules, in order — the order matters for what an outsider can learn:

1. **Scope.** The request's path parameters name a workspace, project, document... Each is
   resolved to the workspace (and project) it belongs to. Unknown ids are 404.
2. **Membership.** The user must have an *active* membership (``ended_at IS NULL``) in that
   workspace; otherwise the resource **does not exist** for them: 404, never 403 (ADR-12, NFR-27).
   The membership is read from the database on every request, so removing a member or changing
   their role applies on their next request.
3. **Role.** The workspace role is replaced by the project-level override (``project_members.
   role_override_id``, FR-79) when the request is about a project and one exists.
4. **Permissions.** The role's permission names (never the role name itself).

Other modules add their own path parameters (``channel_id``, ``issue_id``,
``change_request_id``...) with :func:`register_scope_resolver` when their tables exist.
"""

import logging
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from fastapi.exceptions import RequestValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import NotFoundError
from app.models import (
    Document,
    Membership,
    Project,
    ProjectMember,
    Requirement,
    Role,
    User,
    Workspace,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Scope:
    """The tenant a request is about. ``project_id`` is None for workspace-level resources."""

    workspace_id: uuid.UUID
    project_id: uuid.UUID | None = None


@dataclass(frozen=True)
class AccessContext:
    """What the caller may do in the scope of this request (immutable, built per request)."""

    user: User
    workspace_id: uuid.UUID
    project_id: uuid.UUID | None
    membership: Membership
    role: Role  # the *effective* role: the project override if there is one
    permissions: frozenset[str]
    # Permissions held for protected requirements only (spec §1.22, e.g. Compliance Reviewer's
    # ``finding.review``). The caller of the guarded action enforces the "protected" part.
    protected_only: frozenset[str]

    def can(self, permission: str, *, protected_requirement: bool = False) -> bool:
        """Does the caller hold ``permission`` *for this action*?

        Safe by default: a permission held for **protected requirements only** (the Compliance
        Reviewer's ``finding.review``) answers ``False`` unless the caller says the action is
        about a protected requirement (``protected_requirement=True``). A handler that acts on a
        particular requirement therefore passes ``requirement.is_protected`` and cannot forget the
        restriction by merely calling ``ctx.can(...)``.
        """
        if permission not in self.permissions:
            return False
        return protected_requirement or permission not in self.protected_only


ScopeResolver = Callable[[Session, uuid.UUID], Scope | None]


# ── scope resolvers: one per path parameter name ────────────────────────────────────────────
def _workspace_scope(db: Session, workspace_id: uuid.UUID) -> Scope | None:
    return Scope(workspace_id) if db.get(Workspace, workspace_id) is not None else None


def _project_scope(db: Session, project_id: uuid.UUID) -> Scope | None:
    project = db.get(Project, project_id)
    return None if project is None else Scope(project.workspace_id, project.id)


def _document_scope(db: Session, document_id: uuid.UUID) -> Scope | None:
    row = db.execute(
        select(Document.workspace_id, Document.project_id).where(Document.id == document_id)
    ).first()
    return None if row is None else Scope(row[0], row[1])


def _requirement_scope(db: Session, requirement_id: uuid.UUID) -> Scope | None:
    row = db.execute(
        select(Project.workspace_id, Requirement.project_id)
        .join(Project, Project.id == Requirement.project_id)
        .where(Requirement.id == requirement_id)
    ).first()
    return None if row is None else Scope(row[0], row[1])


SCOPE_RESOLVERS: dict[str, ScopeResolver] = {
    "workspace_id": _workspace_scope,
    "project_id": _project_scope,
    "document_id": _document_scope,
    "requirement_id": _requirement_scope,
}


def register_scope_resolver(param_name: str, resolver: ScopeResolver) -> None:
    """Teach ``require_permission`` how to find the tenant of a new kind of resource.

    Call at import time from the module that owns the table, e.g. Madhav's channels::

        register_scope_resolver("channel_id", lambda db, channel_id: ...)

    The resolver returns the resource's :class:`Scope`, or ``None`` if it does not exist.
    """
    if param_name in SCOPE_RESOLVERS and SCOPE_RESOLVERS[param_name] is not resolver:
        raise ValueError(f"A scope resolver for {param_name!r} is already registered")
    SCOPE_RESOLVERS[param_name] = resolver


def resolve_scope(db: Session, path_params: Mapping[str, object]) -> Scope:
    """Resolve every known path parameter and make sure they all agree on one tenant.

    A malformed id is a 422 (as FastAPI would report it for the route's own parameter); an id
    that does not exist, or ids from different workspaces/projects, are a 404.
    """
    scopes: list[Scope] = []
    for name, raw in path_params.items():
        resolver = SCOPE_RESOLVERS.get(name)
        if resolver is None:
            continue
        try:
            value = raw if isinstance(raw, uuid.UUID) else uuid.UUID(str(raw))
        except ValueError:
            raise RequestValidationError(
                [
                    {
                        "loc": ("path", name),
                        "msg": "Input should be a valid UUID",
                        "type": "uuid_parsing",
                    }
                ]
            ) from None
        scope = resolver(db, value)
        if scope is None:
            raise NotFoundError()
        scopes.append(scope)

    if not scopes:
        # A programming error, not a client error: a route declared a permission but has no
        # path parameter the access layer understands. Fail loudly in development and tests.
        raise RuntimeError(
            "require_permission() used on a route without a workspace, project or other "
            "registered resource path parameter — use authenticated_only() instead"
        )

    workspace_ids = {scope.workspace_id for scope in scopes}
    project_ids = {scope.project_id for scope in scopes if scope.project_id is not None}
    if len(workspace_ids) != 1 or len(project_ids) > 1:
        raise NotFoundError()  # ids from different tenants: nothing is there
    return Scope(workspace_ids.pop(), project_ids.pop() if project_ids else None)


# ── memberships and effective roles ─────────────────────────────────────────────────────────
def active_membership(
    db: Session, user_id: uuid.UUID, workspace_id: uuid.UUID
) -> Membership | None:
    """The user's active membership in a workspace, with its role and permissions loaded.

    ``populate_existing`` re-reads the row even if this session already holds it, so a role
    change made moments ago can never be masked by a stale identity-map entry.
    """
    return db.scalar(
        select(Membership)
        .where(
            Membership.user_id == user_id,
            Membership.workspace_id == workspace_id,
            Membership.ended_at.is_(None),
        )
        .options(selectinload(Membership.role).selectinload(Role.permissions))
        .execution_options(populate_existing=True)
    )


def _project_role_override(db: Session, user_id: uuid.UUID, project_id: uuid.UUID) -> Role | None:
    return db.scalar(
        select(Role)
        .join(ProjectMember, ProjectMember.role_override_id == Role.id)
        .where(ProjectMember.project_id == project_id, ProjectMember.user_id == user_id)
        .options(selectinload(Role.permissions))
        .execution_options(populate_existing=True)
    )


def build_access_context(db: Session, user: User, scope: Scope) -> AccessContext:
    """Build the caller's :class:`AccessContext`, or raise 404 if they are not a member."""
    membership = active_membership(db, user.id, scope.workspace_id)
    if membership is None:
        # Not a member (or removed): the tenant's resources do not exist for this user.
        raise NotFoundError()

    role = membership.role
    if scope.project_id is not None:
        override = _project_role_override(db, user.id, scope.project_id)
        if override is not None:
            role = override

    grants = role.permissions
    return AccessContext(
        user=user,
        workspace_id=scope.workspace_id,
        project_id=scope.project_id,
        membership=membership,
        role=role,
        permissions=frozenset(grant.permission for grant in grants),
        protected_only=frozenset(grant.permission for grant in grants if grant.protected_only),
    )
