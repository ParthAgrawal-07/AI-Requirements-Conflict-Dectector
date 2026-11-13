"""Message routes (Dhavni — US-29, FR-51, FR-52; contract in ``docs/contracts/realtime.md``).

* Reading needs ``view``; posting, replying and editing need ``message.post`` and are rate-limited
  per user (``MESSAGES_PER_MINUTE``). Deleting your own message needs ``message.post`` as well.
* A message in a private channel the caller is not listed on is a 404, like an unknown id.
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response

from app.api.deps import DbSession, requires
from app.core.config import get_settings
from app.core.rate_limit import RateLimiter, enforce, get_rate_limiter
from app.models import User
from app.schemas.common import ErrorResponse
from app.schemas.messages import MessageCreate, MessagePageRead, MessageRead, MessageUpdate
from app.services import channels as channel_service
from app.services import messages as message_service
from app.services.access import AccessContext

router = APIRouter(tags=["messages"])

_NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Not a member, or no such (visible) message"}
}
_WRITES: dict[int | str, dict[str, Any]] = {
    **_NOT_FOUND,
    400: {"model": ErrorResponse, "description": "Empty or too long"},
    403: {"model": ErrorResponse},
    409: {"model": ErrorResponse, "description": "Archived channel, deleted or non-chat message"},
    429: {"model": ErrorResponse, "description": "Too many messages; slow down"},
}


def _limit(limiter: RateLimiter, user: User) -> None:
    enforce(
        limiter,
        f"messages:user:{user.id}",
        limit=get_settings().messages_per_minute,
        window_seconds=60,
    )


@router.get(
    "/channels/{channel_id}/messages",
    response_model=MessagePageRead,
    summary="Channel history, newest page first (cursor pagination)",
    responses={**_NOT_FOUND, 400: {"model": ErrorResponse, "description": "Bad cursor"}},
)
def list_messages(
    channel_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
    before: Annotated[str | None, Query(description="Older than this cursor")] = None,
    after: Annotated[str | None, Query(description="Newer than this cursor (catch-up)")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> MessagePageRead:
    channel = channel_service.get_visible_channel(db, channel_id, ctx.user)
    page = message_service.list_messages(
        db, channel=channel, before=before, after=after, limit=limit
    )
    return MessagePageRead(
        items=[MessageRead.from_view(view) for view in page.items], next_cursor=page.next_cursor
    )


@router.post(
    "/channels/{channel_id}/messages",
    status_code=201,
    response_model=MessageRead,
    summary="Post a message, or reply in a thread with parent_id",
    responses=_WRITES,
)
def post_message(
    channel_id: uuid.UUID,
    body: MessageCreate,
    ctx: Annotated[AccessContext, requires("message.post")],
    db: DbSession,
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> MessageRead:
    channel = channel_service.get_visible_channel(db, channel_id, ctx.user)
    _limit(limiter, ctx.user)
    message = message_service.post_message(
        db, channel=channel, author=ctx.user, body=body.body, parent_id=body.parent_id
    )
    return MessageRead.from_view(message_service.view_of(db, channel, message))


@router.get(
    "/messages/{message_id}",
    response_model=MessageRead,
    summary="One message (clients re-read it after a message.* event)",
    responses=_NOT_FOUND,
)
def get_message(
    message_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
) -> MessageRead:
    message, channel = message_service.get_message(db, message_id, ctx.user)
    return MessageRead.from_view(message_service.view_of(db, channel, message))


@router.get(
    "/messages/{message_id}/thread",
    response_model=list[MessageRead],
    summary="A thread: its first message, then the replies, oldest first",
    responses={**_NOT_FOUND, 409: {"model": ErrorResponse, "description": "Not a thread root"}},
)
def get_thread(
    message_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
) -> list[MessageRead]:
    message, channel = message_service.get_message(db, message_id, ctx.user)
    return [
        MessageRead.from_view(view)
        for view in message_service.get_thread(db, root=message, channel=channel)
    ]


@router.patch(
    "/messages/{message_id}",
    response_model=MessageRead,
    summary="Edit your own chat message (shown as edited)",
    responses=_WRITES,
)
def edit_message(
    message_id: uuid.UUID,
    body: MessageUpdate,
    ctx: Annotated[AccessContext, requires("message.post")],
    db: DbSession,
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> MessageRead:
    message, channel = message_service.get_message(db, message_id, ctx.user)
    _limit(limiter, ctx.user)
    message = message_service.edit_message(
        db, message=message, channel=channel, user=ctx.user, body=body.body
    )
    return MessageRead.from_view(message_service.view_of(db, channel, message))


@router.delete(
    "/messages/{message_id}",
    status_code=204,
    summary="Delete your own chat message (its replies stay)",
    responses=_WRITES,
)
def delete_message(
    message_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("message.post")],
    db: DbSession,
) -> Response:
    message, channel = message_service.get_message(db, message_id, ctx.user)
    message_service.delete_message(db, message=message, channel=channel, user=ctx.user)
    return Response(status_code=204)
