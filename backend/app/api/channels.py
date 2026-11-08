"""Channel routes (Madhav — US-28, FR-50; contract in ``docs/contracts/channels.md``).

* ``POST /projects/{p}/channels``, ``PATCH /channels/{c}``, ``POST /channels/{c}/archive`` and the
  private member list changes need ``channel.manage``;
* reading needs ``view``; a private channel the caller is not listed on is a 404, like an unknown
  id (``channels.get_visible_channel``);
* ``POST /channels/{c}/read`` only moves the caller's own read marker, so ``view`` is enough
  (listed in ``tests/api/test_access_invariants.py``).
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query, Response

from app.api.deps import DbSession, requires
from app.core.errors import NotFoundError
from app.models import Channel, Project
from app.schemas.channels import (
    ChannelCreate,
    ChannelMemberAdd,
    ChannelMemberRead,
    ChannelRead,
    ChannelUpdate,
)
from app.schemas.common import ErrorResponse
from app.services import channels as channel_service
from app.services.access import AccessContext

router = APIRouter(tags=["channels"])

_NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Not a member, or no such (visible) channel"}
}
_CHANGES: dict[int | str, dict[str, Any]] = {
    **_NOT_FOUND,
    403: {"model": ErrorResponse},
    409: {"model": ErrorResponse, "description": "Name taken, channel archived, or #general"},
}


def _read(channel: Channel, unread: int = 0, last_message_at: Any = None) -> ChannelRead:
    return ChannelRead(
        id=channel.id,
        project_id=channel.project_id,
        name=channel.name,
        topic=channel.topic,
        is_private=channel.is_private,
        is_default=channel.is_default,
        archived_at=channel.archived_at,
        created_by=channel.created_by,
        created_at=channel.created_at,
        unread_count=unread,
        last_message_at=last_message_at,
    )


@router.post(
    "/projects/{project_id}/channels",
    status_code=201,
    response_model=ChannelRead,
    summary="Create a channel (public, or private with a member list)",
    responses=_CHANGES,
)
def create_channel(
    project_id: uuid.UUID,
    body: ChannelCreate,
    response: Response,
    ctx: Annotated[AccessContext, requires("channel.manage")],
    db: DbSession,
) -> ChannelRead:
    project = db.get(Project, project_id)
    if project is None:  # cannot happen after require_permission; defensive
        raise NotFoundError("Project not found")
    channel = channel_service.create_channel(
        db,
        project=project,
        creator=ctx.user,
        name=body.name,
        topic=body.topic,
        is_private=body.is_private,
        member_ids=body.member_ids,
    )
    response.headers["Location"] = f"/api/v1/channels/{channel.id}"
    return _read(channel)


@router.get(
    "/projects/{project_id}/channels",
    response_model=list[ChannelRead],
    summary="The project's channels the caller can see, with unread counts",
    responses=_NOT_FOUND,
)
def list_channels(
    project_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
    include_archived: Annotated[bool, Query()] = False,
) -> list[ChannelRead]:
    return [
        _read(item.channel, item.unread_count, item.last_message_at)
        for item in channel_service.list_channels(
            db,
            project_id=project_id,
            user=ctx.user,
            since=ctx.membership.joined_at,
            include_archived=include_archived,
        )
    ]


@router.get(
    "/channels/{channel_id}",
    response_model=ChannelRead,
    summary="Get a channel",
    responses=_NOT_FOUND,
)
def get_channel(
    channel_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
) -> ChannelRead:
    return _read(channel_service.get_visible_channel(db, channel_id, ctx.user))


@router.patch(
    "/channels/{channel_id}",
    response_model=ChannelRead,
    summary="Rename a channel or change its topic",
    responses=_CHANGES,
)
def update_channel(
    channel_id: uuid.UUID,
    body: ChannelUpdate,
    ctx: Annotated[AccessContext, requires("channel.manage")],
    db: DbSession,
) -> ChannelRead:
    channel = channel_service.get_visible_channel(db, channel_id, ctx.user)
    channel = channel_service.update_channel(
        db, channel=channel, actor=ctx.user, name=body.name, topic=body.topic
    )
    return _read(channel)


@router.post(
    "/channels/{channel_id}/archive",
    response_model=ChannelRead,
    summary="Archive a channel: read-only and hidden by default",
    responses=_CHANGES,
)
def archive_channel(
    channel_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("channel.manage")],
    db: DbSession,
) -> ChannelRead:
    channel = channel_service.get_visible_channel(db, channel_id, ctx.user)
    return _read(channel_service.archive_channel(db, channel=channel, actor=ctx.user))


@router.post(
    "/channels/{channel_id}/read",
    status_code=204,
    summary="Mark the channel as read by the caller (clears its unread count)",
    responses=_NOT_FOUND,
)
def mark_read(
    channel_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
) -> Response:
    channel = channel_service.get_visible_channel(db, channel_id, ctx.user)
    channel_service.mark_read(db, channel=channel, user=ctx.user)
    return Response(status_code=204)


@router.get(
    "/channels/{channel_id}/members",
    response_model=list[ChannelMemberRead],
    summary="The people listed on a private channel",
    responses={**_NOT_FOUND, 409: {"model": ErrorResponse, "description": "Public channel"}},
)
def list_members(
    channel_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
) -> list[ChannelMemberRead]:
    channel = channel_service.get_visible_channel(db, channel_id, ctx.user)
    return [
        ChannelMemberRead(user_id=m.user_id, full_name=m.user.full_name, added_at=m.added_at)
        for m in channel_service.list_members(db, channel)
    ]


@router.post(
    "/channels/{channel_id}/members",
    status_code=201,
    response_model=ChannelMemberRead,
    summary="List a workspace member on a private channel",
    responses=_CHANGES,
)
def add_member(
    channel_id: uuid.UUID,
    body: ChannelMemberAdd,
    ctx: Annotated[AccessContext, requires("channel.manage")],
    db: DbSession,
) -> ChannelMemberRead:
    channel = channel_service.get_visible_channel(db, channel_id, ctx.user)
    member = channel_service.add_member(db, channel=channel, actor=ctx.user, user_id=body.user_id)
    return ChannelMemberRead(
        user_id=member.user_id, full_name=member.user.full_name, added_at=member.added_at
    )


@router.delete(
    "/channels/{channel_id}/members/{user_id}",
    status_code=204,
    summary="Take someone off a private channel",
    responses=_CHANGES,
)
def remove_member(
    channel_id: uuid.UUID,
    user_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("channel.manage")],
    db: DbSession,
) -> Response:
    channel = channel_service.get_visible_channel(db, channel_id, ctx.user)
    channel_service.remove_member(db, channel=channel, actor=ctx.user, user_id=user_id)
    return Response(status_code=204)
