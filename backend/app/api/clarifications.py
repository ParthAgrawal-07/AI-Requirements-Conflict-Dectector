"""Clarification routes (Madhav — US-09, FR-22, FR-23).

* ``GET /findings/{id}/clarification`` (``view``) — the finding's question and its answer.
* ``POST /findings/{id}/clarification`` (``finding.review``) — ask for a question now (e.g. for
  a finding from before Sprint 3, or after the model failed); queued, **202**.
* ``POST /clarifications/{id}/answer`` (``req.comment``) — mark the question answered with the
  resolution text (FR-23). Anyone taking part in the discussion may answer — usually the owner or
  a stakeholder. Recorded in the history of every requirement involved (audit, ids only).
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import DbSession, requires
from app.clarification.delivery import posted_subject
from app.clarification.generator import needs_question
from app.clarification.tasks import GENERATE_FOR_FINDING
from app.core.celery_app import celery_app
from app.core.errors import AppError, ConflictError, NotFoundError
from app.models import (
    AuditAction,
    AuditLog,
    Clarification,
    Finding,
    Project,
)
from app.schemas.common import ErrorResponse
from app.schemas.findings import ClarificationRead
from app.services.access import AccessContext, Scope, register_scope_resolver
from app.services.findings import get_finding, involved_requirements

router = APIRouter(tags=["clarifications"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse, "description": "Not a member, or no such finding or question"},
    409: {"model": ErrorResponse},
}


class AnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    resolution: str = Field(min_length=3, max_length=2000)

    @field_validator("resolution", mode="before")
    @classmethod
    def normalize(cls, value: Any) -> Any:
        if isinstance(value, str) and "\x00" in value:
            raise ValueError("Answers cannot contain NUL characters")
        return value.strip() if isinstance(value, str) else value


@router.get(
    "/findings/{finding_id}/clarification",
    response_model=ClarificationRead,
    summary="The finding's clarification question and its answer",
    responses=_ERRORS,
)
def get_clarification(
    finding_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
) -> ClarificationRead:
    get_finding(db, finding_id, ctx.user, ctx.workspace_id)
    clarification = db.scalar(select(Clarification).where(Clarification.finding_id == finding_id))
    if clarification is None:
        raise NotFoundError("This finding has no clarification question yet")
    return ClarificationRead.from_model(clarification)


@router.post(
    "/findings/{finding_id}/clarification",
    status_code=202,
    summary="Generate the finding's clarification question now (queued)",
    responses={
        **_ERRORS,
        503: {"model": ErrorResponse, "description": "Queue unavailable; retry later"},
    },
)
def request_clarification(
    finding_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("finding.review")],
    db: DbSession,
) -> Response:
    finding = db.scalar(
        select(Finding)
        .join(Project)
        .where(
            Finding.id == finding_id,
            Finding.project_id == ctx.project_id,
            Project.workspace_id == ctx.workspace_id,
        )
    )
    if finding is None:
        raise NotFoundError("Finding not found")
    if not needs_question(finding):
        raise ConflictError(
            "Only open Conflicting, Ambiguous and Incomplete findings get a question",
            code="no_question_needed",
        )
    # Posted questions may need either reply delivery or card-refresh recovery.
    needs_reply = posted_subject(db, finding) is not None
    if finding.clarification is not None and not needs_reply:
        raise ConflictError("This finding already has a question", code="already_asked")
    try:
        celery_app.send_task(GENERATE_FOR_FINDING, args=[str(finding.id)])
    except Exception as error:
        raise AppError(
            "Question generation could not be queued; please retry",
            status_code=503,
            code="generation_unavailable",
            headers={"Retry-After": "5"},
        ) from error
    return Response(status_code=202)


@router.post(
    "/clarifications/{clarification_id}/answer",
    response_model=ClarificationRead,
    summary="Mark a clarification question answered with the resolution (FR-23)",
    responses=_ERRORS,
)
def answer_clarification(
    clarification_id: uuid.UUID,
    body: AnswerRequest,
    ctx: Annotated[AccessContext, requires("req.comment")],
    db: DbSession,
) -> ClarificationRead:
    clarification = db.scalar(
        select(Clarification)
        .join(Finding)
        .join(Project)
        .where(
            Clarification.id == clarification_id,
            Finding.project_id == ctx.project_id,
            Project.workspace_id == ctx.workspace_id,
        )
        .with_for_update(of=Clarification)
    )
    if clarification is None:
        raise NotFoundError("Clarification not found")
    if clarification.resolved_at is not None:
        raise ConflictError("This question was already answered", code="already_answered")
    clarification.resolution = body.resolution
    clarification.resolved_by = ctx.user.id
    clarification.resolved_at = datetime.now(UTC)
    _record_in_history(db, ctx, clarification)
    db.commit()
    return ClarificationRead.from_model(clarification)


def _record_in_history(db: Session, ctx: AccessContext, clarification: Clarification) -> None:
    finding = db.get(Finding, clarification.finding_id)
    if finding is None:
        return
    for requirement in involved_requirements(db, finding):
        db.add(
            AuditLog(
                workspace_id=ctx.workspace_id,
                actor_id=ctx.user.id,
                finding_id=finding.id,
                requirement_id=requirement.id,
                action=AuditAction.CLARIFICATION_ANSWERED,
                details={"clarification_id": str(clarification.id)},
            )
        )


def _clarification_scope(db: Session, clarification_id: uuid.UUID) -> Scope | None:
    row = db.execute(
        select(Project.workspace_id, Project.id)
        .join(Finding, Finding.project_id == Project.id)
        .join(Clarification, Clarification.finding_id == Finding.id)
        .where(Clarification.id == clarification_id)
    ).first()
    return None if row is None else Scope(row[0], row[1])


register_scope_resolver("clarification_id", _clarification_scope)
