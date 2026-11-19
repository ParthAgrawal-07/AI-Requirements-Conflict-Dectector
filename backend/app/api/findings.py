"""Finding routes (Keval — US-07; Parth — US-10).

* Reading needs ``view``.
* ``POST /findings/{id}/review`` needs ``finding.review`` and admits its *protected-only* holders
  (the Compliance Reviewer): ``app.services.review_state.may_review`` then lets them act only on
  findings about protected requirements, and lets nobody else act on those (CR-19).
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query

from app.api.deps import DbSession, requires
from app.core.errors import NotFoundError
from app.models import FindingCategory, FindingStatus, Project
from app.schemas.common import ErrorResponse, Page
from app.schemas.findings import FindingRead, FindingReviewRead, ReviewRequest
from app.services import findings as finding_service
from app.services import review_state
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
    source: Annotated[
        str | None,
        Query(
            pattern=r"^(ai|rule|person)(,(ai|rule|person))*$",
            description="Who found them, comma-separated: ai, rule, person (US-56)",
        ),
    ] = None,
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
        sources=source.split(",") if source else None,
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


@router.post(
    "/findings/{finding_id}/review",
    response_model=FindingRead,
    summary="Confirm, dismiss, merge, reclassify, reopen or escalate a finding (US-10)",
    responses={
        **_NOT_FOUND,
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse, "description": "Protected: compliance reviewers only"},
        409: {"model": ErrorResponse, "description": "Not possible from the current state"},
    },
)
def review_finding(
    finding_id: uuid.UUID,
    body: ReviewRequest,
    ctx: Annotated[AccessContext, requires("finding.review", allow_protected_only=True)],
    db: DbSession,
) -> FindingRead:
    review_state.review(
        db,
        ctx,
        finding_id,
        body.action,
        reason=body.reason,
        category=body.category,
        merge_into=body.merge_into,
    )
    view = finding_service.get_finding(db, finding_id, ctx.user, ctx.workspace_id)
    return FindingRead.from_view(view)


@router.get(
    "/findings/{finding_id}/reviews",
    response_model=list[FindingReviewRead],
    summary="Every human decision on a finding, oldest first",
    responses=_NOT_FOUND,
)
def list_reviews(
    finding_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
) -> list[FindingReviewRead]:
    return [FindingReviewRead.from_model(r) for r in review_state.reviews_of(db, ctx, finding_id)]
