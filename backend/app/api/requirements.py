"""Requirement routes (Parth — US-04, US-37).

* ``GET /projects/{p}/requirements`` is the data behind the requirements screen: paginated and
  searchable, with the printed document ID (``REQ-n``), text, state, owner and origin, filterable
  by ``state``, ``origin``, ``owner``, ``document_id`` and a free-text ``q`` (case-insensitive,
  over text and printed ID).
* ``GET /requirements/{id}`` (``view``) — the drawer: detail, allowed moves, approval readiness.
* ``PATCH /requirements/{id}`` — a lifecycle move (US-37). Different moves need different
  permissions (``baseline.manage``, ``req.implement``, or ``req.propose`` for the author's
  withdrawal), so the route admits any of them and ``app.services.lifecycle`` checks the one the
  requested move needs.
* ``POST /requirements/{id}/signoff`` (``protected.signoff``) — sign off a protected requirement's
  current text (FR-21).
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query
from sqlalchemy.orm import Session

from app.api.deps import DbSession, requires, requires_any
from app.core.errors import BadRequestError, NotFoundError
from app.models import Requirement, RequirementOrigin, RequirementState
from app.schemas.common import ErrorResponse, Page
from app.schemas.documents import RequirementRead
from app.schemas.requirements import RequirementDetail, RequirementUpdate, SignOffRequest
from app.services import lifecycle
from app.services import requirements as requirement_service
from app.services.access import AccessContext

router = APIRouter(tags=["requirements"])


@router.get(
    "/projects/{project_id}/requirements",
    response_model=Page[RequirementRead],
    summary="List a project's requirements",
    responses={404: {"model": ErrorResponse, "description": "Not a member, or no such project"}},
)
def list_requirements(
    project_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
    q: Annotated[
        str | None, Query(max_length=200, description="Case-insensitive search in ID and text")
    ] = None,
    state: Annotated[
        RequirementState | None, Query(description="Filter by lifecycle state")
    ] = None,
    origin: Annotated[RequirementOrigin | None, Query(description="Filter by origin")] = None,
    owner: Annotated[uuid.UUID | None, Query(description="Filter by owner user id")] = None,
    document_id: Annotated[uuid.UUID | None, Query(description="Only this document's")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[RequirementRead]:
    requirements, total = requirement_service.list_requirements(
        db,
        project_id,
        query=q,
        state=state,
        origin=origin,
        owner_id=owner,
        document_id=document_id,
        limit=limit,
        offset=offset,
    )
    return Page[RequirementRead](
        items=[RequirementRead.from_model(item) for item in requirements],
        total=total,
        limit=limit,
        offset=offset,
    )


def _detail(db: Session, ctx: AccessContext, requirement_id: uuid.UUID) -> RequirementDetail:
    requirement = db.get(Requirement, requirement_id)
    if requirement is None:
        raise NotFoundError("Requirement not found")
    db.refresh(requirement)
    return RequirementDetail.build(
        requirement,
        allowed=lifecycle.allowed_moves(db, ctx, requirement),
        readiness=lifecycle.readiness(db, requirement),
        transitions=lifecycle.history(db, requirement.id),
    )


_ONE: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Not a member, or no such requirement"}
}


@router.get(
    "/requirements/{requirement_id}",
    response_model=RequirementDetail,
    summary="One requirement with its allowed moves and approval readiness",
    responses=_ONE,
)
def get_requirement(
    requirement_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
) -> RequirementDetail:
    return _detail(db, ctx, requirement_id)


@router.patch(
    "/requirements/{requirement_id}",
    response_model=RequirementDetail,
    summary="Move a requirement through its lifecycle (US-37)",
    responses={
        **_ONE,
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        409: {
            "model": ErrorResponse,
            "description": "Illegal move, changed text, analysis not current, open High finding",
        },
    },
)
def update_requirement(
    requirement_id: uuid.UUID,
    body: RequirementUpdate,
    ctx: Annotated[AccessContext, requires_any("baseline.manage", "req.implement", "req.propose")],
    db: DbSession,
) -> RequirementDetail:
    if body.state is None or body.version is None:
        raise BadRequestError("Nothing to change", code="nothing_to_change")
    lifecycle.transition(
        db,
        ctx,
        requirement_id,
        body.state,
        version=body.version,
        reason=body.reason,
        accepted_risk=body.accepted_risk,
    )
    return _detail(db, ctx, requirement_id)


@router.post(
    "/requirements/{requirement_id}/signoff",
    response_model=RequirementDetail,
    summary="Sign off the current text of a protected requirement (FR-21)",
    responses={**_ONE, 403: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def sign_off(
    requirement_id: uuid.UUID,
    body: SignOffRequest,
    ctx: Annotated[AccessContext, requires("protected.signoff")],
    db: DbSession,
) -> RequirementDetail:
    lifecycle.sign_off(db, ctx, requirement_id, version=body.version)
    return _detail(db, ctx, requirement_id)
