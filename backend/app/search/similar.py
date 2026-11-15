"""Similar-requirement hints (Heet — US-51 groundwork, FR-83; interface design §5.2).

``POST /projects/{p}/similar`` takes the text being written in the composer and returns the most
similar existing requirements — "similar questions" as on Stack Overflow — so a member sees
REQ-014 before posting its duplicate. Embedding similarity only: no LLM, no budget, nothing
stored (the draft text is not saved by this call). The composer calls it 800 ms after typing
stops; a per-user rate limit keeps a stuck client from hammering the embedder.

A hint is a *pointer*, never a finding: similarity alone does not make a conflict (DR-10).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import DbSession, requires
from app.core.config import get_settings
from app.core.rate_limit import RateLimiter, enforce, get_rate_limiter
from app.embeddings.incremental import MAX_HINTS, similar_to_text
from app.embeddings.model import Embedder, get_embedder
from app.models import Requirement, RequirementState
from app.schemas.common import ErrorResponse
from app.services.access import AccessContext

router = APIRouter(tags=["composer"])

PREVIEW_CHARS = 160
MAX_TEXT_CHARS = 4000


class SimilarRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)
    k: int = Field(default=3, ge=1, le=MAX_HINTS)


class SimilarRequirement(BaseModel):
    requirement_id: uuid.UUID
    label: str | None  # printed ID, e.g. "REQ-014"
    state: RequirementState
    preview: str  # the start of the statement, for the side panel
    similarity: float


class SimilarResponse(BaseModel):
    hints: list[SimilarRequirement]


def similar_requirements(
    db: Session, project_id: uuid.UUID, text: str, embedder: Embedder, *, k: int = 3
) -> list[SimilarRequirement]:
    hints = similar_to_text(db, project_id, text, embedder, k=k)
    rows = {
        r.id: r
        for r in db.scalars(
            select(Requirement).where(Requirement.id.in_([h.requirement_id for h in hints]))
        )
    }
    result: list[SimilarRequirement] = []
    for hint in hints:
        requirement = rows.get(hint.requirement_id)
        if requirement is None:  # deleted between the two queries
            continue
        body = requirement.body
        preview = body if len(body) <= PREVIEW_CHARS else body[: PREVIEW_CHARS - 1] + "…"
        result.append(
            SimilarRequirement(
                requirement_id=requirement.id,
                label=hint.label,
                state=requirement.state,
                preview=preview,
                similarity=round(hint.similarity, 3),
            )
        )
    return result


@router.post(
    "/projects/{project_id}/similar",
    response_model=SimilarResponse,
    summary="Requirements similar to a draft (embedding only, nothing stored)",
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
    },
)
def post_similar(
    project_id: uuid.UUID,
    body: SimilarRequest,
    ctx: Annotated[AccessContext, requires("req.propose")],
    db: DbSession,
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
    embedder: Annotated[Embedder, Depends(get_embedder)],
) -> SimilarResponse:
    enforce(
        limiter,
        f"similar:user:{ctx.user.id}",
        limit=get_settings().similar_requests_per_minute,
        window_seconds=60,
    )
    return SimilarResponse(
        hints=similar_requirements(db, project_id, body.text, embedder, k=body.k)
    )
