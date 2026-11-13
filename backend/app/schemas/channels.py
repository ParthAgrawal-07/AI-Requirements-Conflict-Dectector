"""Channel schemas (Madhav — US-28)."""

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.channel import MAX_CHANNEL_NAME

_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def normalize_channel_name(value: str) -> str:
    """``" Mobile App "`` -> ``"mobile-app"``; a leading ``#`` is dropped. Raises on bad names."""
    cleaned = re.sub(r"\s+", "-", value.strip().lstrip("#").strip().lower())
    if not cleaned:
        raise ValueError("Name must not be blank")
    if len(cleaned) > MAX_CHANNEL_NAME:
        raise ValueError(f"Name must be at most {MAX_CHANNEL_NAME} characters")
    if not _NAME.match(cleaned):
        raise ValueError(
            "Use lowercase letters, digits, '-' and '_' only, starting with a letter or digit"
        )
    return cleaned


class ChannelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=MAX_CHANNEL_NAME + 1)
    topic: str | None = Field(default=None, max_length=250)
    is_private: bool = False
    # Private channels only: who else is listed (the creator always is).
    member_ids: list[uuid.UUID] = Field(default_factory=list, max_length=200)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return normalize_channel_name(value)


class ChannelUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=MAX_CHANNEL_NAME + 1)
    topic: str | None = Field(default=None, max_length=250)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        return None if value is None else normalize_channel_name(value)


class ChannelRead(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    topic: str | None
    is_private: bool
    is_default: bool
    archived_at: datetime | None
    created_by: uuid.UUID | None
    created_at: datetime
    # For the caller: top-level messages by others since they last read the channel.
    unread_count: int = 0
    last_message_at: datetime | None = None


class ChannelMemberAdd(BaseModel):
    user_id: uuid.UUID


class ChannelMemberRead(BaseModel):
    user_id: uuid.UUID
    full_name: str
    added_at: datetime
