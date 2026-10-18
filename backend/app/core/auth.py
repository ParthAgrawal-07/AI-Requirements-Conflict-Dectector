"""Authentication & authorization dependencies (Role 5 — US-19, FR-37, NFR-11).

Typical use in a route::

    @router.post("/documents")
    def upload(user: Annotated[User, Depends(require_roles(Role.ANALYST, Role.ADMIN))]): ...

    @router.get("/documents")
    def list_documents(user: CurrentUser): ...   # any authenticated, active user

Role capabilities (see docs/engineering/roles-and-access.md):

    analyst              upload, review/confirm/dismiss/merge findings, view dashboard
    admin                everything an analyst can + thresholds, workspace users
    compliance_reviewer  resolve findings on protected requirements, view the audit trail
    read_only            dashboard and reports only
    service              background workers / future public API

Workspace scoping (FR-38): every query for documents, requirements or findings must filter
by ``user.workspace_id``. Sprint 2 (T15) adds a shared helper; until then, do it explicitly.
"""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import ForbiddenError, NotAuthenticatedError
from app.core.security import TokenError, decode_access_token
from app.models import Role, User
from app.services.users import get_user

# auto_error=False -> we raise our own error so 401s use the standard error body.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


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


def require_roles(*allowed: Role) -> Callable[[User], User]:
    """Build a dependency that only lets users with one of ``allowed`` roles through."""
    if not allowed:
        raise ValueError("require_roles() needs at least one role")
    allowed_set = frozenset(allowed)

    def dependency(user: CurrentUser) -> User:
        if user.role not in allowed_set:
            raise ForbiddenError()
        return user

    return dependency


# Standard permission catalogue mapping permissions to authorized roles (FR-37, NFR-11)
PERMISSION_ROLE_MAP: dict[str, set[Role]] = {
    "join_codes:create": {Role.ADMIN},
    "join_codes:read": {Role.ADMIN},
    "join_codes:delete": {Role.ADMIN},
    "join_requests:read": {Role.ADMIN, Role.ANALYST, Role.READ_ONLY, Role.COMPLIANCE_REVIEWER},
    "join_requests:decide": {Role.ADMIN},
    "join_codes:redeem": {Role.ADMIN, Role.ANALYST, Role.READ_ONLY, Role.COMPLIANCE_REVIEWER},
}


def require_permission(permission: str) -> Callable[[User], User]:
    """Build a dependency that verifies the user holds the specified catalog permission."""
    allowed_roles = PERMISSION_ROLE_MAP.get(permission)
    if allowed_roles is None:
        allowed_roles = {Role.ADMIN}

    def dependency(user: CurrentUser) -> User:
        if user.role not in allowed_roles:
            raise ForbiddenError(f"Missing required permission: {permission}")
        return user

    return dependency
