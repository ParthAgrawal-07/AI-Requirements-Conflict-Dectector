"""Messages, threads and mentions (Dhavni — US-29, FR-51, FR-52, NFR-24).

* **Visibility** is the channel's (``app.services.channels.get_visible_channel``): a private
  channel's messages do not exist for people not listed on it.
* **Threads** are one level deep: a reply's parent is a live top-level message of the same channel.
* **Mentions** are ``<@user-uuid>`` tokens in the body (the composer inserts them from the member
  picker; the client renders them as ``@Name``). Only people who can see the channel are kept.
* **Editing and deleting** is for the author's own *chat* messages. A requirement post is never
  edited — it changes through a change request (design update §4.2). Deleting is soft: the body is
  blanked so replies keep their thread, and nothing of the text survives.
* **Ordering** uses ``clock_timestamp()``, not the transaction time, so two messages written in one
  transaction still sort in the order they were posted; history pages use a ``(created_at, id)``
  cursor.
* **Events** (``message.*``) are published after the commit and carry ids only; clients re-read
  the message over REST, which re-checks access (CR-04).
"""

import base64
import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import ColumnElement, and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.models import (
    Channel,
    ChannelMember,
    Membership,
    Message,
    MessageKind,
    Project,
    User,
)
from app.models.channel import MAX_MESSAGE_CHARS
from app.realtime import bus
from app.realtime.events import MESSAGE_CREATED, MESSAGE_DELETED, MESSAGE_UPDATED, message_event
from app.services import channels as channel_service
from app.services.access import Scope, register_scope_resolver

MENTION = re.compile(r"<@([0-9a-fA-F-]{36})>")
MAX_MENTIONS = 50
MAX_PAGE = 100


@dataclass(frozen=True)
class MessageView:
    """A message plus what the reader needs around it."""

    message: Message
    author_is_member: bool  # False: shown as "former member" (US-26)
    reply_count: int = 0
    last_reply_at: datetime | None = None


@dataclass(frozen=True)
class MessagePage:
    items: list[MessageView]  # oldest first
    next_cursor: str | None  # pass as ``before`` (older) or ``after`` (newer), as requested


# ── cursors ─────────────────────────────────────────────────────────────────────────────────
def encode_cursor(message: Message) -> str:
    raw = f"{message.created_at.isoformat()}|{message.id}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        at, _, message_id = base64.urlsafe_b64decode(padded).decode().partition("|")
        return datetime.fromisoformat(at), uuid.UUID(message_id)
    except (ValueError, UnicodeDecodeError):
        raise BadRequestError("Invalid cursor", code="invalid_cursor") from None


# ── reading ─────────────────────────────────────────────────────────────────────────────────
def get_message(db: Session, message_id: uuid.UUID, user: User) -> tuple[Message, Channel]:
    """The message and its channel, if the caller can see the channel (else 404)."""
    message = db.get(Message, message_id)
    if message is None:
        raise NotFoundError("Message not found")
    try:
        channel = channel_service.get_visible_channel(db, message.channel_id, user)
    except NotFoundError:
        raise NotFoundError("Message not found") from None
    return message, channel


def list_messages(
    db: Session,
    *,
    channel: Channel,
    before: str | None = None,
    after: str | None = None,
    limit: int = 50,
) -> MessagePage:
    """Top-level messages of a channel. Newest page by default; ``before`` pages back in time,
    ``after`` catches up on what was posted since (after a reconnect, US-29)."""
    if before and after:
        raise BadRequestError("Give `before` or `after`, not both", code="invalid_cursor")
    limit = max(1, min(limit, MAX_PAGE))
    query = select(Message).where(Message.channel_id == channel.id, Message.parent_id.is_(None))
    if after:
        at, last_id = decode_cursor(after)
        query = query.where(_later_than(at, last_id)).order_by(Message.created_at, Message.id)
    else:
        if before:
            at, last_id = decode_cursor(before)
            query = query.where(_earlier_than(at, last_id))
        query = query.order_by(Message.created_at.desc(), Message.id.desc())
    rows = list(db.scalars(query.limit(limit + 1)))
    more = len(rows) > limit
    rows = rows[:limit]
    if not after:
        rows.reverse()
    cursor = None
    if more and rows:
        cursor = encode_cursor(rows[-1] if after else rows[0])
    return MessagePage(items=_views(db, channel, rows, with_replies=True), next_cursor=cursor)


def get_thread(db: Session, *, root: Message, channel: Channel) -> list[MessageView]:
    """The root followed by its replies, oldest first (at most ``MAX_PAGE * 2`` replies)."""
    if root.parent_id is not None:
        raise ConflictError("This message is a reply; open its thread root", code="not_a_root")
    replies = list(
        db.scalars(
            select(Message)
            .where(Message.parent_id == root.id)
            .order_by(Message.created_at, Message.id)
            .limit(MAX_PAGE * 2)
        )
    )
    return _views(db, channel, [root, *replies], with_replies=True)


