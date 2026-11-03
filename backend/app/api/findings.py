"""Finding routes (Keval — US-07). Reading needs ``view``; reviewing findings is US-10 (Sprint 3)."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query

from app.api.deps import DbSession, requires
from app.core.errors import NotFoundError
from app.models import FindingCategory, FindingStatus, Project
from app.schemas.common import ErrorResponse, Page
from app.schemas.findings import FindingRead
from app.services import findings as finding_service
from app.services.access import AccessContext

router = APIRouter(tags=["findings"])

_NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Not a member, or no such finding"}
}


@router.get(
    "/projects/{project_id}/findings",
    response_model=Page[FindingRead],
    summary="The project's findings with confidence, explanation and the requirements involved",
    responses=_NOT_FOUND,
)
def list_findings(
    project_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
    category: Annotated[FindingCategory | None, Query()] = None,
    status: Annotated[FindingStatus | None, Query()] = None,
    requirement: Annotated[uuid.UUID | None, Query(description="Findings about this one")] = None,
    low_confidence: Annotated[bool | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[FindingRead]:
    project = db.get(Project, project_id)
    if project is None:  # cannot happen after require_permission; defensive
        raise NotFoundError("Project not found")
    views, total = finding_service.list_findings(
        db,
        project,
        category=category,
        status=status,
        requirement_id=requirement,
        low_confidence=low_confidence,
        limit=limit,
        offset=offset,
    )
    return Page[FindingRead](
        items=[FindingRead.from_view(v) for v in views], total=total, limit=limit, offset=offset
    )


@router.get(
    "/findings/{finding_id}",
    response_model=FindingRead,
    summary="One finding",
    responses=_NOT_FOUND,
)
def get_finding(
    finding_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
) -> FindingRead:
    view = finding_service.get_finding(db, finding_id, ctx.user, ctx.workspace_id)
    return FindingRead.from_view(view)
