"""Threshold tuning per project (Heet — US-06, FR-10, FR-16, FR-17, NFR-18).

A project's ``similarity_threshold`` decides which pairs the embedding filter sends to the AI;
its ``confidence_threshold`` decides which findings are shown as confident. Both are edited with
``PATCH /projects/{p}`` (``project.manage``); before saving, a manager previews a candidate value:

* ``GET /projects/{p}/thresholds/preview?similarity=&confidence=`` — how many pairs the filter
  would send at that similarity, with the pairs just **above** (would be compared) and just
  **below** (would be skipped) it, each with the finding it has today if any; and how many live
  AI findings would count as confident at that confidence. Read-only, embeddings only, no LLM.
* ``POST /projects/{p}/reanalyse`` — apply saved thresholds: queue the analysis of every document
  again (no re-upload). Unchanged pairs are not paid for twice (G1); newly selected pairs are.

Rule checks (US-58) do not depend on either threshold: that is the point of them.
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query, status
from pydantic import BaseModel
from sqlalchemy import Row, and_, func, select
from sqlalchemy.orm import Session, aliased

from app.api.deps import DbSession, requires
from app.core.errors import NotFoundError
from app.models import (
    CandidatePair,
    Embedding,
    Finding,
    Project,
    Requirement,
    RequirementState,
)
from app.schemas.common import ErrorResponse
from app.services import analysis_orchestrator
from app.services.access import AccessContext
from app.services.projects import ensure_project_active

router = APIRouter(tags=["settings"])

EXAMPLES = 5
MAX_REQUIREMENTS = 500  # the preview compares every pair: keep it bounded on huge projects
LIVE = (RequirementState.REJECTED, RequirementState.DEPRECATED)


class PairExample(BaseModel):
    a_id: uuid.UUID
    a_label: str | None
    b_id: uuid.UUID
    b_label: str | None
    similarity: float
    finding: str | None  # the category of a live finding on the pair today, if any
    found_by: str | None


class SimilarityPreview(BaseModel):
    threshold: float
    current: float
    pairs_above: int
    pairs_compared: int  # every pair of live requirements with an embedding
    above: list[PairExample]  # closest to the threshold first
    below: list[PairExample]
    truncated: bool  # more than MAX_REQUIREMENTS: only the first ones were compared


class ConfidencePreview(BaseModel):
    threshold: float
    current: float
    confident: int
    low_confidence: int


class ThresholdPreview(BaseModel):
    similarity: SimilarityPreview
    confidence: ConfidencePreview


class ReanalyseOut(BaseModel):
    queued: int


def _live_findings(db: Session, project_id: uuid.UUID) -> dict[uuid.UUID, tuple[str, str]]:
    rows = db.execute(
        select(CandidatePair.id, Finding.category, Finding.source)
        .join(Finding, Finding.candidate_pair_id == CandidatePair.id)
        .where(Finding.project_id == project_id, ~Finding.is_stale)
        .order_by(Finding.created_at)
    ).tuples()
    return {pair_id: (category.value, source) for pair_id, category, source in rows}


def similarity_preview(db: Session, project: Project, threshold: float) -> SimilarityPreview:
    ids = list(
        db.scalars(
            select(Requirement.id)
            .join(Embedding, Embedding.requirement_id == Requirement.id)
            .where(Requirement.project_id == project.id, Requirement.state.not_in(LIVE))
            .order_by(Requirement.order_index, Requirement.id)
            .limit(MAX_REQUIREMENTS + 1)
        )
    )
    truncated = len(ids) > MAX_REQUIREMENTS
    ids = ids[:MAX_REQUIREMENTS]
    a, b = aliased(Embedding), aliased(Embedding)
    similarity = (1 - a.vector.cosine_distance(b.vector)).label("similarity")
    pairs = (
        select(a.requirement_id.label("a"), b.requirement_id.label("b"), similarity)
        .join(b, and_(a.requirement_id < b.requirement_id, b.requirement_id.in_(ids)))
        .where(a.requirement_id.in_(ids))
        .subquery()
    )
    total = db.scalar(select(func.count()).select_from(pairs)) or 0
    above_count = (
        db.scalar(select(func.count()).select_from(pairs).where(pairs.c.similarity >= threshold))
        or 0
    )
    above = db.execute(
        select(pairs).where(pairs.c.similarity >= threshold).order_by(pairs.c.similarity)
        .limit(EXAMPLES)
    ).all()  # fmt: skip
    below = db.execute(
        select(pairs).where(pairs.c.similarity < threshold).order_by(pairs.c.similarity.desc())
        .limit(EXAMPLES)
    ).all()  # fmt: skip
    rows = [*above, *below]
    labels = dict(
        db.execute(
            select(Requirement.id, Requirement.source_req_id).where(
                Requirement.id.in_({r.a for r in rows} | {r.b for r in rows})
            )
        )
        .tuples()
        .all()  # a Result has keys(): dict() would read it as a mapping
    )
    pair_ids = {
        (p.requirement_a_id, p.requirement_b_id): p.id
        for p in db.scalars(
            select(CandidatePair).where(
                CandidatePair.requirement_a_id.in_({r.a for r in rows} | {r.b for r in rows})
            )
        )
    }
    live = _live_findings(db, project.id)

    def example(row: Row[Any]) -> PairExample:
        pair_id = pair_ids.get(CandidatePair.ordered(row.a, row.b))
        found = live.get(pair_id) if pair_id else None
        return PairExample(
            a_id=row.a,
            a_label=labels.get(row.a),
            b_id=row.b,
            b_label=labels.get(row.b),
            similarity=round(float(row.similarity), 3),
            finding=found[0] if found else None,
            found_by=found[1] if found else None,
        )

    return SimilarityPreview(
        threshold=threshold,
        current=project.similarity_threshold,
        pairs_above=above_count,
        pairs_compared=total,
        above=[example(r) for r in above],
        below=[example(r) for r in below],
        truncated=truncated,
    )


def confidence_preview(db: Session, project: Project, threshold: float) -> ConfidencePreview:
    base = (
        select(func.count())
        .select_from(Finding)
        .where(Finding.project_id == project.id, ~Finding.is_stale, Finding.source == "ai")
    )
    confident = db.scalar(base.where(Finding.confidence >= threshold)) or 0
    low = db.scalar(base.where(Finding.confidence < threshold)) or 0
    return ConfidencePreview(
        threshold=threshold,
        current=project.confidence_threshold,
        confident=confident,
        low_confidence=low,
    )


def _project(db: Session, project_id: uuid.UUID) -> Project:
    project = db.get(Project, project_id)
    if project is None:  # cannot happen after require_permission; defensive
        raise NotFoundError("Project not found")
    return project


@router.get(
    "/projects/{project_id}/thresholds/preview",
    response_model=ThresholdPreview,
    summary="What candidate thresholds would select, before saving them",
    responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def get_threshold_preview(
    project_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("project.manage")],
    db: DbSession,
    similarity: Annotated[float | None, Query(ge=0, le=1)] = None,
    confidence: Annotated[float | None, Query(ge=0, le=1)] = None,
) -> ThresholdPreview:
    project = _project(db, project_id)
    return ThresholdPreview(
        similarity=similarity_preview(
            db, project, project.similarity_threshold if similarity is None else similarity
        ),
        confidence=confidence_preview(
            db, project, project.confidence_threshold if confidence is None else confidence
        ),
    )


@router.post(
    "/projects/{project_id}/reanalyse",
    response_model=ReanalyseOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Analyse the project again with its current thresholds (no re-upload)",
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },  # fmt: skip
)
def post_reanalyse(
    project_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("project.manage")],
    db: DbSession,
) -> ReanalyseOut:
    project = _project(db, project_id)
    ensure_project_active(project)
    # ``send`` looked up now, not bound as the default: tests replace it.
    queued = analysis_orchestrator.analyse_project(db, project.id, analysis_orchestrator.send)
    return ReanalyseOut(queued=queued)
