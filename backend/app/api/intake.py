"""Requirement intake routes (Bansil — FR-81).

* ``GET /composer/templates`` — the EARS template catalogue, so the composer UI (Pranshu) builds
  its chips, slots and live preview from the same definition the backend renders.
* ``POST /channels/{c}/requirement-posts`` (``req.propose``) — post a requirement in that
  channel: a card plus a Proposed requirement and its queued live analysis (``app.intake.posts``).
  The composer's *Propose* is ``POST /projects/{p}/requirements`` (``app.api.requirements_compose``),
  which picks the channel. Drafts are ``/me/drafts`` (``app.api.drafts``).
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import Authenticated, DbSession, requires
from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.core.rate_limit import RateLimiter, enforce, get_rate_limiter
from app.intake import posts as post_service
from app.intake.ears import templates_as_json
from app.intake.posts import PostResult
from app.intake.schemas import ComposerFields
from app.models import Channel
from app.schemas.common import ErrorResponse
from app.schemas.documents import RequirementRead
from app.schemas.messages import MessageRead
from app.services import channels as channel_service
from app.services import messages as message_service
from app.services.access import AccessContext

router = APIRouter(tags=["composer"])


@router.get(
    "/composer/templates",
    summary="The EARS sentence templates, their slots and examples",
)
def list_templates(user: Authenticated) -> list[dict[str, Any]]:
    return templates_as_json()


class RequirementPostCreate(BaseModel):
    fields: ComposerFields
    # The draft this post came from; it is deleted with the post.
    draft_id: uuid.UUID | None = None
    # US-45: a post written from an accepted suggestion replaces the member's own proposal.
    supersedes: uuid.UUID | None = None
    source_suggestion_id: uuid.UUID | None = None


class RequirementPostRead(BaseModel):
    message: MessageRead
    requirement: RequirementRead
    # The live analysis started for it (US-31); its result card arrives in the message's thread.
    analysis_run_id: uuid.UUID

    @classmethod
    def build(cls, db: Session, result: PostResult) -> "RequirementPostRead":
        channel = db.get(Channel, result.message.channel_id)
        if channel is None:  # the message was just posted there; defensive
            raise NotFoundError("Channel not found")
        return cls(
            message=MessageRead.from_view(message_service.view_of(db, channel, result.message)),
            requirement=RequirementRead.from_model(result.requirement),
            analysis_run_id=result.run.id,
        )


@router.post(
    "/channels/{channel_id}/requirement-posts",
    status_code=201,
    response_model=RequirementPostRead,
    summary="Post a requirement in a channel: a card plus a Proposed requirement",
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse, "description": "The channel is archived"},
        429: {"model": ErrorResponse},
    },
)
def post_requirement(
    channel_id: uuid.UUID,
    body: RequirementPostCreate,
    ctx: Annotated[AccessContext, requires("req.propose")],
    db: DbSession,
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> RequirementPostRead:
    channel = channel_service.get_visible_channel(db, channel_id, ctx.user)
    enforce(
        limiter,
        f"messages:user:{ctx.user.id}",
        limit=get_settings().messages_per_minute,
        window_seconds=60,
    )
    result = post_service.post_requirement(
        db, channel=channel, author=ctx.user, fields=body.fields, draft_id=body.draft_id
    )
    return RequirementPostRead.build(db, result)
