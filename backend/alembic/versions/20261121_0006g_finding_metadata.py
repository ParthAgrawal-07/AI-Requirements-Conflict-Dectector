"""Finding provenance (US-09; ADR-31).

Revision ID: 0006g
Revises: 0006e
"""

import sqlalchemy as sa
from alembic import op

revision = "0006g"
down_revision = "0006e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("findings", sa.Column("llm_model", sa.String(80), nullable=True))


def downgrade() -> None:
    op.drop_column("findings", "llm_model")
