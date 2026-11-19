"""Quality dashboard API (Parth — US-13 aggregation, FR-27, FR-28, FR-42, NFR-16).

* ``GET /projects/{p}/analytics`` — the project dashboard's counts, with optional filters
  (``requirement``, ``req_type``, ``group``, ``owner``, ``state``, ``priority``). The answer also
  carries ``suggested_filters``: role-appropriate defaults (NFR-16) — someone who does not manage
  the baseline starts on their own requirements; the UI applies them unless the member clears
  them.
* ``GET /workspaces/{w}/analytics`` — each project's headline numbers and their totals.

Read-only, ``view``. The counts are the rows the lists show (``app.services.analytics``).
"""

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.deps import DbSession, requires
from app.core.errors import NotFoundError
from app.models import Project, RequirementState
from app.schemas.common import ErrorResponse
from app.services import analytics
from app.services.access import AccessContext

router = APIRouter(tags=["analytics"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
}


@router.get(
    "/projects/{project_id}/analytics",
    summary="The project's quality dashboard counts",
    responses=_ERRORS,
)
def project_analytics(
    project_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
    requirement: uuid.UUID | None = None,
    req_type: Annotated[
        Literal["functional", "non_functional", "constraint"] | None, Query()
    ] = None,
    group: Annotated[str | None, Query(max_length=120)] = None,
    owner: uuid.UUID | None = None,
    state: RequirementState | None = None,
    priority: Annotated[Literal["must", "should", "could", "wont"] | None, Query()] = None,
) -> dict[str, Any]:
    project = db.get(Project, project_id)
    if project is None:  # defensive
        raise NotFoundError("Project not found")
    filters = analytics.Filters(
        requirement_id=requirement,
        req_type=req_type,
        stakeholder_group=group,
        owner_id=owner,
        state=state,
        priority=priority,
    )
    board = analytics.project_dashboard(db, project, filters)
    board["suggested_filters"] = {} if ctx.can("baseline.manage") else {"owner": str(ctx.user.id)}
    return board


@router.get(
    "/workspaces/{workspace_id}/analytics",
    summary="Every project's headline numbers",
    responses=_ERRORS,
)
def workspace_analytics(
    workspace_id: uuid.UUID, ctx: Annotated[AccessContext, requires("view")], db: DbSession
) -> dict[str, Any]:
    projects = list(
        db.scalars(
            select(Project).where(Project.workspace_id == workspace_id).order_by(Project.name)
        )
    )
    return analytics.workspace_dashboard(db, projects)
