"""Versioned API router (Role 5).

Every router except ``auth`` is mounted with ``get_current_user`` as a *router-level*
dependency, so any endpoint a teammate adds later is authenticated by default (FR-37).

On top of that, **every route must declare who may call it** (``app.core.auth``): a
``require_permission("...")`` for workspace/project resources, ``authenticated_only`` for
account-level routes, ``public_route`` for login/sign-up. ``tests/api/test_access_invariants.py``
fails if a route has none (or more than one), so a forgotten permission cannot ship.
"""

from typing import Any

from fastapi import APIRouter, Depends

from app.api import (
    auth,
    context,
    documents,
    findings,
    intake,
    me,
    projects,
    reports,
    requirements,
    workspaces,
)
from app.core.auth import get_current_user
from app.schemas.common import ErrorResponse

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth.router)  # /auth/login and /auth/signup must stay public

_authenticated = [Depends(get_current_user)]
_unauthorized: dict[int | str, dict[str, Any]] = {401: {"model": ErrorResponse}}

for _router in (
    me.router,
    workspaces.router,
    projects.router,
    context.router,
    documents.router,
    requirements.router,
    intake.router,
):
    api_router.include_router(_router, dependencies=_authenticated, responses=_unauthorized)

# Placeholders owned by later sprints; they get their own prefix and declarations when filled in.
api_router.include_router(
    findings.router,
    prefix="/findings",
    tags=["findings"],
    dependencies=_authenticated,
    responses=_unauthorized,
)
api_router.include_router(
    reports.router,
    prefix="/reports",
    tags=["reports"],
    dependencies=_authenticated,
    responses=_unauthorized,
)
