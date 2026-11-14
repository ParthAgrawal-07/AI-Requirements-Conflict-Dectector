"""Channel service (Madhav — US-28, FR-50).

Rules, in the order they are checked:

* **Workspace first.** ``require_permission`` has already turned a non-member into a 404 for
  ``/channels/{c}`` (the ``channel_id`` scope resolver below names the channel's project).
* **Private channels exist only for their listed members.** :func:`get_visible_channel` answers
  404 to anyone else — a manager who is not listed included (ADR-12). ``channel.manage`` decides
  who may create, rename, archive and list people; it is not a key to every private channel.
* **Archived channels are read-only** (409 on rename, member changes and — in
  ``app.services.messages`` — on posting) and hidden from the list unless asked for.
* **``#general``** is created with every project, is public and cannot be archived.

Changes are audited with ids only (CR-04) and announced as ``channel.*`` events *after* the commit.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from sqlalchemy import CursorResult, delete, exists, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models import (
    AuditAction,
    AuditLog,
    Channel,
    ChannelMember,
    ChannelRead,
    Message,
    Project,
    User,
)
from app.realtime import bus
from app.realtime.events import (
    CHANNEL_CREATED,
    CHANNEL_MEMBER_REMOVED,
    CHANNEL_UPDATED,
    channel_event,
)
from app.services.access import Scope, active_membership, register_scope_resolver

GENERAL = "general"


@dataclass(frozen=True)
class ChannelListing:
    channel: Channel
    unread_count: int
    last_message_at: datetime | None


# ── visibility ──────────────────────────────────────────────────────────────────────────────
def _is_listed(db: Session, channel_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    return db.get(ChannelMember, (channel_id, user_id)) is not None


def can_see(db: Session, channel: Channel, user_id: uuid.UUID) -> bool:
    """Public channels: every workspace member (already checked). Private: listed members only."""
    return not channel.is_private or _is_listed(db, channel.id, user_id)


def get_visible_channel(db: Session, channel_id: uuid.UUID, user: User) -> Channel:
    channel = db.get(Channel, channel_id)
    if channel is None or not can_see(db, channel, user.id):
        raise NotFoundError("Channel not found")
    return channel


def _ensure_writable(channel: Channel) -> None:
    if channel.is_archived:
        raise ConflictError("This channel is archived and read-only", code="channel_archived")


# ── create ──────────────────────────────────────────────────────────────────────────────────
def create_general_channel(
    db: Session, *, project_id: uuid.UUID, creator_id: uuid.UUID | None
) -> Channel:
    """``#general`` for a new project. Flushes only: called inside the project's transaction."""
    channel = Channel(project_id=project_id, name=GENERAL, is_default=True, created_by=creator_id)
    db.add(channel)
    db.flush()
    return channel


def create_channel(
    db: Session,
    *,
    project: Project,
    creator: User,
    name: str,
    topic: str | None = None,
    is_private: bool = False,
    member_ids: list[uuid.UUID] | None = None,
) -> Channel:
    """Create a channel. A private channel lists its creator and ``member_ids``, who must all be
    active members of the workspace (404 otherwise). A taken name is a 409."""
    listed = {creator.id, *(member_ids or [])} if is_private else set()
    if not is_private and member_ids:
        raise ConflictError("Public channels are open to everyone and have no member list")
    for user_id in listed:
        if active_membership(db, user_id, project.workspace_id) is None:
            raise NotFoundError("A listed person is not a member of this workspace")

    channel = Channel(
        project_id=project.id,
        name=name,
        topic=topic,
        is_private=is_private,
        created_by=creator.id,
    )
    try:
        with db.begin_nested():
            db.add(channel)
            db.flush()
    except IntegrityError:
        raise ConflictError("This project already has a channel with this name") from None
    db.add_all(
        ChannelMember(channel_id=channel.id, user_id=user_id, added_by=creator.id)
        for user_id in sorted(listed)
    )
    _audit(db, project.workspace_id, creator.id, AuditAction.CHANNEL_CREATED, channel)
    db.commit()
    _announce(CHANNEL_CREATED, project, channel)
    return channel


# ── read ────────────────────────────────────────────────────────────────────────────────────
def list_channels(
    db: Session,
    *,
    project_id: uuid.UUID,
    user: User,
    since: datetime | None,
    include_archived: bool = False,
) -> list[ChannelListing]:
    """The project's channels the caller can see, ``#general`` first, then by name.

    ``unread_count`` counts top-level messages by other people since the caller last read the
    channel — or since ``since`` (when they joined the workspace) if they never did.
    """
    read_at = (
        select(ChannelRead.last_read_at)
        .where(ChannelRead.channel_id == Channel.id, ChannelRead.user_id == user.id)
        .scalar_subquery()
    )
    floor = func.coalesce(read_at, since) if since is not None else read_at
    unread = (
        select(func.count(Message.id))
        .where(
            Message.channel_id == Channel.id,
            Message.parent_id.is_(None),
            Message.deleted_at.is_(None),
            # IS DISTINCT FROM: a system card (no author) is unread for everyone.
            Message.author_id.is_distinct_from(user.id),
            or_(floor.is_(None), Message.created_at > floor),
        )
        .scalar_subquery()
    )
    last_message = (
        select(func.max(Message.created_at))
        .where(Message.channel_id == Channel.id, Message.deleted_at.is_(None))
        .scalar_subquery()
    )
    listed = exists().where(
        ChannelMember.channel_id == Channel.id, ChannelMember.user_id == user.id
    )
    query = (
        select(Channel, unread, last_message)
        .where(Channel.project_id == project_id, or_(Channel.is_private.is_(False), listed))
        .order_by(Channel.is_default.desc(), Channel.name)
    )
    if not include_archived:
        query = query.where(Channel.archived_at.is_(None))
    return [
        ChannelListing(channel=row[0], unread_count=row[1] or 0, last_message_at=row[2])
        for row in db.execute(query)
    ]


