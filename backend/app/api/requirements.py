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
* ``POST /requirements/{id}/ownership-requests`` (``req.propose``), ``GET`` the same (``view``) and
  ``POST /ownership-requests/{id}/decision`` — ask to own a requirement; its owner or a member with
  ``baseline.manage`` decides (US-36, Bansil). Deciding admits ``baseline.manage`` or
  ``req.propose`` and ``app.intake.ownership.decide`` checks the caller owns it or may reassign.
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query
from sqlalchemy.orm import Session

from app.api.deps import DbSession, requires, requires_any
from app.core.errors import BadRequestError, NotFoundError
from app.intake import ownership
from app.models import AuditAction, AuditLog, Requirement, RequirementOrigin, RequirementState
from app.schemas.common import ErrorResponse, Page
from app.schemas.documents import RequirementRead
from app.schemas.requirements import (
    OwnershipDecision,
    OwnershipRequestCreate,
    OwnershipRequestRead,
    RequirementDetail,
    RequirementUpdate,
    SignOffRequest,
)
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
    if requirement.is_protected:
        db.add(
            AuditLog(
                workspace_id=ctx.workspace_id,
                actor_id=ctx.user.id,
                requirement_id=requirement.id,
                action=AuditAction.VIEWED_PROTECTED,
            )
        )
        db.commit()
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


@router.post(
    "/requirements/{requirement_id}/ownership-requests",
    response_model=OwnershipRequestRead,
    status_code=201,
    summary="Ask to own a requirement (US-36)",
    responses={
        **_ONE,
        403: {"model": ErrorResponse},
        409: {"model": ErrorResponse, "description": "Already the owner, or already asked"},
    },
)
def request_ownership(
    requirement_id: uuid.UUID,
    body: OwnershipRequestCreate,
    ctx: Annotated[AccessContext, requires("req.propose")],
    db: DbSession,
) -> OwnershipRequestRead:
    request = ownership.request_ownership(db, ctx, requirement_id, note=body.note)
    return OwnershipRequestRead.model_validate(request)


@router.get(
    "/requirements/{requirement_id}/ownership-requests",
    response_model=list[OwnershipRequestRead],
    summary="A requirement's ownership requests, oldest first (US-36)",
    responses=_ONE,
)
def list_ownership_requests(
    requirement_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
) -> list[OwnershipRequestRead]:
    return [
        OwnershipRequestRead.model_validate(r) for r in ownership.list_requests(db, requirement_id)
    ]


@router.post(
    "/ownership-requests/{ownership_request_id}/decision",
    response_model=OwnershipRequestRead,
    summary="Accept or decline an ownership request (US-36)",
    responses={
        404: {"model": ErrorResponse, "description": "Not a member, or no such request"},
        403: {"model": ErrorResponse, "description": "Neither the owner nor a manager"},
        409: {"model": ErrorResponse, "description": "Already decided"},
    },
)
def decide_ownership(
    ownership_request_id: uuid.UUID,
    body: OwnershipDecision,
    ctx: Annotated[AccessContext, requires_any("baseline.manage", "req.propose")],
    db: DbSession,
) -> OwnershipRequestRead:
    request = ownership.decide(db, ctx, ownership_request_id, accept=body.accept)
    return OwnershipRequestRead.model_validate(request)
