"""The change-log summary with its optional AI paragraph (Keval — US-55, FR-96).

``POST /projects/{project_id}/changes/summary`` (``view``) — the same counts, important changes
and Markdown as ``GET …/changes/summary`` (Dhavni), plus, when ``narrative`` is true and a model
is configured, one paragraph written by the LLM from that data only and labelled AI
(``app.classification.change_summary``). A POST because it may spend the project's LLM budget;
it changes no data. Rate-limited per member; without a model or budget the paragraph is simply
absent and the reply says why.
"""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from app.api.deps import DbSession, requires
from app.classification import change_summary
from app.classification.llm_client import LLMClient, get_llm_client
from app.core.rate_limit import RateLimiter, enforce, get_rate_limiter
from app.graph import changelog
from app.graph.changes_api import NarrativeRead, SummaryRead, summary_read, window
from app.schemas.common import ErrorResponse
from app.services.access import AccessContext

router = APIRouter(tags=["changes"])

SUMMARIES_PER_MINUTE = 6


class SummaryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    since: datetime | None = None
    since_baseline_id: uuid.UUID | None = None
    since_last_visit: bool = False
    until: datetime | None = None
    narrative: bool = True


class SummaryWithNarrative(SummaryRead):
    # Why there is no paragraph, when there is none: "not_requested", "no_model", "unavailable".
    narrative_status: str = "ok"


@router.post(
    "/projects/{project_id}/changes/summary",
    response_model=SummaryWithNarrative,
    summary="Summarise changes since… with an optional AI paragraph (labelled AI)",
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
    },
)
def summarise(
    project_id: uuid.UUID,
    body: SummaryRequest,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
    llm: Annotated[LLMClient | None, Depends(get_llm_client)],
) -> SummaryWithNarrative:
    start = window(
        db,
        ctx,
        project_id,
        since=body.since,
        since_baseline_id=body.since_baseline_id,
        since_last_visit=body.since_last_visit,
    )
    result = changelog.summary(
        db,
        project_id,
        since=start.since,
        since_label=start.label,
        until=body.until,
        after_revision=start.after_revision,
    )
    reply = SummaryWithNarrative(**summary_read(result).model_dump())
    if not body.narrative:
        reply.narrative_status = "not_requested"
        return reply
    if llm is None:
        reply.narrative_status = "no_model"
        return reply
    enforce(
        limiter,
        f"change-summary:user:{ctx.user.id}",
        limit=SUMMARIES_PER_MINUTE,
        window_seconds=60,
    )
    narrative = change_summary.write(result, llm=llm, project_id=project_id)
    if narrative is None:
        reply.narrative_status = "unavailable"
        return reply
    reply.narrative = NarrativeRead(
        text=narrative.text, provider=narrative.provider, model=narrative.model
    )
    return reply
