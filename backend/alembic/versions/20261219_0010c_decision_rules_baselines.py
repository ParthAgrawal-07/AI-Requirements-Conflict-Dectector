"""decision rules, decisions on findings, issues and change requests; baselines

Sprint 5 (Parth — US-57, US-40, FR-65, FR-73, FR-100, DR-08, DR-23; design update §4.1, §11.1;
ADR-26).

* ``decision_rules`` — per project: what a rule matches (category, label, stakeholder group,
  requirement type, protected) and who decides (a role, a person, or the requirement owner),
  with required and optional reviewers. One default rule per project (matches everything).
* ``findings.decision``, ``issues.decision``, ``change_requests.decision`` — the decision as it
  was resolved for that item (rule, owner, reviewers). A rule edited later applies to an open
  item at its next update, not retroactively.
* ``review_requests.reason`` gains ``decision_owner`` and ``decision_rule``: who the rule
  asked to review.
* ``baselines`` and ``baseline_items`` — labelled, frozen snapshots: each Approved or Implemented
  requirement with its version and text at that moment. A trigger keeps both immutable (a
  project's deletion still cascades).

Revision ID: 0010c
Revises: 0008
Create Date: 2026-12-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010c"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

IMMUTABLE = """
CREATE OR REPLACE FUNCTION baseline_immutable() RETURNS trigger AS $$
BEGIN
    IF pg_trigger_depth() > 1 THEN  -- the cascade of a deleted project
        RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
    END IF;
    RAISE EXCEPTION 'baselines are immutable (%)', TG_OP USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql;
"""


def _jsonb_list(name: str) -> sa.Column[object]:
    return sa.Column(
        name,
        postgresql.JSONB(astext_type=sa.Text()),
        server_default=sa.text("'[]'::jsonb"),
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "decision_rules",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("priority", sa.Integer(), server_default=sa.text("100"), nullable=False),
        sa.Column("match_category", sa.String(length=32), nullable=True),
        sa.Column("match_label", sa.String(length=64), nullable=True),
        sa.Column("match_group", sa.String(length=120), nullable=True),
        sa.Column("match_req_type", sa.String(length=32), nullable=True),
        sa.Column("match_protected", sa.Boolean(), nullable=True),
        sa.Column("owner_kind", sa.String(length=24), nullable=False),
        sa.Column("owner_role_id", sa.Uuid(), nullable=True),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        _jsonb_list("required_reviewers"),
        _jsonb_list("optional_reviewers"),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "owner_kind IN ('role', 'user', 'requirement_owner')",
            name=op.f("ck_decision_rules_owner_kind_values"),
        ),
        sa.CheckConstraint(
            "(owner_kind = 'role') = (owner_role_id IS NOT NULL)",
            name=op.f("ck_decision_rules_role_owner_has_role"),
        ),
        sa.CheckConstraint(
            "(owner_kind = 'user') = (owner_user_id IS NOT NULL)",
            name=op.f("ck_decision_rules_user_owner_has_user"),
        ),
        sa.CheckConstraint(
            "NOT is_default OR num_nonnulls(match_category, match_label, match_group, "
            "match_req_type, match_protected) = 0",
            name=op.f("ck_decision_rules_default_matches_all"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_decision_rules_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_role_id"],
            ["roles.id"],
            name=op.f("fk_decision_rules_owner_role_id_roles"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name=op.f("fk_decision_rules_owner_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_decision_rules_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_decision_rules")),
    )
    op.create_index("ix_decision_rules_project_id", "decision_rules", ["project_id"])
    op.create_index(
        "uq_decision_rules_default_project_id",
        "decision_rules",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )
    op.drop_constraint(op.f("ck_review_requests_reason_values"), "review_requests", type_="check")
    op.create_check_constraint(
        op.f("ck_review_requests_reason_values"),
        "review_requests",
        "reason IN ('owner', 'direct_conflict', 'merge_quota', 'compliance', 'transitive', 'requested', 'decision_owner', 'decision_rule')",
    )
    for table in ("findings", "issues", "change_requests"):
        op.add_column(
            table, sa.Column("decision", postgresql.JSONB(astext_type=sa.Text()), nullable=True)
        )

    op.create_table(
        "baselines",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("label", sa.String(length=80), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("baseline_revision", sa.Integer(), nullable=False),
        sa.Column("requirement_count", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("length(trim(label)) > 0", name=op.f("ck_baselines_label_not_blank")),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_baselines_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_baselines_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_baselines")),
        sa.UniqueConstraint("project_id", "label", name=op.f("uq_baselines_project_id_label")),
    )
    op.create_table(
        "baseline_items",
        sa.Column("baseline_id", sa.Uuid(), nullable=False),
        sa.Column("requirement_id", sa.Uuid(), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=64), nullable=True),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["baseline_id"],
            ["baselines.id"],
            name=op.f("fk_baseline_items_baseline_id_baselines"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requirement_id"],
            ["requirements.id"],
            name=op.f("fk_baseline_items_requirement_id_requirements"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("baseline_id", "requirement_id", name=op.f("pk_baseline_items")),
    )
    op.execute(IMMUTABLE)
    for table in ("baselines", "baseline_items"):
        op.execute(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION baseline_immutable()"
        )


def downgrade() -> None:
    for table in ("baseline_items", "baselines"):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_immutable ON {table}")
    op.execute("DROP FUNCTION IF EXISTS baseline_immutable()")
    op.drop_table("baseline_items")
    op.drop_table("baselines")
    for table in ("change_requests", "issues", "findings"):
        op.drop_column(table, "decision")
    op.execute("DELETE FROM review_requests WHERE reason IN ('decision_owner', 'decision_rule')")
    op.drop_constraint(op.f("ck_review_requests_reason_values"), "review_requests", type_="check")
    op.create_check_constraint(
        op.f("ck_review_requests_reason_values"),
        "review_requests",
        "reason IN ('owner', 'direct_conflict', 'merge_quota', 'compliance', 'transitive', 'requested')",
    )
    op.drop_index("uq_decision_rules_default_project_id", table_name="decision_rules")
    op.drop_index("ix_decision_rules_project_id", table_name="decision_rules")
    op.drop_table("decision_rules")
