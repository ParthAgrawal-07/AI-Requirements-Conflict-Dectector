"""enforce at most one finding per candidate pair (US-60, FR-14)

Sprint 1 (Keval; ADR-28, FR-14).
Ensures a candidate pair cannot have duplicate findings inserted by
concurrent workers or duplicate task invocations.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-27
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        op.f("uq_findings_candidate_pair_id"),
        "findings",
        ["candidate_pair_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("uq_findings_candidate_pair_id"),
        "findings",
        type_="unique",
    )
