"""collaboration part 2: channels, channel_members, channel_reads, messages

Sprint 2, US-28 (Madhav) and US-29 (Dhavni); design update §4.1, §4.3 (``0005_collaboration``
family). A new file rather than an edit of ``0005``: a merged migration is never edited.

* ``channels`` — per project; unique name per project; one ``is_default`` channel (``#general``)
  per project, which is public and never archived. Every existing project gets its ``#general``.
* ``channel_members`` — the people listed on a *private* channel (public channels have none).
* ``channel_reads`` — when each person last read a channel, for unread counts.
* ``messages`` — chat, requirement posts and cards; one-level threads (``parent_id``); soft
  delete; parsed mentions; a generated ``tsvector`` with a GIN index for search (US-46).

Revision ID: 0005b
Revises: 0005
Create Date: 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005b"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Frozen copy of the enum: a migration must not change when the application code does.
MESSAGE_KINDS = ("chat", "requirement_post", "change_request", "analysis_card", "system")


def _in_list(column: str, values: Sequence[str]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "channels",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("topic", sa.String(length=250), nullable=True),
        sa.Column("is_private", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("name ~ '^[a-z0-9][a-z0-9_-]*$'", name=op.f("ck_channels_name_format")),
        sa.CheckConstraint(
            "NOT (is_default AND (is_private OR archived_at IS NOT NULL))",
            name=op.f("ck_channels_default_open"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_channels_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_channels_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_channels")),
        sa.UniqueConstraint("project_id", "name", name=op.f("uq_channels_project_id_name")),
    )
    op.create_index(
        "uq_channels_default_per_project",
        "channels",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )

    op.create_table(
        "channel_members",
        sa.Column("channel_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("added_by", sa.Uuid(), nullable=True),
        sa.Column(
            "added_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["channel_id"],
            ["channels.id"],
            name=op.f("fk_channel_members_channel_id_channels"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_channel_members_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["added_by"],
            ["users.id"],
            name=op.f("fk_channel_members_added_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("channel_id", "user_id", name=op.f("pk_channel_members")),
    )
    op.create_index("ix_channel_members_user_id", "channel_members", ["user_id"])

    op.create_table(
        "channel_reads",
        sa.Column("channel_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("last_read_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["channel_id"],
            ["channels.id"],
            name=op.f("fk_channel_reads_channel_id_channels"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_channel_reads_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("channel_id", "user_id", name=op.f("pk_channel_reads")),
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("channel_id", sa.Uuid(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column(
            "kind",
            sa.Enum(
                *MESSAGE_KINDS,
                name="message_kind",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            server_default="chat",
            nullable=False,
        ),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "mentions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "search",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('simple', coalesce(body, ''))", persisted=True),
            nullable=True,
        ),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(_in_list("kind", MESSAGE_KINDS), name=op.f("ck_messages_message_kind")),
        sa.CheckConstraint(
            "parent_id IS NULL OR parent_id <> id", name=op.f("ck_messages_not_own_parent")
        ),
        sa.CheckConstraint(
            "deleted_at IS NOT NULL OR char_length(body) BETWEEN 1 AND 4000",
            name=op.f("ck_messages_body_length"),
        ),
        sa.ForeignKeyConstraint(
            ["channel_id"],
            ["channels.id"],
            name=op.f("fk_messages_channel_id_channels"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["users.id"],
            name=op.f("fk_messages_author_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["messages.id"],
            name=op.f("fk_messages_parent_id_messages"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_messages")),
    )
    op.create_index(
        "ix_messages_channel_id_created_at_id", "messages", ["channel_id", "created_at", "id"]
    )
    op.create_index("ix_messages_parent_id_created_at", "messages", ["parent_id", "created_at"])
    op.create_index("ix_messages_search", "messages", ["search"], postgresql_using="gin")

    # Every existing project gets its #general, created by the project's creator if known.
    op.execute(
        """
        INSERT INTO channels (project_id, name, is_private, is_default, created_by)
        SELECT id, 'general', false, true, created_by FROM projects
        """
    )


def downgrade() -> None:
    op.drop_index("ix_messages_search", table_name="messages")
    op.drop_index("ix_messages_parent_id_created_at", table_name="messages")
    op.drop_index("ix_messages_channel_id_created_at_id", table_name="messages")
    op.drop_table("messages")
    op.drop_table("channel_reads")
    op.drop_index("ix_channel_members_user_id", table_name="channel_members")
    op.drop_table("channel_members")
    op.drop_index("uq_channels_default_per_project", table_name="channels")
    op.drop_table("channels")
