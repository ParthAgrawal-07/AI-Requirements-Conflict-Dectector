"""trust layer part 1: who found a finding — the AI, a rule, or a person

Sprint 4 (Bansil — US-56, FR-97, NFR-37; design update §11.1, §11.2; ADR-25).

``findings`` gains:

* ``source`` — ``ai`` (backfilled for every existing row), ``rule`` (Sprint 5 rule checks) or
  ``person`` (a raised concern);
* ``raised_by`` and ``external_ref`` — who raised a concern and what they cite ("Contract §7.2");
* ``ai_miss`` — set on a concern when neither the AI nor a rule had a finding on the same
  requirements: the count NFR-37 reports.

One live finding per pair (``uq_findings_live_pair``, 0006c) now holds for the analysis only: a
person may raise a concern about a pair the AI has already flagged, and the AI may later flag a
pair someone raised.

Revision ID: 0010a
Revises: 0007a
Create Date: 2026-12-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010a"
down_revision: str | None = "0007a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "findings", sa.Column("source", sa.String(length=16), server_default="ai", nullable=False)
    )
    op.add_column("findings", sa.Column("raised_by", sa.Uuid(), nullable=True))
    op.add_column("findings", sa.Column("external_ref", sa.String(length=200), nullable=True))
    op.add_column(
        "findings",
        sa.Column("ai_miss", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_findings_source_values"), "findings", "source IN ('ai', 'rule', 'person')"
    )
    op.create_foreign_key(
        op.f("fk_findings_raised_by_users"),
        "findings",
        "users",
        ["raised_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.drop_index("uq_findings_live_pair", table_name="findings")
    op.create_index(
        "uq_findings_live_pair",
        "findings",
        ["candidate_pair_id"],
        unique=True,
        postgresql_where=sa.text(
            "candidate_pair_id IS NOT NULL AND NOT is_stale AND source <> 'person'"
        ),
    )


def downgrade() -> None:
    op.execute("DELETE FROM findings WHERE source = 'person'")
    op.drop_index("uq_findings_live_pair", table_name="findings")
    op.create_index(
        "uq_findings_live_pair",
        "findings",
        ["candidate_pair_id"],
        unique=True,
        postgresql_where=sa.text("candidate_pair_id IS NOT NULL AND NOT is_stale"),
    )
    op.drop_constraint(op.f("fk_findings_raised_by_users"), "findings", type_="foreignkey")
    op.drop_constraint(op.f("ck_findings_source_values"), "findings", type_="check")
    op.drop_column("findings", "ai_miss")
    op.drop_column("findings", "external_ref")
    op.drop_column("findings", "raised_by")
    op.drop_column("findings", "source")