def view_of(db: Session, channel: Channel, message: Message) -> MessageView:
    return _views(db, channel, [message], with_replies=True)[0]


# ── writing ─────────────────────────────────────────────────────────────────────────────────
def _clean_body(body: str) -> str:
    cleaned = body.strip()
    if not cleaned:
        raise BadRequestError("A message cannot be empty", code="empty_message")
    if len(cleaned) > MAX_MESSAGE_CHARS:
        raise BadRequestError(
            f"A message is at most {MAX_MESSAGE_CHARS} characters", code="message_too_long"
        )
    return cleaned


def parse_mentions(db: Session, channel: Channel, workspace_id: uuid.UUID, body: str) -> list[str]:
    """User ids mentioned with ``<@id>`` who are active members and can see the channel."""
    wanted: list[uuid.UUID] = []
    for raw in MENTION.findall(body):
        try:
            user_id = uuid.UUID(raw)
        except ValueError:
            continue
        if user_id not in wanted:
            wanted.append(user_id)
        if len(wanted) >= MAX_MENTIONS:
            break
    if not wanted:
        return []
    members = set(
        db.scalars(
            select(Membership.user_id).where(
                Membership.workspace_id == workspace_id,
                Membership.ended_at.is_(None),
                Membership.user_id.in_(wanted),
            )
        )
    )
    if channel.is_private:
        members &= set(
            db.scalars(
                select(ChannelMember.user_id).where(
                    ChannelMember.channel_id == channel.id, ChannelMember.user_id.in_(members)
                )
            )
        )
    return [str(user_id) for user_id in wanted if user_id in members]


def post_message(
    db: Session,
    *,
    channel: Channel,
    author: User,
    body: str,
    parent_id: uuid.UUID | None = None,
    kind: MessageKind = MessageKind.CHAT,
    commit: bool = True,
) -> Message:
    """Post to a channel (or reply in a thread). ``commit=False`` flushes only and publishes
    nothing — for callers (requirement posts) that write more in the same transaction and then
    call :func:`announce` themselves."""
    if channel.is_archived:
        raise ConflictError("This channel is archived and read-only", code="channel_archived")
    text = _clean_body(body)
    project = _project(db, channel)
    if parent_id is not None:
        parent = db.get(Message, parent_id)
        if parent is None or parent.channel_id != channel.id:
            raise NotFoundError("The message you are replying to was not found")
        if parent.parent_id is not None:
            raise ConflictError("Reply to the thread's first message", code="nested_thread")
        if parent.is_deleted:
            raise ConflictError("That message was deleted", code="message_deleted")
    message = Message(
        channel_id=channel.id,
        author_id=author.id,
        parent_id=parent_id,
        kind=kind,
        body=text,
        mentions=parse_mentions(db, channel, project.workspace_id, text),
        created_at=func.clock_timestamp(),
    )
    db.add(message)
    db.flush()
    db.refresh(message, ["created_at"])
    if commit:
        db.commit()
        announce(MESSAGE_CREATED, project, channel, message)
    return message


SYSTEM_KINDS = (MessageKind.ANALYSIS_CARD, MessageKind.SYSTEM)


