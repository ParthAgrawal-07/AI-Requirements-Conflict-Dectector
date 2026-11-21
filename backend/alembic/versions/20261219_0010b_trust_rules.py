"""trust layer part 2: requirement attributes and rule findings

Sprint 5 (Heet — US-58, FR-101, NFR-37; design update §11.1, §11.5; ADR-27).

* ``requirement_attributes`` — one row per requirement **version**: entity, metric, value and
  unit, comparison, actor, action, condition, negation, modality, how it was extracted
  (``rules`` or ``llm``) and with what confidence. Indexed by (project, entity) and (project,
  metric): the rule checker compares requirements that share either, whatever their similarity.
* ``findings.rule_id`` — the rule that fired (``numeric_limit``, ``negation``, ``actor``,
  ``condition_overlap``), required for ``source = 'rule'``.
* One live finding per pair (``uq_findings_live_pair``) now binds **the AI** only; a rule may
  flag the same pair once per rule (``uq_findings_live_rule``). A rule finding is never dropped
  because the model disagrees.

Revision ID: 0010b
Revises: 0007c
Create Date: 2026-12-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010b"
down_revision: str | None = "0007c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "requirement_attributes",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("requirement_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("entity", sa.String(length=120), nullable=True),
        sa.Column("metric", sa.String(length=80), nullable=True),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(length=16), nullable=True),
        sa.Column("comparison", sa.String(length=2), nullable=True),
        sa.Column("actor", sa.String(length=120), nullable=True),
        sa.Column("action", sa.String(length=120), nullable=True),
        sa.Column("condition", sa.String(length=200), nullable=True),
        sa.Column("negated", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("modality", sa.String(length=16), nullable=True),
        sa.Column("extractor", sa.String(length=8), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "extractor IN ('rules', 'llm')", name=op.f("ck_requirement_attributes_extractor_values")
        ),
        sa.CheckConstraint(
            "comparison IS NULL OR comparison IN ('<=', '>=', '=')",
            name=op.f("ck_requirement_attributes_comparison_values"),
        ),
        sa.CheckConstraint(
            "confidence BETWEEN 0 AND 1", name=op.f("ck_requirement_attributes_confidence_range")
        ),
        sa.CheckConstraint(
            "version_no >= 1", name=op.f("ck_requirement_attributes_version_positive")
        ),
        sa.ForeignKeyConstraint(
            ["requirement_id"],
            ["requirements.id"],
            name=op.f("fk_requirement_attributes_requirement_id_requirements"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_requirement_attributes_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_requirement_attributes")),
        sa.UniqueConstraint(
            "requirement_id",
            "version_no",
            name=op.f("uq_requirement_attributes_requirement_id_version_no"),
        ),
    )
    op.create_index(
        "ix_requirement_attributes_project_id_entity",
        "requirement_attributes",
        ["project_id", "entity"],
    )
    op.create_index(
        "ix_requirement_attributes_project_id_metric",
        "requirement_attributes",
        ["project_id", "metric"],
    )

    op.add_column("findings", sa.Column("rule_id", sa.String(length=64), nullable=True))
    op.create_check_constraint(
        op.f("ck_findings_rule_has_rule_id"),
        "findings",
        "(source = 'rule') = (rule_id IS NOT NULL)",
    )
    op.drop_index("uq_findings_live_pair", table_name="findings")
    op.create_index(
        "uq_findings_live_pair",
        "findings",
        ["candidate_pair_id"],
        unique=True,
        postgresql_where=sa.text(
            "candidate_pair_id IS NOT NULL AND NOT is_stale AND source = 'ai'"
        ),
    )
    op.create_index(
        "uq_findings_live_rule",
        "findings",
        ["candidate_pair_id", "rule_id"],
        unique=True,
        postgresql_where=sa.text(
            "candidate_pair_id IS NOT NULL AND NOT is_stale AND source = 'rule'"
        ),
    )


def downgrade() -> None:
    op.execute("DELETE FROM findings WHERE source = 'rule'")
    op.drop_index("uq_findings_live_rule", table_name="findings")
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
    op.drop_constraint(op.f("ck_findings_rule_has_rule_id"), "findings", type_="check")
    op.drop_column("findings", "rule_id")
    op.drop_index(
        "ix_requirement_attributes_project_id_metric", table_name="requirement_attributes"
    )
    op.drop_index(
        "ix_requirement_attributes_project_id_entity", table_name="requirement_attributes"
    )
    op.drop_table("requirement_attributes")
