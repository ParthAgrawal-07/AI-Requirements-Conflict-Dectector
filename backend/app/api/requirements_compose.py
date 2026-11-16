"""Composer and ownership routes (Bansil — US-30, US-36; FR-55, FR-59).

* ``POST /projects/{p}/requirements`` (``req.propose``) — the composer's *Propose*: a Proposed
  requirement posted as a card in the chosen channel (default: the group's, else ``#general``),
  with its live analysis queued (``app.intake.posts``).
* ``POST /requirements/{id}/ownership-requests`` (``req.propose``) — ask to own a requirement.
* ``GET /requirements/{id}/ownership-requests`` (``view``) — its requests, oldest first.
* ``POST /ownership-requests/{id}/decision`` — accept or decline. The current owner (who holds
  ``req.propose`` as a contributor) or anyone who could reassign it (``baseline.manage``); the
  service checks which (``app.intake.ownership``).

Reassigning an owner or group directly is ``PATCH /requirements/{id}`` (``app.api.requirements``).
"""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import DbSession, requires, requires_any
from app.api.intake import RequirementPostCreate, RequirementPostRead
from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.core.rate_limit import RateLimiter, enforce, get_rate_limiter
from app.intake import ownership
from app.intake import posts as post_service
from app.models import OwnershipRequest, Project
from app.schemas.common import ErrorResponse
from app.services.access import AccessContext

router = APIRouter(tags=["composer"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse, "description": "Not a member, or no such resource"},
    409: {"model": ErrorResponse},
}


@router.post(
    "/projects/{project_id}/requirements",
    status_code=201,
    response_model=RequirementPostRead,
    summary="Propose a requirement from the composer (posted as a card, analysed live)",
    responses={**_ERRORS, 429: {"model": ErrorResponse}},
)
def propose_requirement(
    project_id: uuid.UUID,
    body: RequirementPostCreate,
    ctx: Annotated[AccessContext, requires("req.propose")],
    db: DbSession,
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> RequirementPostRead:
    project = db.get(Project, project_id)
    if project is None:  # resolved by the access layer a moment ago; defensive
        raise NotFoundError("Project not found")
    enforce(
        limiter,
        f"messages:user:{ctx.user.id}",
        limit=get_settings().messages_per_minute,
        window_seconds=60,
    )
    result = post_service.post_to_project(
        db, project=project, author=ctx.user, fields=body.fields, draft_id=body.draft_id
    )
    return RequirementPostRead.build(db, result)


class OwnershipRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str | None = Field(default=None, max_length=500)


class OwnershipDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accept: bool


class OwnershipRequestRead(BaseModel):
    id: uuid.UUID
    requirement_id: uuid.UUID
    requester_id: uuid.UUID
    status: str  # pending, accepted, declined
    note: str | None
    decided_by: uuid.UUID | None
    decided_at: datetime | None
    created_at: datetime

    @classmethod
    def from_model(cls, row: OwnershipRequest) -> "OwnershipRequestRead":
        return cls(
            id=row.id,
            requirement_id=row.requirement_id,
            requester_id=row.requester_id,
            status=row.status,
            note=row.note,
            decided_by=row.decided_by,
            decided_at=row.decided_at,
            created_at=row.created_at,
        )


@router.post(
    "/requirements/{requirement_id}/ownership-requests",
    status_code=201,
    response_model=OwnershipRequestRead,
    summary="Ask to own a requirement",
    responses=_ERRORS,
)
def request_ownership(
    requirement_id: uuid.UUID,
    body: OwnershipRequestCreate,
    ctx: Annotated[AccessContext, requires("req.propose")],
    db: DbSession,
) -> OwnershipRequestRead:
    request = ownership.request_ownership(db, ctx, requirement_id, note=body.note)
    return OwnershipRequestRead.from_model(request)


@router.get(
    "/requirements/{requirement_id}/ownership-requests",
    response_model=list[OwnershipRequestRead],
    summary="A requirement's ownership requests, oldest first",
    responses=_ERRORS,
)
def list_ownership_requests(
    requirement_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
) -> list[OwnershipRequestRead]:
    return [OwnershipRequestRead.from_model(r) for r in ownership.list_requests(db, requirement_id)]


@router.post(
    "/ownership-requests/{ownership_request_id}/decision",
    response_model=OwnershipRequestRead,
    summary="Accept or decline an ownership request (the owner or a manager)",
    responses=_ERRORS,
)
def decide_ownership_request(
    ownership_request_id: uuid.UUID,
    body: OwnershipDecision,
    ctx: Annotated[AccessContext, requires_any("req.propose", "baseline.manage")],
    db: DbSession,
) -> OwnershipRequestRead:
    request = ownership.decide(db, ctx, ownership_request_id, accept=body.accept)
    return OwnershipRequestRead.from_model(request)
