"""lifecycle and runs part 8: clarification question provenance and its thread message

Sprint 3 (Madhav — US-09, FR-22, FR-23; ADR-31).

``clarifications`` (created in 0001, empty until now) gains who the question is for
(``addressed_to``), the prompt version and model that wrote it, and the thread message it was
posted as (``message_id``; NULL for findings about extracted requirements, which have no thread).
Answering uses the existing ``resolution`` / ``resolved_by`` / ``resolved_at``.

Revision ID: 0006h
Revises: 0006g
Create Date: 2026-11-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006h"
down_revision: str | None = "0006g"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("clarifications", sa.Column("addressed_to", sa.String(length=16), nullable=True))
    op.add_column(
        "clarifications", sa.Column("prompt_version", sa.String(length=16), nullable=True)
    )
    op.add_column("clarifications", sa.Column("llm_model", sa.String(length=80), nullable=True))
    op.add_column("clarifications", sa.Column("message_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_clarifications_message_id_messages"),
        "clarifications",
        "messages",
        ["message_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_clarifications_message_id_messages"), "clarifications", type_="foreignkey"
    )
    for column in ("message_id", "llm_model", "prompt_version", "addressed_to"):
        op.drop_column("clarifications", column)