def post_system_message(
    db: Session,
    *,
    channel: Channel,
    body: str,
    kind: MessageKind,
    parent_id: uuid.UUID | None = None,
    payload: dict[str, Any] | None = None,
) -> Message:
    """Post a message written by the app, not a member — a result card (US-31) or a notice.

    Mentions in the body are parsed as for a member's message, so an @mentioned owner is notified.
    Posts even in an archived channel: the card belongs to a requirement posted before archiving.
    Commits and announces ``message.created``.
    """
    if kind not in SYSTEM_KINDS:
        raise ValueError(f"{kind} is not a system message kind")
    project = _project(db, channel)
    text = _clean_body(body)
    message = Message(
        channel_id=channel.id,
        author_id=None,
        parent_id=parent_id,
        kind=kind,
        body=text,
        mentions=parse_mentions(db, channel, project.workspace_id, text),
        payload=payload,
        created_at=func.clock_timestamp(),
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    announce(MESSAGE_CREATED, project, channel, message)
    return message


def update_system_message(
    db: Session, *, message: Message, body: str, payload: dict[str, Any] | None
) -> Message:
    """Rewrite a system card (e.g. "waiting for budget" → the results). Announces
    ``message.updated``; members' own messages never go through here."""
    if message.kind not in SYSTEM_KINDS or message.author_id is not None:
        raise ValueError("Only system messages are updated by the app")
    channel = db.get(Channel, message.channel_id)
    if channel is None:
        raise NotFoundError("Channel not found")
    project = _project(db, channel)
    text = _clean_body(body)
    message.body = text
    message.mentions = parse_mentions(db, channel, project.workspace_id, text)
    message.payload = payload
    message.edited_at = datetime.now(UTC)
    db.commit()
    db.refresh(message)
    announce(MESSAGE_UPDATED, project, channel, message)
    return message


def _own_chat_message(message: Message, user: User) -> None:
    if message.author_id != user.id:
        raise ForbiddenError("You can only change your own messages")
    if message.is_deleted:
        raise ConflictError("That message was deleted", code="message_deleted")
    if message.kind is not MessageKind.CHAT:
        raise ConflictError(
            "Only chat messages can be changed; a requirement changes through a change request",
            code="not_editable",
        )


def edit_message(
    db: Session, *, message: Message, channel: Channel, user: User, body: str
) -> Message:
    if channel.is_archived:
        raise ConflictError("This channel is archived and read-only", code="channel_archived")
    _own_chat_message(message, user)
    text = _clean_body(body)
    project = _project(db, channel)
    if text != message.body:
        message.body = text
        message.mentions = parse_mentions(db, channel, project.workspace_id, text)
        message.edited_at = datetime.now(UTC)
        db.commit()
        db.refresh(message)
        announce(MESSAGE_UPDATED, project, channel, message)
    return message


def delete_message(db: Session, *, message: Message, channel: Channel, user: User) -> None:
    if channel.is_archived:
        raise ConflictError("This channel is archived and read-only", code="channel_archived")
    _own_chat_message(message, user)
    project = _project(db, channel)
    message.body = ""
    message.mentions = []
    message.deleted_at = datetime.now(UTC)
    db.commit()
    announce(MESSAGE_DELETED, project, channel, message)


def announce(event_type: str, project: Project, channel: Channel, message: Message) -> None:
    """Publish ``message.*`` — after the commit that made it visible."""
    bus.publish(
        message_event(
            event_type,
            workspace_id=project.workspace_id,
            project_id=project.id,
            channel_id=channel.id,
            private=channel.is_private,
            message_id=message.id,
            parent_id=message.parent_id,
            author_id=message.author_id,
            mentions=list(message.mentions),
        )
    )


# ── helpers ─────────────────────────────────────────────────────────────────────────────────
def _later_than(at: datetime, message_id: uuid.UUID) -> ColumnElement[bool]:
    return or_(Message.created_at > at, and_(Message.created_at == at, Message.id > message_id))


def _earlier_than(at: datetime, message_id: uuid.UUID) -> ColumnElement[bool]:
    return or_(Message.created_at < at, and_(Message.created_at == at, Message.id < message_id))


def _project(db: Session, channel: Channel) -> Project:
    project = db.get(Project, channel.project_id)
    if project is None:  # impossible through the FK; defensive
        raise NotFoundError("Channel not found")
    return project


def _views(
    db: Session, channel: Channel, messages: Iterable[Message], *, with_replies: bool
) -> list[MessageView]:
    messages = list(messages)
    if not messages:
        return []
    project = _project(db, channel)
    authors = {message.author_id for message in messages if message.author_id is not None}
    members = set(
        db.scalars(
            select(Membership.user_id).where(
                Membership.workspace_id == project.workspace_id,
                Membership.ended_at.is_(None),
                Membership.user_id.in_(authors),
            )
        )
    )
    replies: dict[uuid.UUID, tuple[int, datetime | None]] = {}
    roots = [m.id for m in messages if m.parent_id is None]
    if with_replies and roots:
        for parent_id, count, last in db.execute(
            select(Message.parent_id, func.count(Message.id), func.max(Message.created_at))
            .where(Message.parent_id.in_(roots), Message.deleted_at.is_(None))
            .group_by(Message.parent_id)
        ):
            if parent_id is not None:  # always set: the query filters on it
                replies[parent_id] = (count, last)
    return [
        MessageView(
            message=message,
            author_is_member=message.author_id in members,
            reply_count=replies.get(message.id, (0, None))[0],
            last_reply_at=replies.get(message.id, (0, None))[1],
        )
        for message in messages
    ]


def _message_scope(db: Session, message_id: uuid.UUID) -> Scope | None:
    row = db.execute(
        select(Project.workspace_id, Project.id)
        .join(Channel, Channel.project_id == Project.id)
        .join(Message, Message.channel_id == Channel.id)
        .where(Message.id == message_id)
    ).first()
    return None if row is None else Scope(row[0], row[1])


register_scope_resolver("message_id", _message_scope)
