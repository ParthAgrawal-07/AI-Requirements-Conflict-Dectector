"""Authoring aids (Keval — US-51, FR-82, FR-93, NFR-34; design update §8 "Authoring aids").

=====================================  =========================================================
``GET /lint/catalogue``                the lint catalogue, so the browser lints with no request
``POST /projects/{p}/lint``            the same lint on the server (fallback; ``req.propose``)
``POST /projects/{p}/preflight``       dry-run analysis: likely findings, budget left
``POST /projects/{p}/improve-wording``  an EARS rewrite by the AI, returned as original + proposed
=====================================  =========================================================

Nothing here stores anything. The two AI routes need an active project (the ContextGate: no
analysis before the context is confirmed), are rate-limited per member, and spend the project's
LLM budget through its ``BudgetGuard``; an exhausted budget is a 429 ``budget_exhausted`` that
says so, never a silent empty answer.
"""

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import Authenticated, DbSession, requires
from app.classification import preflight, wording
from app.classification.budget import BudgetExceededError, BudgetGuard, get_budget_guard
from app.classification.context_pack import ContextPackBuilder
from app.classification.llm_client import LLMClient, get_llm_client
from app.core.config import get_settings
from app.core.errors import AppError, NotFoundError
from app.core.rate_limit import RateLimiter, enforce, get_rate_limiter
from app.embeddings.model import Embedder, get_embedder
from app.lint import engine
from app.models import Project
from app.schemas.common import ErrorResponse
from app.services.access import AccessContext
from app.services.projects import ensure_project_active

router = APIRouter(tags=["composer"])

MAX_TEXT_CHARS = 4000
_ERRORS: dict[int | str, dict[str, Any]] = {
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    429: {"model": ErrorResponse},
}


class BudgetExhaustedError(AppError):
    status_code = 429
    code = "budget_exhausted"

    def __init__(self) -> None:
        super().__init__("This project's AI budget for the month is used up")


class AiUnavailableError(AppError):
    status_code = 503
    code = "ai_unavailable"

    def __init__(self) -> None:
        super().__init__("No AI model is configured")


class TextIn(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)


class PreflightIn(TextIn):
    # The requirement a change request is about (US-33): it is not compared with itself.
    requirement_id: uuid.UUID | None = None


class LintIssueOut(BaseModel):
    rule_id: str
    category: str
    severity: str
    start: int
    end: int
    match: str
    message: str
    hint: str


class LintOut(BaseModel):
    issues: list[LintIssueOut]
    score: int
    quality: Literal["good", "fair", "poor"]


class LikelyFindingOut(BaseModel):
    category: str
    requirement_id: uuid.UUID | None
    label: str | None
    confidence: float
    rationale: str
    low_confidence: bool


class BudgetOut(BaseModel):
    remaining: int | None  # None: no limit
    monthly: int


class PreflightOut(BaseModel):
    status: Literal["done", "partial", "budget", "unavailable"]
    lint: LintOut
    likely_findings: list[LikelyFindingOut]
    compared: list[uuid.UUID]
    llm_calls: int
    budget: BudgetOut
    label: str = "AI"


class WordingOut(BaseModel):
    original: str
    proposed: str
    template: str
    changes: list[str]
    tbd_slots: list[str]
    lint_before: int
    lint_after: int
    label: str
    prompt_version: str
    model: str


def _lint_out(result: engine.LintResult) -> LintOut:
    return LintOut(
        issues=[LintIssueOut(**issue.as_json()) for issue in result.issues],
        score=result.score,
        quality=result.quality,
    )


def _active_project(db: DbSession, project_id: uuid.UUID) -> Project:
    project = db.get(Project, project_id)
    if project is None:  # cannot happen after require_permission; defensive
        raise NotFoundError("Project not found")
    ensure_project_active(project)
    return project


@router.get("/lint/catalogue", summary="The lint catalogue the composer runs in the browser")
def get_catalogue(_: Authenticated) -> dict[str, Any]:
    return engine.catalogue()


@router.post(
    "/projects/{project_id}/lint",
    response_model=LintOut,
    summary="Lint a draft on the server (no AI, nothing stored)",
    responses=_ERRORS,
)
def post_lint(
    project_id: uuid.UUID,
    body: TextIn,
    ctx: Annotated[AccessContext, requires("req.propose")],
) -> LintOut:
    return _lint_out(engine.lint(body.text))


@router.post(
    "/projects/{project_id}/preflight",
    response_model=PreflightOut,
    summary="Dry-run analysis of a draft: likely findings, nothing stored",
    responses=_ERRORS,
)
def post_preflight(
    project_id: uuid.UUID,
    body: PreflightIn,
    ctx: Annotated[AccessContext, requires("req.propose")],
    db: DbSession,
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
    embedder: Annotated[Embedder, Depends(get_embedder)],
    llm: Annotated[LLMClient | None, Depends(get_llm_client)],
    budget: Annotated[BudgetGuard, Depends(get_budget_guard)],
) -> PreflightOut:
    project = _active_project(db, project_id)
    enforce(
        limiter,
        f"preflight:user:{ctx.user.id}",
        limit=get_settings().preflight_requests_per_minute,
        window_seconds=60,
    )
    result = preflight.dry_run(
        db,
        project,
        body.text,
        llm=llm,
        embedder=embedder,
        budget=budget,
        exclude_requirement_id=body.requirement_id,
    )
    return PreflightOut(
        status=result.status,
        lint=_lint_out(result.lint),
        likely_findings=[LikelyFindingOut(**vars(found)) for found in result.likely],
        compared=result.compared,
        llm_calls=result.llm_calls,
        budget=BudgetOut(remaining=result.budget_remaining, monthly=result.budget_monthly),
    )


@router.post(
    "/projects/{project_id}/improve-wording",
    response_model=WordingOut,
    summary="Suggest an EARS rewrite (AI, shown as a diff, never applied here)",
    responses={**_ERRORS, 422: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
def post_improve_wording(
    project_id: uuid.UUID,
    body: TextIn,
    ctx: Annotated[AccessContext, requires("req.propose")],
    db: DbSession,
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
    llm: Annotated[LLMClient | None, Depends(get_llm_client)],
) -> WordingOut:
    project = _active_project(db, project_id)
    enforce(
        limiter,
        f"wording:user:{ctx.user.id}",
        limit=get_settings().wording_requests_per_minute,
        window_seconds=60,
    )
    if llm is None:
        raise AiUnavailableError()
    pack = ContextPackBuilder(db).build(project, query_text=body.text)
    try:
        suggestion, _ = wording.improve(body.text, llm=llm, pack=pack, project_id=project.id)
    except BudgetExceededError:
        raise BudgetExhaustedError() from None
    if suggestion is None:
        raise AppError(
            "The AI could not suggest a wording that keeps the meaning; try again or edit it "
            "yourself",
            status_code=422,
            code="no_suggestion",
        )
    return WordingOut(**vars(suggestion))
