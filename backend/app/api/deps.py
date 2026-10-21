"""Shared route dependencies and type aliases (Parth — US-27).

Routes import from here so the access pattern looks the same everywhere::

    from app.api.deps import DbSession, Access, requires

    @router.get("/projects/{project_id}/requirements")
    def list_requirements(ctx: Annotated[AccessContext, requires("view")], db: DbSession): ...

``requires("x")`` is ``Depends(require_permission("x"))``; see ``app.core.auth`` for the four
kinds of access declaration every route must have.
"""

from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.auth import (
    CurrentUser,
    authenticated_only,
    public_route,
    require_any_permission,
    require_permission,
)
from app.core.database import get_db
from app.models import User
from app.services.access import AccessContext

DbSession = Annotated[Session, Depends(get_db)]


def requires(permission: str, *, allow_protected_only: bool = False) -> Any:
    """``Depends(require_permission(permission))`` — the caller must hold ``permission``.

    Holders of a *protected-only* grant are refused unless ``allow_protected_only=True``; a route
    that sets it must check ``ctx.can(permission, protected_requirement=...)`` itself.
    """
    return Depends(require_permission(permission, allow_protected_only=allow_protected_only))


def requires_any(*permissions: str, allow_protected_only: bool = False) -> Any:
    """``Depends(require_any_permission(...))`` — at least one of ``permissions`` is enough."""
    return Depends(require_any_permission(*permissions, allow_protected_only=allow_protected_only))


# Annotated shortcuts for the two non-permission declarations.
Authenticated = Annotated[User, Depends(authenticated_only)]
PublicRoute = Depends(public_route)

__all__ = [
    "AccessContext",
    "Authenticated",
    "CurrentUser",
    "DbSession",
    "PublicRoute",
    "requires",
    "requires_any",
]
