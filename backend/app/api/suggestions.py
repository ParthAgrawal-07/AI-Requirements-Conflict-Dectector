"""AI suggestions API (Madhav — US-45, FR-68, FR-94, NFR-36; design update §8 "AI suggestions").

=============================================  ===============================================
``GET /findings/{f}/suggestions``              the finding's live suggestion (``view``); queues
                                               one when there is none yet (202 while pending)
``POST /findings/{f}/suggestions/regenerate``  new options respecting an instruction
                                               (``req.comment``)
``POST /suggestions/{s}/feedback``             one response: the six outcomes, prefer, thumbs,
                                               regenerate (``req.comment``; accepting needs a
                                               propose permission too)
``POST /suggestions/{s}/rating``               an analyst's 1–5 correctness rating
                                               (``finding.review``, the CP2 study)
``GET /projects/{p}/suggestions/stats``        outcomes per category, acceptance, ratings
=============================================  ===============================================

Nothing here changes a requirement: an acceptance answers with the *pre-fill* the change editor
opens with (DR-04).
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Response, status
from sqlalchemy.orm import Session

from app.api.deps import DbSession, requires
from app.core.errors import NotFoundError
from app.models import Finding, Project
from app.models.suggestion import EXPERT_RATING, PENDING, READY, WAITING_BUDGET, Suggestion
from app.schemas.common import ErrorResponse
from app.services.access import AccessContext, Scope, register_scope_resolver
from app.suggestions import service, tasks
from app.suggestions.schemas import (
    FeedbackCreate,
    FeedbackRead,
    FeedbackResponse,
    PrefillRead,
    RatingCreate,
    RegenerateRequest,
    SuggestionRead,
    SuggestionStats,
)

router = APIRouter(tags=["suggestions"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
}


def _read(db: Session, row: Suggestion, ctx: AccessContext) -> SuggestionRead:
    return SuggestionRead.build(
        row, service.preferences(db, row), service.my_outcome(db, row, ctx.user.id)
    )


def _finding(db: Session, finding_id: uuid.UUID) -> Finding:
    finding = db.get(Finding, finding_id)
    if finding is None:  # cannot happen after require_permission; defensive
        raise NotFoundError("Finding not found")
    return finding


def _suggestion(db: Session, suggestion_id: uuid.UUID) -> Suggestion:
    row = db.get(Suggestion, suggestion_id)
    if row is None:  # cannot happen after require_permission; defensive
        raise NotFoundError("Suggestion not found")
    return row


@router.get(
    "/findings/{finding_id}/suggestions",
    response_model=SuggestionRead,
    summary="The AI's suggested resolutions for a finding",
    responses={202: {"model": SuggestionRead}, **_ERRORS},
)
def get_suggestions(
    finding_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
    response: Response,
) -> SuggestionRead:
    finding = _finding(db, finding_id)
    row, created = service.request(db, finding, requested_by=ctx.user.id)
    if created or row.status == WAITING_BUDGET:
        tasks.enqueue(row.id)  # parked for budget: asked again when someone looks
    if row.status in (PENDING, WAITING_BUDGET):
        response.status_code = status.HTTP_202_ACCEPTED
    return _read(db, row, ctx)


@router.post(
    "/findings/{finding_id}/suggestions/regenerate",
    response_model=SuggestionRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ask for new options that respect an instruction",
    responses=_ERRORS,
)
def regenerate(
    finding_id: uuid.UUID,
    body: RegenerateRequest,
    ctx: Annotated[AccessContext, requires("req.comment")],
    db: DbSession,
) -> SuggestionRead:
    finding = _finding(db, finding_id)
    current = service.live(db, finding.id)
    if current is not None and current.status == READY:
        result = service.record_feedback(
            db, ctx, current, action="regenerate", instruction=body.instruction
        )
        row = result.regenerated or current
    else:
        row, _ = service.request(
            db, finding, requested_by=ctx.user.id, instruction=body.instruction
        )
    tasks.enqueue(row.id)
    return _read(db, row, ctx)


@router.post(
    "/suggestions/{suggestion_id}/feedback",
    response_model=FeedbackResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record a response to a suggestion (append-only)",
    responses=_ERRORS,
)
def post_feedback(
    suggestion_id: uuid.UUID,
    body: FeedbackCreate,
    ctx: Annotated[AccessContext, requires("req.comment")],
    db: DbSession,
) -> FeedbackResponse:
    row = _suggestion(db, suggestion_id)
    result = service.record_feedback(
        db,
        ctx,
        row,
        action=body.action,
        option_index=body.option_index,
        final_text=body.final_text,
        reason=body.reason,
        instruction=body.instruction,
    )
    if result.regenerated is not None:
        tasks.enqueue(result.regenerated.id)
    return FeedbackResponse(
        feedback=FeedbackRead.build(result.feedback),
        prefill=PrefillRead.model_validate(vars(result.prefill)) if result.prefill else None,
        suggestion=_read(db, result.regenerated, ctx) if result.regenerated else None,
    )


@router.post(
    "/suggestions/{suggestion_id}/rating",
    response_model=FeedbackRead,
    status_code=status.HTTP_201_CREATED,
    summary="Rate an option's correctness (analysts, the CP2 study)",
    responses=_ERRORS,
)
def post_rating(
    suggestion_id: uuid.UUID,
    body: RatingCreate,
    ctx: Annotated[AccessContext, requires("finding.review")],
    db: DbSession,
) -> FeedbackRead:
    result = service.record_feedback(
        db,
        ctx,
        _suggestion(db, suggestion_id),
        action=EXPERT_RATING,
        option_index=body.option_index,
        reason=body.note,
        expert_rating=body.rating,
    )
    return FeedbackRead.build(result.feedback)


@router.get(
    "/projects/{project_id}/suggestions/stats",
    response_model=SuggestionStats,
    summary="How people responded to the AI's suggestions (NFR-36)",
    responses=_ERRORS,
)
def get_stats(
    project_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
) -> SuggestionStats:
    project = db.get(Project, project_id)
    if project is None:  # cannot happen after require_permission; defensive
        raise NotFoundError("Project not found")
    return SuggestionStats.model_validate(service.stats(db, project))


def _suggestion_scope(db: Session, suggestion_id: uuid.UUID) -> Scope | None:
    row = db.get(Suggestion, suggestion_id)
    project = db.get(Project, row.project_id) if row else None
    return None if project is None else Scope(project.workspace_id, project.id)


register_scope_resolver("suggestion_id", _suggestion_scope)