def list_members(db: Session, channel: Channel) -> list[ChannelMember]:
    if not channel.is_private:
        raise ConflictError(
            "Public channels are open to every member and have no member list",
            code="channel_public",
        )
    return list(
        db.scalars(
            select(ChannelMember)
            .where(ChannelMember.channel_id == channel.id)
            .order_by(ChannelMember.added_at, ChannelMember.user_id)
        )
    )


# ── change ──────────────────────────────────────────────────────────────────────────────────
def update_channel(
    db: Session, *, channel: Channel, actor: User, name: str | None, topic: str | None
) -> Channel:
    _ensure_writable(channel)
    if name is not None and name != channel.name:
        if channel.is_default:
            raise ConflictError("#general cannot be renamed")
        channel.name = name
    if topic is not None:
        channel.topic = topic or None
    project = _project(db, channel)
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError:
        raise ConflictError("This project already has a channel with this name") from None
    _audit(db, project.workspace_id, actor.id, AuditAction.CHANNEL_UPDATED, channel)
    db.commit()
    _announce(CHANNEL_UPDATED, project, channel)
    return channel


def archive_channel(db: Session, *, channel: Channel, actor: User) -> Channel:
    """Make a channel read-only and hide it from the default list. Archiving twice is harmless."""
    if channel.is_default:
        raise ConflictError("#general cannot be archived")
    if channel.is_archived:
        return channel
    channel.archived_at = func.now()
    project = _project(db, channel)
    _audit(db, project.workspace_id, actor.id, AuditAction.CHANNEL_ARCHIVED, channel)
    db.commit()
    db.refresh(channel)
    _announce(CHANNEL_UPDATED, project, channel, archived=True)
    return channel


def add_member(db: Session, *, channel: Channel, actor: User, user_id: uuid.UUID) -> ChannelMember:
    """List a workspace member on a private channel (idempotent)."""
    _ensure_writable(channel)
    project = _project(db, channel)
    list_members(db, channel)  # 409 for a public channel
    if active_membership(db, user_id, project.workspace_id) is None:
        raise NotFoundError("This person is not a member of the workspace")
    existing = db.get(ChannelMember, (channel.id, user_id))
    if existing is not None:
        return existing
    member = ChannelMember(channel_id=channel.id, user_id=user_id, added_by=actor.id)
    db.add(member)
    _audit(
        db,
        project.workspace_id,
        actor.id,
        AuditAction.CHANNEL_MEMBER_ADDED,
        channel,
        user_id=user_id,
    )
    db.commit()
    return member


def remove_member(db: Session, *, channel: Channel, actor: User, user_id: uuid.UUID) -> None:
    """Take someone off a private channel; their open sockets stop receiving it at once."""
    _ensure_writable(channel)
    project = _project(db, channel)
    list_members(db, channel)
    deleted = cast(
        CursorResult[Any],
        db.execute(
            delete(ChannelMember).where(
                ChannelMember.channel_id == channel.id, ChannelMember.user_id == user_id
            )
        ),
    )
    if not deleted.rowcount:
        raise NotFoundError("This person is not listed on the channel")
    _audit(
        db,
        project.workspace_id,
        actor.id,
        AuditAction.CHANNEL_MEMBER_REMOVED,
        channel,
        user_id=user_id,
    )
    db.commit()
    _announce(CHANNEL_MEMBER_REMOVED, project, channel, user_id=str(user_id))


def mark_read(db: Session, *, channel: Channel, user: User) -> None:
    """Remember that ``user`` has read ``channel`` up to now (clears its unread count)."""
    statement = insert(ChannelRead).values(
        channel_id=channel.id, user_id=user.id, last_read_at=func.clock_timestamp()
    )
    db.execute(
        statement.on_conflict_do_update(
            index_elements=[ChannelRead.channel_id, ChannelRead.user_id],
            set_={"last_read_at": statement.excluded.last_read_at},
        )
    )
    db.commit()


# ── helpers ─────────────────────────────────────────────────────────────────────────────────
def _project(db: Session, channel: Channel) -> Project:
    project = db.get(Project, channel.project_id)
    if project is None:  # the FK makes this impossible; defensive
        raise NotFoundError("Channel not found")
    return project


def _audit(
    db: Session,
    workspace_id: uuid.UUID,
    actor_id: uuid.UUID,
    action: AuditAction,
    channel: Channel,
    *,
    user_id: uuid.UUID | None = None,
) -> None:
    details = {"project_id": str(channel.project_id), "channel_id": str(channel.id)}
    if user_id is not None:
        details["user_id"] = str(user_id)
    db.add(AuditLog(workspace_id=workspace_id, actor_id=actor_id, action=action, details=details))


def _announce(event_type: str, project: Project, channel: Channel, **data: object) -> None:
    bus.publish(
        channel_event(
            event_type,
            workspace_id=project.workspace_id,
            project_id=project.id,
            channel_id=channel.id,
            private=channel.is_private,
            **data,
        )
    )


def _channel_scope(db: Session, channel_id: uuid.UUID) -> Scope | None:
    row = db.execute(
        select(Project.workspace_id, Project.id)
        .join(Channel, Channel.project_id == Project.id)
        .where(Channel.id == channel_id)
    ).first()
    return None if row is None else Scope(row[0], row[1])


register_scope_resolver("channel_id", _channel_scope)
