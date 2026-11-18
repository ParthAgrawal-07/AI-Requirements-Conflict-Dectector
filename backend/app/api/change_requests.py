"""Change request routes (US-33 intake: Bansil; US-35 review and merge: Parth).

* ``POST /requirements/{id}/change-requests`` (``rcr.open``) — open RCR-n (``app.intake.change_intake``).
* ``GET /projects/{p}/change-requests`` (``view``) — newest first; filter by status, requirement.
* ``GET /change-requests/{id}`` (``view``) — the proposal, the text it was written against
  (``base_body``) and the current text, so the page can show both diffs.

Another workspace's change request is a 404 (NFR-27).
"""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import DbSession, requires
from app.core.errors import NotFoundError
from app.intake import change_intake
from app.models import ChangeRequest, Project, Requirement, RequirementState
from app.schemas.common import ErrorResponse, Page
from app.services.access import AccessContext, Scope, register_scope_resolver

router = APIRouter(tags=["change requests"])

ERRORS: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse, "description": "Not a member, or no such change request"},
    409: {"model": ErrorResponse},
}
Kind = Literal["modify", "deprecate"]
Status = Literal["draft", "open", "needs_update", "approved", "merged", "closed", "withdrawn"]


class UserRef(BaseModel):
    id: uuid.UUID
    full_name: str


class RequirementRef(BaseModel):
    id: uuid.UUID
    label: str | None
    state: RequirementState
    current_version: int
    is_protected: bool
    owner_id: uuid.UUID | None


class IssueRef(BaseModel):
    id: uuid.UUID
    key: str  # "ISS-3"
    title: str
    status: Literal["open", "closed"]


class ChangeRequestRead(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    number: int
    key: str  # "RCR-7"
    requirement: RequirementRef
    kind: Kind
    status: Status
    base_version: int
    proposal_revision: int
    proposed_body: str | None  # None for a deprecation
    base_body: str  # the requirement's text at base_version
    current_body: str  # its text now (differs from base_body once someone else merged)
    reason: str
    proposer: UserRef | None
    resolves: list[IssueRef]
    merged_version: int | None
    merged_at: datetime | None
    closed_at: datetime | None
    close_reason: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_view(cls, item: change_intake.ChangeRequestView) -> "ChangeRequestRead":
        cr, requirement = item.change_request, item.requirement
        return cls(
            id=cr.id,
            project_id=cr.project_id,
            number=cr.number,
            key=change_intake.key(cr),
            requirement=RequirementRef(
                id=requirement.id,
                label=requirement.source_req_id,
                state=requirement.state,
                current_version=requirement.current_version,
                is_protected=requirement.is_protected,
                owner_id=requirement.owner_id,
            ),
            kind="deprecate" if cr.kind == "deprecate" else "modify",
            status=cast(Status, cr.status),
            base_version=cr.base_version,
            proposal_revision=cr.proposal_revision,
            proposed_body=cr.proposed_body,
            base_body=item.base_body,
            current_body=requirement.body,
            reason=cr.reason,
            proposer=UserRef(id=item.proposer.id, full_name=item.proposer.full_name)
            if item.proposer
            else None,
            resolves=[
                IssueRef(
                    id=i.id,
                    key=f"ISS-{i.number}",
                    title=i.title,
                    status="closed" if i.status == "closed" else "open",
                )
                for i in item.issues
            ],
            merged_version=cr.merged_version,
            merged_at=cr.merged_at,
            closed_at=cr.closed_at,
            close_reason=cr.close_reason,
            created_at=cr.created_at,
            updated_at=cr.updated_at,
        )


class ChangeRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Kind = "modify"
    proposed_body: str | None = Field(default=None, max_length=4000)
    proposed_fields: dict[str, Any] | None = None
    reason: str = Field(min_length=3, max_length=4000)
    base_version: int | None = Field(default=None, ge=1, description="The version you read")
    resolves: list[int] = Field(default_factory=list, max_length=20, description="ISS numbers")
    draft: bool = False


def change_request_or_404(db: Session, change_request_id: uuid.UUID) -> ChangeRequest:
    change_request = db.get(ChangeRequest, change_request_id)
    if change_request is None:  # cannot happen after require_permission; defensive
        raise NotFoundError("Change request not found")
    return change_request


@router.post(
    "/requirements/{requirement_id}/change-requests",
    response_model=ChangeRequestRead,
    status_code=status.HTTP_201_CREATED,
    summary="Propose a change to a requirement (RCR-n)",
    responses=ERRORS,
)
def create_change_request(
    requirement_id: uuid.UUID,
    body: ChangeRequestCreate,
    ctx: Annotated[AccessContext, requires("rcr.open")],
    db: DbSession,
) -> ChangeRequestRead:
    requirement = db.get(Requirement, requirement_id)
    if requirement is None:  # cannot happen after require_permission; defensive
        raise NotFoundError("Requirement not found")
    change_request = change_intake.open_change_request(
        db,
        ctx,
        requirement,
        kind=body.kind,
        reason=body.reason,
        proposed_body=body.proposed_body,
        proposed_fields=body.proposed_fields,
        base_version=body.base_version,
        resolves_numbers=body.resolves,
        draft=body.draft,
    )
    return ChangeRequestRead.from_view(change_intake.view(db, change_request))


@router.get(
    "/projects/{project_id}/change-requests",
    response_model=Page[ChangeRequestRead],
    summary="The project's change requests, newest first",
    responses=ERRORS,
)
def list_change_requests(
    project_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
    status_: Annotated[Status | None, Query(alias="status")] = None,
    requirement: Annotated[uuid.UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[ChangeRequestRead]:
    views, total = change_intake.list_change_requests(
        db, project_id, status=status_, requirement_id=requirement, limit=limit, offset=offset
    )
    return Page[ChangeRequestRead](
        items=[ChangeRequestRead.from_view(v) for v in views],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/change-requests/{change_request_id}",
    response_model=ChangeRequestRead,
    summary="One change request",
    responses=ERRORS,
)
def get_change_request(
    change_request_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
) -> ChangeRequestRead:
    return ChangeRequestRead.from_view(
        change_intake.view(db, change_request_or_404(db, change_request_id))
    )


def _change_request_scope(db: Session, change_request_id: uuid.UUID) -> Scope | None:
    row = db.execute(
        select(Project.workspace_id, Project.id)
        .join(ChangeRequest, ChangeRequest.project_id == Project.id)
        .where(ChangeRequest.id == change_request_id)
    ).first()
    return None if row is None else Scope(row[0], row[1])


register_scope_resolver("change_request_id", _change_request_scope)
