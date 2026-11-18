"""Composer route (Pranshu — US-30; FR-55, FR-59).

* ``POST /projects/{p}/requirements`` (``req.propose``) — the composer's *Propose*: a Proposed
  requirement posted as a card in the chosen channel (default: the group's, else ``#general``),
  with its live analysis queued (``app.intake.posts``).

Ownership requests and reassignment are in ``app.api.requirements`` (US-36).
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.api.deps import DbSession, requires
from app.api.intake import RequirementPostCreate, RequirementPostRead
from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.core.rate_limit import RateLimiter, enforce, get_rate_limiter
from app.intake import posts as post_service
from app.models import Project
from app.schemas.common import ErrorResponse
from app.services.access import AccessContext

router = APIRouter(tags=["composer"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse, "description": "Not a member, or no such resource"},
    409: {"model": ErrorResponse},
}


@router.post(
    "/projects/{project_id}/requirements",
    status_code=201,
    response_model=RequirementPostRead,
    summary="Propose a requirement from the composer (posted as a card, analysed live)",
    responses={**_ERRORS, 429: {"model": ErrorResponse}},
)
def propose_requirement(
    project_id: uuid.UUID,
    body: RequirementPostCreate,
    ctx: Annotated[AccessContext, requires("req.propose")],
    db: DbSession,
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> RequirementPostRead:
    project = db.get(Project, project_id)
    if project is None:  # resolved by the access layer a moment ago; defensive
        raise NotFoundError("Project not found")
    enforce(
        limiter,
        f"messages:user:{ctx.user.id}",
        limit=get_settings().messages_per_minute,
        window_seconds=60,
    )
    result = post_service.post_to_project(
        db, project=project, author=ctx.user, fields=body.fields, draft_id=body.draft_id
    )
    return RequirementPostRead.build(db, result)
