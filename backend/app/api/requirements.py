"""Requirement routes (Parth — US-04, US-37).

* ``GET /projects/{p}/requirements`` is the data behind the requirements screen: paginated and
  searchable, with the printed document ID (``REQ-n``), text, state, owner and origin, filterable
  by ``state``, ``origin``, ``owner``, ``document_id`` and a free-text ``q`` (case-insensitive,
  over text and printed ID).
* ``GET /requirements/{id}`` (``view``) — the drawer: detail, allowed moves, approval readiness.
* ``PATCH /requirements/{id}`` — a lifecycle move (US-37) and/or a new owner or group (US-36,
  Bansil). Different changes need different permissions (``baseline.manage``, ``req.implement``,
  or ``req.propose`` for the author's withdrawal), so the route admits any of them and
  ``app.services.lifecycle`` / ``app.intake.ownership`` check the one the change needs.
* ``POST /requirements/{id}/signoff`` (``protected.signoff``) — sign off a protected requirement's
  current text (FR-21).
* ``GET /requirements/{id}/versions`` (``view``) — every version, newest first, with who made it
  and the change request it was merged from (US-12).
"""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import DbSession, requires, requires_any
from app.core.errors import BadRequestError, NotFoundError
from app.intake import ownership
from app.models import ChangeRequest, Requirement, RequirementOrigin, RequirementState, User
from app.schemas.common import ErrorResponse, Page
from app.schemas.documents import RequirementRead
from app.schemas.requirements import RequirementDetail, RequirementUpdate, SignOffRequest
from app.services import change_requests, compliance, lifecycle
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
    requirement = db.get(Requirement, requirement_id)
    if requirement is not None:  # Parth (US-18, NFR-13): viewing a protected one is audited
        compliance.record_view(db, ctx, requirement, "detail")
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
    sent = body.model_fields_set
    reassigning = bool(sent & {"owner_id", "stakeholder_group"})
    if (body.state is None or body.version is None) and not reassigning:
        raise BadRequestError("Nothing to change", code="nothing_to_change")
    if reassigning:
        ownership.reassign(
            db,
            ctx,
            requirement_id,
            owner_id=body.owner_id,
            set_owner="owner_id" in sent,
            group=body.stakeholder_group,
            set_group="stakeholder_group" in sent,
        )
    if body.state is None or body.version is None:
        return _detail(db, ctx, requirement_id)
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


class VersionAuthor(BaseModel):
    id: uuid.UUID
    full_name: str


class VersionChangeRequest(BaseModel):
    id: uuid.UUID
    key: str  # "RCR-7"


class RequirementVersionRead(BaseModel):
    version_no: int
    body: str
    changed_by: VersionAuthor | None  # None for the extracted first version
    changed_at: datetime
    change_request: VersionChangeRequest | None


@router.get(
    "/requirements/{requirement_id}/versions",
    response_model=list[RequirementVersionRead],
    summary="Every version of the requirement, newest first (US-12)",
    responses=_ONE,
)
def list_versions(
    requirement_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
) -> list[RequirementVersionRead]:
    requirement = db.get(Requirement, requirement_id)
    if requirement is not None:
        compliance.record_view(db, ctx, requirement, "versions")
    rows = change_requests.versions(db, requirement_id)
    authors = {
        u.id: u
        for u in db.scalars(
            select(User).where(User.id.in_({r.changed_by for r in rows if r.changed_by}))
        )
    }
    numbers = {
        c.id: c.number
        for c in db.scalars(
            select(ChangeRequest).where(
                ChangeRequest.id.in_({r.change_request_id for r in rows if r.change_request_id})
            )
        )
    }
    result = []
    for row in rows:
        author = authors.get(row.changed_by) if row.changed_by else None
        number = numbers.get(row.change_request_id) if row.change_request_id else None
        result.append(
            RequirementVersionRead(
                version_no=row.version_no,
                body=row.body_snapshot,
                changed_by=VersionAuthor(id=author.id, full_name=author.full_name)
                if author
                else None,
                changed_at=row.changed_at,
                change_request=VersionChangeRequest(id=row.change_request_id, key=f"RCR-{number}")
                if row.change_request_id and number is not None
                else None,
            )
        )
    return result
