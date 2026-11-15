"""Channel, ChannelMember, ChannelRead and Message models (Madhav — US-28; messages: Dhavni — US-29).

A project has channels (``#general`` is created with the project and cannot be archived).

* **Public** channels are open to every active member of the workspace (FR-38: the workspace
  membership is the gate). **Private** channels are visible only to the people listed in
  ``channel_members``; to anyone else they do not exist (404, never 403 — ADR-12).
* **Archived** channels are read-only and hidden from the sidebar by default.
* ``channel_reads`` remembers, per person, when they last read a channel, for unread counts.

``messages`` belongs to the same migration (``0005b``) so the channel list can count unread
messages; posting, threads and mentions are Dhavni's ``app.services.messages`` (US-29).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin, enum_column
from app.models.enums import MessageKind

if TYPE_CHECKING:
    from app.models.user import User

MAX_CHANNEL_NAME = 80
MAX_MESSAGE_CHARS = 4000


class Channel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "channels"
    __table_args__ = (
        # Slack-style: names are unique in the project, archived channels included, so a link
        # to "#security" never silently points at a different channel later.
        UniqueConstraint("project_id", "name"),
        CheckConstraint("name ~ '^[a-z0-9][a-z0-9_-]*$'", name="name_format"),
        # The default channel is public and never archived.
        CheckConstraint(
            "NOT (is_default AND (is_private OR archived_at IS NOT NULL))", name="default_open"
        ),
        Index(
            "uq_channels_default_per_project",
            "project_id",
            unique=True,
            postgresql_where=text("is_default"),
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(MAX_CHANNEL_NAME))
    topic: Mapped[str | None] = mapped_column(String(250))
    is_private: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    is_default: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    # NULL when the system created it (#general of a project created before migration 0005b).
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    members: Mapped[list[ChannelMember]] = relationship(
        back_populates="channel", passive_deletes=True
    )

    @property
    def is_archived(self) -> bool:
        return self.archived_at is not None


class ChannelMember(Base):
    """A person listed on a **private** channel. Public channels have no member rows."""

    __tablename__ = "channel_members"
    __table_args__ = (
        PrimaryKeyConstraint("channel_id", "user_id"),
        Index("ix_channel_members_user_id", "user_id"),
    )

    channel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    added_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    channel: Mapped[Channel] = relationship(back_populates="members")
    user: Mapped[User] = relationship(foreign_keys=[user_id])


class ChannelRead(Base):
    """When a person last read a channel (unread counts in the sidebar, US-28)."""

    __tablename__ = "channel_reads"
    __table_args__ = (PrimaryKeyConstraint("channel_id", "user_id"),)

    channel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    last_read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Message(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One channel message: chat, a requirement post, or a card (design update §4.1).

    Threads are one level deep: a reply's ``parent_id`` is a top-level message of the same
    channel. Deleting is soft (``deleted_at``) and blanks the body, so a thread keeps its shape
    and a removed member's messages stay, attributed to a former member (US-26).
    """

    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("parent_id IS NULL OR parent_id <> id", name="not_own_parent"),
        CheckConstraint(
            "deleted_at IS NOT NULL OR char_length(body) BETWEEN 1 AND 4000", name="body_length"
        ),
        # A result card is written by the analysis, not a member (US-31, migration 0006d).
        CheckConstraint(
            "author_id IS NOT NULL OR kind IN ('analysis_card', 'system')", name="author_or_system"
        ),
        # History pages (cursor = created_at, id) and thread replies.
        Index("ix_messages_channel_id_created_at_id", "channel_id", "created_at", "id"),
        Index("ix_messages_parent_id_created_at", "parent_id", "created_at"),
        Index("ix_messages_search", "search", postgresql_using="gin"),
    )

    channel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"))
    # RESTRICT: users are deactivated, never deleted, and their messages stay (FR-45).
    # NULL only for system messages (result cards, "Riya joined").
    author_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE")
    )
    kind: Mapped[MessageKind] = mapped_column(
        enum_column(MessageKind, "message_kind"),
        default=MessageKind.CHAT,
        server_default=MessageKind.CHAT.value,
    )
    body: Mapped[str] = mapped_column(Text)
    # User ids parsed from ``<@uuid>`` tokens in the body (FR-52), active members only.
    mentions: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    # Full-text search over messages (US-46). 'simple': no stemming, works for any language.
    search: Mapped[Any] = mapped_column(
        TSVECTOR, Computed("to_tsvector('simple', coalesce(body, ''))", persisted=True)
    )
    # A card's structured part (e.g. ``{"run_id": ..., "requirement_id": ...}``): ids and states
    # only. The client reads the details over REST, which re-checks access.
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    author: Mapped[User | None] = relationship(foreign_keys=[author_id])

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None
