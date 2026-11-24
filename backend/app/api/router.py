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
    analysis_runs,
    analytics,
    auth,
    baselines,
    change_requests,
    change_summary,
    channels,
    clarifications,
    compliance,
    concerns,
    consequences,
    context,
    decision_rules,
    documents,
    drafts,
    findings,
    intake,
    issues,
    join_codes,
    me,
    messages,
    projects,
    reports,
    requirements,
    requirements_compose,
    roles,
    social,
    suggestions,
    workspaces,
)
from app.core.auth import get_current_user
from app.graph import api as graph_api
from app.graph import changes_api
from app.lint import api as lint_api
from app.notifications import api as notifications_api
from app.schemas.common import ErrorResponse
from app.search import similar as search_similar
from app.search import thresholds as search_thresholds

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth.router)  # /auth/login and /auth/signup must stay public

_authenticated = [Depends(get_current_user)]
_unauthorized: dict[int | str, dict[str, Any]] = {401: {"model": ErrorResponse}}

for _router in (
    me.router,
    workspaces.router,
    roles.router,
    projects.router,
    context.router,
    documents.router,
    requirements.router,
    requirements_compose.router,
    intake.router,
    drafts.router,
    join_codes.router,
    channels.router,
    messages.router,
    graph_api.router,
    findings.router,
    analysis_runs.router,
    clarifications.router,
    search_similar.router,
    issues.router,
    change_requests.router,
    concerns.router,
    consequences.router,
    lint_api.router,
    search_thresholds.router,
    suggestions.router,
    notifications_api.router,
    decision_rules.router,
    baselines.router,
    analytics.router,
    changes_api.router,
    social.router,
    change_summary.router,
    compliance.router,
):
    api_router.include_router(_router, dependencies=_authenticated, responses=_unauthorized)

# Placeholders owned by later sprints; they get their own prefix and declarations when filled in.
api_router.include_router(
    reports.router,
    prefix="/reports",
    tags=["reports"],
    dependencies=_authenticated,
    responses=_unauthorized,
)
