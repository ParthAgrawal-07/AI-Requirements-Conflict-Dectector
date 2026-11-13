"""lifecycle and runs part 3: finding changes for the detection engine

Sprint 2 (Keval — US-05, US-07; design update §4.1 ``FINDING``, §4.3 ``0006_lifecycle_runs``).

* ``findings.project_id`` (backfilled from the document), ``document_id`` now nullable (findings
  about posted requirements have no document), ``analysis_run_id``, ``is_stale``;
* ``explanation`` and ``evidence_spans`` (US-07) and the ``prompt_version`` that produced it;
* one *live* finding per pair, so a pair task delivered twice can never store a duplicate;
* ``requirements.single_checked_version`` — the version last checked for Ambiguous/Incomplete.

Downgrade deletes findings without a document before restoring NOT NULL, and keeps one finding
per pair (the live one) before restoring the unique constraint.

Revision ID: 0006c
Revises: 0006b
Create Date: 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006c"
down_revision: str | None = "0006b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(op.f("uq_findings_candidate_pair_id"), "findings", type_="unique")
    op.add_column("findings", sa.Column("project_id", sa.Uuid(), nullable=True))
    op.execute(
        "UPDATE findings f SET project_id = d.project_id FROM documents d WHERE d.id = f.document_id"
    )
    op.alter_column("findings", "project_id", existing_type=sa.Uuid(), nullable=False)
    op.create_foreign_key(
        op.f("fk_findings_project_id_projects"),
        "findings",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_findings_project_id_status", "findings", ["project_id", "status"])
    op.alter_column("findings", "document_id", existing_type=sa.Uuid(), nullable=True)

    op.add_column("findings", sa.Column("analysis_run_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_findings_analysis_run_id_analysis_runs"),
        "findings",
        "analysis_runs",
        ["analysis_run_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column("findings", sa.Column("explanation", sa.Text(), nullable=True))
    op.add_column(
        "findings",
        sa.Column(
            "evidence_spans",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column("findings", sa.Column("prompt_version", sa.String(length=16), nullable=True))
    op.add_column(
        "findings",
        sa.Column("is_stale", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.create_index(
        "uq_findings_live_pair",
        "findings",
        ["candidate_pair_id"],
        unique=True,
        postgresql_where=sa.text("candidate_pair_id IS NOT NULL AND NOT is_stale"),
    )

    op.add_column("requirements", sa.Column("single_checked_version", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("requirements", "single_checked_version")
    op.drop_index("uq_findings_live_pair", table_name="findings")
    # 0006c allows stale findings next to the live one for a pair; the restored constraint allows
    # one. Keep the live (else newest) finding per pair, as the pre-0006c schema would have.
    op.execute(
        """
        DELETE FROM findings WHERE id IN (
            SELECT id FROM (
                SELECT id, row_number() OVER (
                    PARTITION BY candidate_pair_id ORDER BY is_stale, created_at DESC, id
                ) AS n
                FROM findings WHERE candidate_pair_id IS NOT NULL
            ) ranked WHERE n > 1
        )
        """
    )
    for column in ("is_stale", "prompt_version", "evidence_spans", "explanation"):
        op.drop_column("findings", column)
    op.drop_constraint(
        op.f("fk_findings_analysis_run_id_analysis_runs"), "findings", type_="foreignkey"
    )
    op.drop_column("findings", "analysis_run_id")
    op.execute("DELETE FROM findings WHERE document_id IS NULL")
    op.alter_column("findings", "document_id", existing_type=sa.Uuid(), nullable=False)
    op.drop_index("ix_findings_project_id_status", table_name="findings")
    op.drop_constraint(op.f("fk_findings_project_id_projects"), "findings", type_="foreignkey")
    op.drop_column("findings", "project_id")
    op.create_unique_constraint(
        op.f("uq_findings_candidate_pair_id"),
        "findings",
        ["candidate_pair_id"],
    )
