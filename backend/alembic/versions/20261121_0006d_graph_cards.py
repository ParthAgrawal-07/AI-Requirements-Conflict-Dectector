"""lifecycle and runs part 4: live map revisions, node positions, system cards

Sprint 3 (Dhavni — US-14, US-31; design update §3.4, §4.3 ``0006_lifecycle_runs``).

* ``projects.graph_revision`` — bumped once per ``graph.delta``; a client holding revision *r*
  applies only the delta from *r* and re-fetches the snapshot otherwise.
* ``node_positions`` — the map's persisted layout (one row per placed requirement), so every
  viewer sees the same picture and nothing jumps when something else changes.
* ``messages.author_id`` becomes nullable for **system** messages only (``analysis_card``,
  ``system``) — a result card is written by the analysis, not by a member — and
  ``messages.payload`` carries a card's ids (run, requirement), never text.

Downgrade deletes the system messages before restoring NOT NULL.

Revision ID: 0006d
Revises: 0006c
Create Date: 2026-11-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006d"
down_revision: str | None = "0006c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("graph_revision", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_projects_graph_revision_non_negative"), "projects", "graph_revision >= 0"
    )

    op.create_table(
        "node_positions",
        sa.Column("requirement_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("x", sa.Float(), nullable=False),
        sa.Column("y", sa.Float(), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["requirement_id"],
            ["requirements.id"],
            name=op.f("fk_node_positions_requirement_id_requirements"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_node_positions_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name=op.f("fk_node_positions_updated_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("requirement_id", name=op.f("pk_node_positions")),
    )
    op.create_index("ix_node_positions_project_id", "node_positions", ["project_id"])

    op.alter_column("messages", "author_id", existing_type=sa.Uuid(), nullable=True)
    op.create_check_constraint(
        op.f("ck_messages_author_or_system"),
        "messages",
        "author_id IS NOT NULL OR kind IN ('analysis_card', 'system')",
    )
    op.add_column(
        "messages", sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("messages", "payload")
    op.drop_constraint(op.f("ck_messages_author_or_system"), "messages", type_="check")
    op.execute("DELETE FROM messages WHERE author_id IS NULL")
    op.alter_column("messages", "author_id", existing_type=sa.Uuid(), nullable=False)

    op.drop_index("ix_node_positions_project_id", table_name="node_positions")
    op.drop_table("node_positions")

    op.drop_constraint(op.f("ck_projects_graph_revision_non_negative"), "projects", type_="check")
    op.drop_column("projects", "graph_revision")
