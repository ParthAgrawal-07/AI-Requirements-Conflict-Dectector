"""issues and change requests part 3: consequence reports, the project's baseline revision

Sprint 4 (Madhav — US-11, US-34, FR-24, FR-25, FR-64, FR-99; design update §3.2, §11.4).

* ``consequence_reports`` — one row per run of a change request's checks: what it ran on
  (``proposal_revision``, ``base_version``, ``baseline_revision``), the affected requirements
  with owners and reasons, the checks (each ``pending``, ``pass``, ``warning``, ``fail`` or
  ``info``), the findings delta (``resolved``, ``new``, ``still_open``, ``must_rerun``), the risk
  level and, from Keval, the AI narrative. ``is_stale`` is set when the baseline or the
  requirement moves on before a decision. Rows are history: the newest one is the report.
* ``projects.baseline_revision`` — +1 on every merged change (Parth, US-35), so a report knows
  whether the baseline it was computed against is still the baseline.

Revision ID: 0007b
Revises: 0010a
Create Date: 2026-12-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007b"
down_revision: str | None = "0010a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _jsonb(name: str, default: str) -> sa.Column[postgresql.JSONB]:
    return sa.Column(
        name,
        postgresql.JSONB(astext_type=sa.Text()),
        server_default=sa.text(f"'{default}'::jsonb"),
        nullable=False,
    )


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("baseline_revision", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_projects_baseline_revision_non_negative"), "projects", "baseline_revision >= 0"
    )
    op.create_table(
        "consequence_reports",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("change_request_id", sa.Uuid(), nullable=False),
        sa.Column("proposal_revision", sa.Integer(), nullable=False),
        sa.Column("base_version", sa.Integer(), nullable=False),
        sa.Column("baseline_revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="done", nullable=False),
        sa.Column("risk_level", sa.String(length=8), nullable=True),
        _jsonb("risk_reasons", "[]"),
        _jsonb("affected", "[]"),
        _jsonb("checks", "[]"),
        _jsonb("findings_delta", '{"resolved": [], "new": [], "still_open": [], "must_rerun": []}'),
        sa.Column("narrative", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_stale", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("llm_calls", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('done', 'failed')", name=op.f("ck_consequence_reports_status_values")
        ),
        sa.CheckConstraint(
            "risk_level IS NULL OR risk_level IN ('low', 'medium', 'high')",
            name=op.f("ck_consequence_reports_risk_level_values"),
        ),
        sa.ForeignKeyConstraint(
            ["change_request_id"],
            ["change_requests.id"],
            name=op.f("fk_consequence_reports_change_request_id_change_requests"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_consequence_reports")),
    )
    op.create_index(
        "ix_consequence_reports_change_request_id_created_at",
        "consequence_reports",
        ["change_request_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_consequence_reports_change_request_id_created_at", table_name="consequence_reports"
    )
    op.drop_table("consequence_reports")
    op.drop_constraint(
        op.f("ck_projects_baseline_revision_non_negative"), "projects", type_="check"
    )
    op.drop_column("projects", "baseline_revision")
