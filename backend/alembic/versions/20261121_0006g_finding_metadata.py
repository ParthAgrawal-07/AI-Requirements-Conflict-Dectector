"""Finding provenance and merge linkage (US-09, US-10; ADR-31).

Revision ID: 0006g
Revises: 0006d
"""

import sqlalchemy as sa
from alembic import op

revision = "0006g"
down_revision = "0006d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("findings", sa.Column("llm_model", sa.String(80), nullable=True))
    op.add_column("findings", sa.Column("merged_into_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_findings_merged_into_id_findings"),
        "findings",
        "findings",
        ["merged_into_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "not_merged_into_itself", "findings", "merged_into_id IS NULL OR merged_into_id <> id"
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_findings_not_merged_into_itself"), "findings", type_="check")
    op.drop_constraint(op.f("fk_findings_merged_into_id_findings"), "findings", type_="foreignkey")
    op.drop_column("findings", "merged_into_id")
    op.drop_column("findings", "llm_model")
