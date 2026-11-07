"""Message schemas (Dhavni — US-29). Bodies are plain text; clients render them as text, never
HTML (no injection), turning ``<@user-id>`` tokens into ``@Name``."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models import MessageKind
from app.models.channel import MAX_MESSAGE_CHARS
from app.services.messages import MessageView, encode_cursor


class MessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS + 200)
    parent_id: uuid.UUID | None = None  # reply in this message's thread


class MessageUpdate(BaseModel):
    body: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS + 200)


class MessageAuthor(BaseModel):
    id: uuid.UUID
    full_name: str
    is_member: bool  # False: show "(former member)"


class MessageRead(BaseModel):
    id: uuid.UUID
    channel_id: uuid.UUID
    parent_id: uuid.UUID | None
    kind: MessageKind
    body: str  # "" once deleted
    author: MessageAuthor
    mentions: list[uuid.UUID]
    created_at: datetime
    edited_at: datetime | None
    deleted: bool
    reply_count: int
    last_reply_at: datetime | None
    # Pass as `after` to catch up on newer messages, or `before` to load older ones (US-29).
    cursor: str

    @classmethod
    def from_view(cls, view: MessageView) -> "MessageRead":
        message = view.message
        return cls(
            id=message.id,
            channel_id=message.channel_id,
            parent_id=message.parent_id,
            kind=message.kind,
            body=message.body,
            author=MessageAuthor(
                id=message.author_id,
                full_name=message.author.full_name,
                is_member=view.author_is_member,
            ),
            mentions=[uuid.UUID(user_id) for user_id in message.mentions],
            created_at=message.created_at,
            edited_at=message.edited_at,
            deleted=message.is_deleted,
            reply_count=view.reply_count,
            last_reply_at=view.last_reply_at,
            cursor=encode_cursor(message),
        )


class MessagePageRead(BaseModel):
    items: list[MessageRead]  # oldest first
    next_cursor: str | None = Field(
        description="Older messages: pass as `before`; with `after`, newer ones: pass as `after`"
    )
