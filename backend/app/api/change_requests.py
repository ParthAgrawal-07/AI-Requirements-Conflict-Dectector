"""Change request routes (US-33 intake: Bansil; US-35 review and merge: Parth).

* ``POST /requirements/{id}/change-requests`` (``rcr.open``) — open RCR-n (``app.intake.change_intake``).
* ``GET /projects/{p}/change-requests`` (``view``) — newest first; filter by status, requirement.
* ``GET /change-requests/{id}`` (``view``) — the proposal, the text it was written against
  (``base_body``) and the current text, so the page can show both diffs.

* ``PATCH /change-requests/{id}`` (``rcr.open``, proposer) — edit: a new proposal revision.
* ``GET /change-requests/{id}/reviews`` (``view``), ``POST …/reviews`` (``rcr.review``),
  ``POST …/reviewers`` (``rcr.open``: the proposer, or a member who may merge).
* ``GET /change-requests/{id}/agreement`` (``view``) — mergeable now, and every unmet
  condition (the merge box).
* ``POST …/merge`` (``rcr.merge``) — **409** ``merge_blocked`` with the unmet conditions in
  ``details``; ``POST …/close`` (``rcr.merge``, with a reason); ``POST …/withdraw``
  (the proposer).

Another workspace's change request is a 404 (NFR-27). Reading a request about a protected
requirement is audited (``viewed_protected``, NFR-13), as reading the requirement itself is.
"""

import uuid
from collections.abc import Iterable
from datetime import datetime
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import DbSession, requires
from app.core.errors import NotFoundError
from app.intake import change_intake
from app.models import (
    AuditAction,
    AuditLog,
    ChangeRequest,
    Project,
    Requirement,
    RequirementState,
    User,
)
from app.schemas.common import ErrorResponse, Page
from app.services import change_requests, reviews
from app.services.access import AccessContext, Scope, register_scope_resolver
from app.services.agreement import AgreementGuard

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
    source_suggestion_id: uuid.UUID | None = None
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
            source_suggestion_id=cr.source_suggestion_id,
            created_at=cr.created_at,
            updated_at=cr.updated_at,
        )


def _has_nul(value: object) -> bool:
    """PostgreSQL stores no NUL character in ``text`` or ``jsonb``: refuse it as invalid input."""
    if isinstance(value, str):
        return "\x00" in value
    if isinstance(value, dict):
        return any(_has_nul(k) or _has_nul(v) for k, v in value.items())
    if isinstance(value, list):
        return any(_has_nul(v) for v in value)
    return False


class ChangeRequestCreate(BaseModel):
    # Whitespace is stripped before the length checks, so "   " is not a three-character reason.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    kind: Kind = "modify"
    proposed_body: str | None = Field(default=None, max_length=4000)
    proposed_fields: dict[str, Any] | None = None
    reason: str = Field(min_length=3, max_length=4000)
    base_version: int | None = Field(default=None, ge=1, description="The version you read")
    resolves: list[int] = Field(default_factory=list, max_length=20, description="ISS numbers")
    draft: bool = False
    # US-45: the accepted AI suggestion this proposal was pre-filled from.
    source_suggestion_id: uuid.UUID | None = None

    @field_validator("proposed_body", "reason", "proposed_fields", mode="before")
    @classmethod
    def _no_nul(cls, value: object) -> object:
        if _has_nul(value):
            raise ValueError("Text cannot contain NUL characters")
        return value


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
        source_suggestion_id=body.source_suggestion_id,
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
    _audit_protected(db, ctx, (v.requirement for v in views))
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
    item = change_intake.view(db, change_request_or_404(db, change_request_id))
    _audit_protected(db, ctx, [item.requirement])
    return ChangeRequestRead.from_view(item)


def _audit_protected(db: Session, ctx: AccessContext, requirements: Iterable[Requirement]) -> None:
    """NFR-13: a read that returns a protected requirement's text (``base_body``,
    ``current_body``) is recorded once per protected requirement, ids only."""
    protected = {r.id for r in requirements if r.is_protected}
    if not protected:
        return
    db.add_all(
        AuditLog(
            workspace_id=ctx.workspace_id,
            actor_id=ctx.user.id,
            requirement_id=requirement_id,
            action=AuditAction.VIEWED_PROTECTED,
        )
        for requirement_id in sorted(protected)
    )
    db.commit()


