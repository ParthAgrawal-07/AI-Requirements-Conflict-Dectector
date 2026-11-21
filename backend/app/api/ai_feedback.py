"""AI feedback report routes (Keval — US-15, FR-18, NFR-22).

* ``GET /projects/{project_id}/ai-feedback`` (``view``) — dismissals per category and pattern
  with their reasons, patterns surfaced for tuning, and AI-suggestion outcomes, in one report.
* ``PUT /projects/{project_id}/ai-feedback/threshold`` (``project.manage``) — how many
  dismissals of one pattern surface it (1–100). Audited.

The report is a signal for people. Nothing in the product retrains itself from it.
"""

import uuid
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import DbSession, requires
from app.classification import feedback_loop
from app.core.errors import NotFoundError
from app.models import Project
from app.schemas.common import ErrorResponse
from app.services.access import AccessContext

router = APIRouter(tags=["ai-feedback"])

PatternSource = Literal["ai", "rule", "person"]

_ERRORS: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
}


class ReasonRead(BaseModel):
    reason: str
    count: int


class PatternRead(BaseModel):
    pattern: str
    source: PatternSource
    confirmed: int
    dismissed: int
    false_positive_rate: float | None
    reasons: list[ReasonRead]
    surfaced: bool


class CategoryRead(BaseModel):
    category: str
    open: int
    confirmed: int
    dismissed: int
    patterns: list[PatternRead]
    suggestions: dict[str, int]


class SurfacedRead(BaseModel):
    category: str
    pattern: PatternRead


class FeedbackReportRead(BaseModel):
    project_id: uuid.UUID
    threshold: int
    categories: list[CategoryRead]
    surfaced: list[SurfacedRead]
    suggestion_totals: dict[str, int]
    self_training: Literal[False] = False


class ThresholdUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    threshold: int = Field(ge=1, le=100)


def _pattern(p: feedback_loop.Pattern) -> PatternRead:
    return PatternRead(
        pattern=p.pattern,
        source=cast(PatternSource, p.source),
        confirmed=p.confirmed,
        dismissed=p.dismissed,
        false_positive_rate=p.false_positive_rate,
        reasons=[ReasonRead(reason=r, count=n) for r, n in p.reasons],
        surfaced=p.surfaced,
    )


def _project(db: DbSession, project_id: uuid.UUID) -> Project:
    project = db.get(Project, project_id)
    if project is None:  # defensive
        raise NotFoundError("Project not found")
    return project


def _read(report: feedback_loop.Report) -> FeedbackReportRead:
    return FeedbackReportRead(
        project_id=report.project_id,
        threshold=report.threshold,
        categories=[
            CategoryRead(
                category=c.category,
                open=c.open,
                confirmed=c.confirmed,
                dismissed=c.dismissed,
                patterns=[_pattern(p) for p in c.patterns],
                suggestions=c.suggestions,
            )
            for c in report.categories
        ],
        surfaced=[SurfacedRead(category=c, pattern=_pattern(p)) for c, p in report.surfaced],
        suggestion_totals=report.suggestion_totals,
    )


@router.get(
    "/projects/{project_id}/ai-feedback",
    response_model=FeedbackReportRead,
    summary="AI feedback: dismissals by category and pattern, and suggestion outcomes",
    responses=_ERRORS,
)
def get_report(
    project_id: uuid.UUID, ctx: Annotated[AccessContext, requires("view")], db: DbSession
) -> FeedbackReportRead:
    return _read(feedback_loop.report(db, _project(db, project_id)))


@router.put(
    "/projects/{project_id}/ai-feedback/threshold",
    response_model=FeedbackReportRead,
    summary="How many dismissals of one pattern surface it for tuning",
    responses=_ERRORS,
)
def put_threshold(
    project_id: uuid.UUID,
    body: ThresholdUpdate,
    ctx: Annotated[AccessContext, requires("project.manage")],
    db: DbSession,
) -> FeedbackReportRead:
    project = feedback_loop.set_threshold(db, _project(db, project_id), ctx.user, body.threshold)
    return _read(feedback_loop.report(db, project))
