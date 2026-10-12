"""requirements: section_heading, needs_review, review_reason (US-02)

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-12 00:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "requirements", sa.Column("section_heading", sa.String(length=255), nullable=True)
    )
    op.add_column(
        "requirements",
        sa.Column("needs_review", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column("requirements", sa.Column("review_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("requirements", "review_reason")
    op.drop_column("requirements", "needs_review")
    op.drop_column("requirements", "section_heading")
