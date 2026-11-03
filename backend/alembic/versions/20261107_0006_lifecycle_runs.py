"""lifecycle and runs part 1: per-pair classification status (G1), analysis_runs, role deletion

Sprint 2 (Parth; design update §4.1, §4.3 ``0006_lifecycle_runs``). Later parts of the same
family: ``0006b`` (drafts and posts, Bansil) and ``0006c`` (finding changes, Keval).

* ``candidate_pairs`` — ``classification_status`` (pending, done, failed), ``attempts``,
  ``last_error``, ``classified_at`` and the requirement versions last classified (gap G1: a pair
  that fails is recorded, never dropped; an unchanged pair is never classified twice).
* ``analysis_runs`` — one row per analysis (document scope in Sprint 2), counting candidate pairs
  and single-requirement checks.
* ``roles.deleted_at`` — custom roles are deleted softly (US-49) because ended memberships and old
  join codes keep referencing them (FK ``RESTRICT``). The per-workspace unique name index now
  ignores deleted roles, so a name can be reused.

Revision ID: 0006
Revises: 0005b
Create Date: 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Frozen copies of the enums.
CLASSIFICATION_STATUSES = ("pending", "done", "failed")
RUN_STATUSES = ("queued", "waiting_budget", "running", "done", "failed")
RUN_SCOPES = ("document", "requirement", "change_request")


def _in_list(column: str, values: Sequence[str]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _enum(values: Sequence[str], name: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=False, length=32)


def upgrade() -> None:
    op.add_column(
        "candidate_pairs",
        sa.Column(
            "classification_status",
            _enum(CLASSIFICATION_STATUSES, "classification_status"),
            server_default="pending",
            nullable=False,
        ),
    )
    op.add_column(
        "candidate_pairs",
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column("candidate_pairs", sa.Column("last_error", sa.String(length=64), nullable=True))
    op.add_column(
        "candidate_pairs", sa.Column("classified_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("candidate_pairs", sa.Column("a_version", sa.Integer(), nullable=True))
    op.add_column("candidate_pairs", sa.Column("b_version", sa.Integer(), nullable=True))
    op.create_check_constraint(
        op.f("ck_candidate_pairs_classification_status"),
        "candidate_pairs",
        _in_list("classification_status", CLASSIFICATION_STATUSES),
    )
    op.create_check_constraint(
        op.f("ck_candidate_pairs_attempts_non_negative"), "candidate_pairs", "attempts >= 0"
    )
    op.create_index(
        "ix_candidate_pairs_classification_status", "candidate_pairs", ["classification_status"]
    )
    # Pairs that already have a finding were classified by the Sprint 1 skeleton.
    op.execute(
        """
        UPDATE candidate_pairs p SET classification_status = 'done', attempts = 1,
            classified_at = now()
        WHERE EXISTS (SELECT 1 FROM findings f WHERE f.candidate_pair_id = p.id)
        """
    )

    op.create_table(
        "analysis_runs",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("scope", _enum(RUN_SCOPES, "analysis_scope"), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            _enum(RUN_STATUSES, "analysis_run_status"),
            server_default="queued",
            nullable=False,
        ),
        sa.Column("pairs_total", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("pairs_done", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("pairs_failed", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("checks_total", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("checks_done", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("checks_failed", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("llm_calls", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            _in_list("scope", RUN_SCOPES), name=op.f("ck_analysis_runs_analysis_scope")
        ),
        sa.CheckConstraint(
            _in_list("status", RUN_STATUSES), name=op.f("ck_analysis_runs_analysis_run_status")
        ),
        sa.CheckConstraint(
            "pairs_total >= 0 AND pairs_done >= 0 AND pairs_failed >= 0 AND llm_calls >= 0"
            " AND checks_total >= 0 AND checks_done >= 0 AND checks_failed >= 0",
            name=op.f("ck_analysis_runs_counts_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_analysis_runs_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_analysis_runs")),
    )
    op.create_index(
        "ix_analysis_runs_project_id_created_at", "analysis_runs", ["project_id", "created_at"]
    )
    op.create_index("ix_analysis_runs_subject_id", "analysis_runs", ["subject_id"])

    op.add_column("roles", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.drop_index("uq_roles_workspace_id_name", table_name="roles")
    op.create_index(
        "uq_roles_workspace_id_name",
        "roles",
        ["workspace_id", "name"],
        unique=True,
        postgresql_where=sa.text("workspace_id IS NOT NULL AND deleted_at IS NULL"),
    )


def downgrade() -> None:
    # Deleted roles would collide with live ones under the old index; rename them first.
    op.execute(
        """
        UPDATE roles SET name = left(name, 70) || ' (' || left(id::text, 8) || ')'
        WHERE deleted_at IS NOT NULL
        """
    )
    op.drop_index("uq_roles_workspace_id_name", table_name="roles")
    op.create_index(
        "uq_roles_workspace_id_name",
        "roles",
        ["workspace_id", "name"],
        unique=True,
        postgresql_where=sa.text("workspace_id IS NOT NULL"),
    )
    op.drop_column("roles", "deleted_at")

    op.drop_index("ix_analysis_runs_subject_id", table_name="analysis_runs")
    op.drop_index("ix_analysis_runs_project_id_created_at", table_name="analysis_runs")
    op.drop_table("analysis_runs")

    op.drop_index("ix_candidate_pairs_classification_status", table_name="candidate_pairs")
    op.drop_constraint(
        op.f("ck_candidate_pairs_attempts_non_negative"), "candidate_pairs", type_="check"
    )
    op.drop_constraint(
        op.f("ck_candidate_pairs_classification_status"), "candidate_pairs", type_="check"
    )
    for column in (
        "b_version",
        "a_version",
        "classified_at",
        "last_error",
        "attempts",
        "classification_status",
    ):
        op.drop_column("candidate_pairs", column)