def _change_request_scope(db: Session, change_request_id: uuid.UUID) -> Scope | None:
    row = db.execute(
        select(Project.workspace_id, Project.id)
        .join(ChangeRequest, ChangeRequest.project_id == Project.id)
        .where(ChangeRequest.id == change_request_id)
    ).first()
    return None if row is None else Scope(row[0], row[1])


register_scope_resolver("change_request_id", _change_request_scope)


# ── review and merge (Parth — US-35, FR-65, FR-98) ──────────────────────────────────────────
ReviewDecision = Literal["approve", "request_changes", "comment"]


class ChangeRequestUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposed_body: str | None = Field(default=None, max_length=4000)
    reason: str | None = Field(default=None, min_length=3, max_length=4000)
    rebase: bool = Field(default=False, description="Write it against the current version")
    open: bool = Field(default=False, description="Open a draft for review")


class InlineComment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str = Field(default="statement", max_length=32)
    start_offset: int | None = Field(default=None, ge=0)
    end_offset: int | None = Field(default=None, ge=0)
    body: str = Field(min_length=1, max_length=2000)


class ReviewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: ReviewDecision
    rationale: str | None = Field(default=None, max_length=4000)
    comments: list[InlineComment] = Field(default_factory=list, max_length=20)


class ReviewCommentRead(BaseModel):
    field: str
    start_offset: int | None
    end_offset: int | None
    body: str


class ReviewRead(BaseModel):
    id: uuid.UUID
    reviewer: UserRef | None
    decision: ReviewDecision
    rationale: str | None
    proposal_revision: int
    reviewed_base_version: int
    dismissed: bool  # given on an earlier revision or base version (FR-98)
    comments: list[ReviewCommentRead]
    created_at: datetime


class ReviewRequestRead(BaseModel):
    reviewer: UserRef | None
    required: bool
    reason: str
    approved: bool  # approved the current revision


class ReviewsRead(BaseModel):
    requests: list[ReviewRequestRead]
    reviews: list[ReviewRead]


class ReviewerAdd(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer_id: uuid.UUID


class UnmetRead(BaseModel):
    code: str
    message: str


class AgreementRead(BaseModel):
    mergeable: bool
    unmet: list[UnmetRead]


class MergeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accepted_risk_reason: str | None = Field(default=None, max_length=2000)


class CloseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=3, max_length=2000)


def _read(db: Session, change_request: ChangeRequest) -> ChangeRequestRead:
    return ChangeRequestRead.from_view(change_intake.view(db, change_request))


def _ref(user: User | None) -> UserRef | None:
    return UserRef(id=user.id, full_name=user.full_name) if user else None


@router.patch(
    "/change-requests/{change_request_id}",
    response_model=ChangeRequestRead,
    summary="Edit the proposal (proposer): a new revision, earlier reviews dismissed",
    responses=ERRORS,
)
def update_change_request(
    change_request_id: uuid.UUID,
    body: ChangeRequestUpdate,
    ctx: Annotated[AccessContext, requires("rcr.open")],
    db: DbSession,
) -> ChangeRequestRead:
    change_request = change_requests.update_proposal(
        db,
        ctx,
        change_request_or_404(db, change_request_id),
        proposed_body=body.proposed_body,
        reason=body.reason,
        rebase=body.rebase,
        open_draft=body.open,
    )
    return _read(db, change_request)


@router.get(
    "/change-requests/{change_request_id}/reviews",
    response_model=ReviewsRead,
    summary="Who was asked to review, and every review (dismissed ones marked)",
    responses=ERRORS,
)
def list_reviews(
    change_request_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
) -> ReviewsRead:
    change_request = change_request_or_404(db, change_request_id)
    rows = reviews.reviews_of(db, change_request.id)
    requested = reviews.requests_of(db, change_request.id)
    wanted = {r.reviewer_id for r in rows} | {r.reviewer_id for r in requested}
    people = {u.id: u for u in db.scalars(select(User).where(User.id.in_(wanted)))}
    comments = reviews.comments_of(db, [r.id for r in rows])
    decisions = reviews.current_decisions(db, change_request)
    current = (change_request.proposal_revision, change_request.base_version)
    return ReviewsRead(
        requests=[
            ReviewRequestRead(
                reviewer=_ref(people.get(r.reviewer_id)),
                required=r.required,
                reason=r.reason,
                approved=r.reviewer_id in decisions
                and decisions[r.reviewer_id].decision == "approve",
            )
            for r in requested
        ],
        reviews=[
            ReviewRead(
                id=r.id,
                reviewer=_ref(people.get(r.reviewer_id)),
                decision=cast(ReviewDecision, r.decision),
                rationale=r.rationale,
                proposal_revision=r.proposal_revision,
                reviewed_base_version=r.reviewed_base_version,
                dismissed=(r.proposal_revision, r.reviewed_base_version) != current,
                comments=[
                    ReviewCommentRead(
                        field=c.field,
                        start_offset=c.start_offset,
                        end_offset=c.end_offset,
                        body=c.body,
                    )
                    for c in comments.get(r.id, [])
                ],
                created_at=r.created_at,
            )
            for r in rows
        ],
    )


