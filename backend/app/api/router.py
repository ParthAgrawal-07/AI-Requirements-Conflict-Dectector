"""Versioned API router (Role 5).

Every router except ``auth`` is mounted with ``get_current_user`` as a *router-level*
dependency, so any endpoint a teammate adds later is authenticated by default (FR-37). Add
``Depends(require_roles(...))`` on individual routes for role restrictions.
"""

from typing import Any

from fastapi import APIRouter, Depends

from app.api import auth, documents, findings, reports, requirements
from app.core.auth import get_current_user
from app.schemas.common import ErrorResponse

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth.router)  # /auth/login must stay public

_authenticated = [Depends(get_current_user)]
_unauthorized: dict[int | str, dict[str, Any]] = {401: {"model": ErrorResponse}}

api_router.include_router(
    documents.router,
    prefix="/documents",
    tags=["documents"],
    dependencies=_authenticated,
    responses=_unauthorized,
)
api_router.include_router(
    requirements.router,
    prefix="/requirements",
    tags=["requirements"],
    dependencies=_authenticated,
    responses=_unauthorized,
)
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
