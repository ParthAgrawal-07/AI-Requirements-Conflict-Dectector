"""lifecycle and runs part 6: ownership requests

Sprint 3 (Bansil — US-36, FR-59, DR-11).

``ownership_requests`` — a member asks to own a requirement; its current owner or a manager
accepts or declines. At most one *pending* request per requester and requirement.

Revision ID: 0006f
Revises: 0006e
Create Date: 2026-11-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006f"
down_revision: str | None = "0006e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ownership_requests",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("requirement_id", sa.Uuid(), nullable=False),
        sa.Column("requester_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("decided_by", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'declined')",
            name=op.f("ck_ownership_requests_status_values"),
        ),
        sa.ForeignKeyConstraint(
            ["requirement_id"],
            ["requirements.id"],
            name=op.f("fk_ownership_requests_requirement_id_requirements"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requester_id"],
            ["users.id"],
            name=op.f("fk_ownership_requests_requester_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["decided_by"],
            ["users.id"],
            name=op.f("fk_ownership_requests_decided_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ownership_requests")),
    )
    op.create_index(
        "ix_ownership_requests_requirement_id_status",
        "ownership_requests",
        ["requirement_id", "status"],
    )
    op.create_index(
        "uq_ownership_requests_one_pending",
        "ownership_requests",
        ["requirement_id", "requester_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("uq_ownership_requests_one_pending", table_name="ownership_requests")
    op.drop_index("ix_ownership_requests_requirement_id_status", table_name="ownership_requests")
    op.drop_table("ownership_requests")
