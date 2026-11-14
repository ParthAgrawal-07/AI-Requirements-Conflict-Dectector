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
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import DbSession, requires
from app.clarification.generator import needs_question
from app.clarification.tasks import GENERATE_FOR_FINDING
from app.core.errors import ConflictError, NotFoundError
from app.models import AuditAction, AuditLog, Clarification, Finding, Project
from app.schemas.common import ErrorResponse
from app.schemas.findings import ClarificationRead
from app.services import analysis_orchestrator
from app.services.access import AccessContext, Scope, register_scope_resolver
from app.services.review_state import involved_requirements

router = APIRouter(tags=["clarifications"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse, "description": "Not a member, or no such finding or question"},
    409: {"model": ErrorResponse},
}


class AnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolution: str = Field(min_length=3, max_length=2000)


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
    clarification = db.scalar(select(Clarification).where(Clarification.finding_id == finding_id))
    if clarification is None:
        raise NotFoundError("This finding has no clarification question yet")
    return ClarificationRead.from_model(clarification)


@router.post(
    "/findings/{finding_id}/clarification",
    status_code=202,
    summary="Generate the finding's clarification question now (queued)",
    responses=_ERRORS,
)
def request_clarification(
    finding_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("finding.review")],
    db: DbSession,
) -> Response:
    finding = db.get(Finding, finding_id)
    if finding is None:
        raise NotFoundError("Finding not found")
    if not needs_question(finding):
        raise ConflictError(
            "Only open Conflicting, Ambiguous and Incomplete findings get a question",
            code="no_question_needed",
        )
    if finding.clarification is not None:
        raise ConflictError("This finding already has a question", code="already_asked")
    analysis_orchestrator.send(GENERATE_FOR_FINDING, [str(finding.id)])
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
        select(Clarification).where(Clarification.id == clarification_id).with_for_update()
    )
    if clarification is None:
        raise NotFoundError("Clarification not found")
    if clarification.resolved_at is not None:
        raise ConflictError("This question was already answered", code="already_answered")
    clarification.resolution = body.resolution.strip()
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
