"""Authentication & authorization dependencies (Parth — US-19, US-27, FR-37, FR-38, NFR-11).

Every route states, in its signature, who may call it. There are exactly four kinds of
declaration, and a test (``tests/api/test_access_invariants.py``) fails if a route has none or
more than one:

================================  =============================================================
``Depends(public_route)``         no login needed (``/auth/login``, ``/auth/signup``) — an
                                  explicit allow-list in the test keeps this from spreading
``Depends(authenticated_only)``   any signed-in user, no workspace involved (``/auth/me``,
                                  ``POST /workspaces``, ``/me/permissions``)
``require_permission("x")``       the caller needs permission ``x`` in the workspace / project
                                  the request path names
``require_any_permission(...)``   at least one of several; the handler then checks the specific
                                  one it needs (e.g. upload as baseline vs. as proposals)
================================  =============================================================

**Protected-only grants** (spec §1.22: the Compliance Reviewer's ``finding.review`` applies to
protected requirements only) are refused by ``require_permission`` **unless the route opts in**
with ``allow_protected_only=True``. A route that opts in must then check the requirement it acts
on: ``ctx.can("finding.review", protected_requirement=requirement.is_protected)``. The safe
behaviour is the default, so a forgotten check fails closed; a test keeps the list of opted-in
routes explicit.

Typical use::

    @router.post("/projects/{project_id}/documents")
    def upload(ctx: Annotated[AccessContext, Depends(require_permission("doc.upload"))]): ...

Authorisation checks **permission names**, never role names (ADR-20). The check order is fixed
by ``app.services.access``: unknown or foreign resources are 404 *before* any permission is
looked at, so a non-member cannot tell "forbidden" from "does not exist" (ADR-12, NFR-27).
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import ForbiddenError, NotAuthenticatedError
from app.core.permissions import PERMISSIONS
from app.core.security import TokenError, decode_access_token
from app.models import User
from app.services.access import AccessContext, build_access_context, resolve_scope
from app.services.users import get_user

# auto_error=False -> we raise our own error so 401s use the standard error body.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

ACCESS_ATTRIBUTE = "__access__"


@dataclass(frozen=True)
class AccessDeclaration:
    """What a route says about who may call it. Read by the invariant tests."""

    kind: Literal["public", "authenticated", "permission", "any_permission"]
    permissions: tuple[str, ...] = ()
    # True when the route admits holders of a protected-only grant and checks the requirement
    # itself. Listed explicitly in tests/api/test_access_invariants.py.
    allow_protected_only: bool = False


def _declare(function: Callable[..., object], declaration: AccessDeclaration) -> None:
    setattr(function, ACCESS_ATTRIBUTE, declaration)


def access_declaration(function: object) -> AccessDeclaration | None:
    """The declaration attached to a dependency callable, if it is one of ours."""
    declaration = getattr(function, ACCESS_ATTRIBUTE, None)
    return declaration if isinstance(declaration, AccessDeclaration) else None


# ── authentication ──────────────────────────────────────────────────────────────────────────
def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    """Resolve the bearer token to an active user, or raise 401."""
    if token is None:
        raise NotAuthenticatedError()
    try:
        payload = decode_access_token(token)
    except TokenError:
        raise NotAuthenticatedError("Invalid or expired token") from None

    user = get_user(db, payload.subject)
    if user is None or not user.is_active:
        # Same message as a bad token: don't reveal whether the account exists or was disabled.
        raise NotAuthenticatedError("Invalid or expired token")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def public_route() -> None:
    """Marks a route that deliberately needs no login. Keep the list short (see the tests)."""


_declare(public_route, AccessDeclaration("public"))


def authenticated_only(user: CurrentUser) -> User:
    """Marks a route any signed-in user may call, with no workspace involved."""
    return user


_declare(authenticated_only, AccessDeclaration("authenticated"))


# ── authorisation ───────────────────────────────────────────────────────────────────────────
def _check_known(permissions: tuple[str, ...]) -> None:
    if not permissions:
        raise ValueError("at least one permission is required")
    unknown = [name for name in permissions if name not in PERMISSIONS]
    if unknown:
        # A typo in a route would otherwise silently lock everyone out (or, worse, in).
        raise ValueError(
            f"Unknown permission(s) {unknown}: not in app.core.permissions.PERMISSIONS"
        )


def _access_for(request: Request, user: User, db: Session) -> AccessContext:
    scope = resolve_scope(db, request.path_params)
    return build_access_context(db, user, scope)


def _admits(
    context: AccessContext, permissions: tuple[str, ...], allow_protected_only: bool
) -> bool:
    return any(
        context.can(permission, protected_requirement=allow_protected_only)
        for permission in permissions
    )


def require_permission(
    permission: str, *, allow_protected_only: bool = False
) -> Callable[..., AccessContext]:
    """Build a dependency that admits only callers holding ``permission`` in the request's scope.

    Returns the caller's :class:`AccessContext` (user, workspace, project, effective permissions).
    Not a member -> 404; member without the permission -> 403.

    A permission the caller holds for **protected requirements only** does not pass unless
    ``allow_protected_only=True`` — then the handler must check the requirement (see the module
    docstring).
    """
    _check_known((permission,))

    def dependency(
        request: Request, user: CurrentUser, db: Annotated[Session, Depends(get_db)]
    ) -> AccessContext:
        context = _access_for(request, user, db)
        if not _admits(context, (permission,), allow_protected_only):
            raise ForbiddenError()
        return context

    _declare(
        dependency,
        AccessDeclaration("permission", (permission,), allow_protected_only=allow_protected_only),
    )
    return dependency


def require_any_permission(
    *permissions: str, allow_protected_only: bool = False
) -> Callable[..., AccessContext]:
    """Like :func:`require_permission`, but one of several permissions is enough.

    The handler must still check the permission its particular action needs with
    ``context.can(...)`` — this dependency only guarantees the caller holds at least one.
    """
    _check_known(permissions)

    def dependency(
        request: Request, user: CurrentUser, db: Annotated[Session, Depends(get_db)]
    ) -> AccessContext:
        context = _access_for(request, user, db)
        if not _admits(context, permissions, allow_protected_only):
            raise ForbiddenError()
        return context

    _declare(
        dependency,
        AccessDeclaration(
            "any_permission", tuple(permissions), allow_protected_only=allow_protected_only
        ),
    )
    return dependency