@router.post(
    "/change-requests/{change_request_id}/reviews",
    response_model=ChangeRequestRead,
    status_code=status.HTTP_201_CREATED,
    summary="Approve, request changes or comment (with inline comments)",
    responses=ERRORS,
)
def create_review(
    change_request_id: uuid.UUID,
    body: ReviewCreate,
    ctx: Annotated[AccessContext, requires("rcr.review")],
    db: DbSession,
) -> ChangeRequestRead:
    change_request = change_request_or_404(db, change_request_id)
    reviews.review(
        db,
        ctx,
        change_request,
        decision=body.decision,
        rationale=body.rationale,
        inline=[c.model_dump() for c in body.comments],
    )
    change_requests.after_review(db, change_request, ctx.user, body.decision)
    return _read(db, change_request)


@router.post(
    "/change-requests/{change_request_id}/reviewers",
    response_model=ReviewRequestRead,
    status_code=status.HTTP_201_CREATED,
    summary="Ask one more person to review (the proposer, or a member who may merge)",
    responses=ERRORS,
)
def add_reviewer(
    change_request_id: uuid.UUID,
    body: ReviewerAdd,
    ctx: Annotated[AccessContext, requires("rcr.open")],
    db: DbSession,
) -> ReviewRequestRead:
    change_request = change_request_or_404(db, change_request_id)
    row = reviews.add_reviewer(db, ctx, change_request, body.reviewer_id)
    return ReviewRequestRead(
        reviewer=_ref(db.get(User, row.reviewer_id)),
        required=row.required,
        reason=row.reason,
        approved=False,
    )


@router.get(
    "/change-requests/{change_request_id}/agreement",
    response_model=AgreementRead,
    summary="Whether it can be merged now, and every unmet condition (FR-98)",
    responses=ERRORS,
)
def get_agreement(
    change_request_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
) -> AgreementRead:
    unmet = AgreementGuard(db).unmet(change_request_or_404(db, change_request_id))
    return AgreementRead(
        mergeable=not unmet, unmet=[UnmetRead(code=u.code, message=u.message) for u in unmet]
    )


@router.post(
    "/change-requests/{change_request_id}/merge",
    response_model=ChangeRequestRead,
    summary="Merge: version n+1 in one transaction, or 409 with the unmet conditions",
    responses=ERRORS,
)
def merge_change_request(
    change_request_id: uuid.UUID,
    body: MergeRequest,
    ctx: Annotated[AccessContext, requires("rcr.merge")],
    db: DbSession,
) -> ChangeRequestRead:
    merged = change_requests.merge(
        db,
        ctx,
        change_request_or_404(db, change_request_id),
        accepted_risk_reason=body.accepted_risk_reason,
    )
    return _read(db, merged.change_request)


@router.post(
    "/change-requests/{change_request_id}/close",
    response_model=ChangeRequestRead,
    summary="Close without merging (rejected), with a reason",
    responses=ERRORS,
)
def close_change_request(
    change_request_id: uuid.UUID,
    body: CloseRequest,
    ctx: Annotated[AccessContext, requires("rcr.merge")],
    db: DbSession,
) -> ChangeRequestRead:
    change_request = change_request_or_404(db, change_request_id)
    return _read(db, change_requests.close(db, ctx, change_request, body.reason))


@router.post(
    "/change-requests/{change_request_id}/withdraw",
    response_model=ChangeRequestRead,
    summary="Withdraw your own change request",
    responses=ERRORS,
)
def withdraw_change_request(
    change_request_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("rcr.open")],
    db: DbSession,
) -> ChangeRequestRead:
    change_request = change_request_or_404(db, change_request_id)
    return _read(db, change_requests.withdraw(db, ctx, change_request))
