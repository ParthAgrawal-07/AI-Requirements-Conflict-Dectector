"""lifecycle and runs part 5: requirement transitions, finding reviews, compliance sign-off

Sprint 3 (Parth — US-37, US-10; design update §7.1; FR-18–FR-21, FR-61, FR-98).

* ``requirement_transitions`` — every lifecycle move (Proposed → Under review → Approved…), with
  the version that was decided, the reason (rejections) and whether a High-severity risk was
  accepted. The requirement's history; the audit log keeps ids only.
* ``finding_reviews`` — every human decision on a finding (confirm, dismiss, merge, reclassify,
  reopen, escalate) with the status and category before and after. The finding itself keeps the
  model's verbatim output in ``original_ai_output`` (FR-20), so nothing the AI said is lost.
* ``findings.merged_into_id`` — the finding a merged duplicate finding was folded into.
* ``requirements.signed_off_version`` / ``signed_off_by`` / ``signed_off_at`` — a compliance
  reviewer's sign-off on the exact text of a protected requirement, required before it can be
  approved (FR-21).

Revision ID: 0006e
Revises: 0006d
Create Date: 2026-11-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006e"
down_revision: str | None = "0006d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Enum columns are VARCHAR + CHECK here (``app.models.base.enum_column``); each column has its own
# name so the two CHECKs of one table do not collide. Frozen copies: migrations never import app.
STATES = ("Proposed", "Under_Review", "Approved", "Rejected", "Implemented", "Deprecated")
STATUSES = ("flagged", "confirmed", "dismissed", "merged", "reclassified")
CATEGORIES = ("Conflicting", "Duplicate", "Ambiguous", "Incomplete", "Dependent")


def _enum(name: str, values: tuple[str, ...]) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=False, length=32)


def _check(table: str, column: str, name: str, values: tuple[str, ...]) -> sa.CheckConstraint:
    listed = ", ".join(f"'{v}'" for v in values)
    return sa.CheckConstraint(f"{column} IN ({listed})", name=op.f(f"ck_{table}_{name}"))


def upgrade() -> None:
    op.create_table(
        "requirement_transitions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("requirement_id", sa.Uuid(), nullable=False),
        sa.Column("from_state", _enum("transition_from_state", STATES), nullable=False),
        sa.Column("to_state", _enum("transition_to_state", STATES), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("accepted_risk", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "from_state <> to_state", name=op.f("ck_requirement_transitions_changes_state")
        ),
        _check("requirement_transitions", "from_state", "transition_from_state", STATES),
        _check("requirement_transitions", "to_state", "transition_to_state", STATES),
        sa.ForeignKeyConstraint(
            ["requirement_id"],
            ["requirements.id"],
            name=op.f("fk_requirement_transitions_requirement_id_requirements"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_requirement_transitions_actor_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_requirement_transitions")),
    )
    op.create_index(
        "ix_requirement_transitions_requirement_id_created_at",
        "requirement_transitions",
        ["requirement_id", "created_at"],
    )

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
        op.f("ck_findings_not_merged_into_itself"),
        "findings",
        "merged_into_id IS NULL OR merged_into_id <> id",
    )

    op.create_table(
        "finding_reviews",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("finding_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("from_status", _enum("review_from_status", STATUSES), nullable=False),
        sa.Column("to_status", _enum("review_to_status", STATUSES), nullable=False),
        sa.Column("from_category", _enum("review_from_category", CATEGORIES), nullable=False),
        sa.Column("to_category", _enum("review_to_category", CATEGORIES), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("merged_into_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "action IN ('confirm', 'dismiss', 'merge', 'reclassify', 'reopen', 'escalate')",
            name=op.f("ck_finding_reviews_action_values"),
        ),
        _check("finding_reviews", "from_status", "review_from_status", STATUSES),
        _check("finding_reviews", "to_status", "review_to_status", STATUSES),
        _check("finding_reviews", "from_category", "review_from_category", CATEGORIES),
        _check("finding_reviews", "to_category", "review_to_category", CATEGORIES),
        sa.ForeignKeyConstraint(
            ["finding_id"],
            ["findings.id"],
            name=op.f("fk_finding_reviews_finding_id_findings"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_finding_reviews_actor_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["merged_into_id"],
            ["findings.id"],
            name=op.f("fk_finding_reviews_merged_into_id_findings"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_finding_reviews")),
    )
    op.create_index(
        "ix_finding_reviews_finding_id_created_at",
        "finding_reviews",
        ["finding_id", "created_at"],
    )

    op.add_column("requirements", sa.Column("signed_off_version", sa.Integer(), nullable=True))
    op.add_column("requirements", sa.Column("signed_off_by", sa.Uuid(), nullable=True))
    op.add_column(
        "requirements", sa.Column("signed_off_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_foreign_key(
        op.f("fk_requirements_signed_off_by_users"),
        "requirements",
        "users",
        ["signed_off_by"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_requirements_signed_off_by_users"), "requirements", type_="foreignkey"
    )
    for column in ("signed_off_at", "signed_off_by", "signed_off_version"):
        op.drop_column("requirements", column)

    op.drop_index("ix_finding_reviews_finding_id_created_at", table_name="finding_reviews")
    op.drop_table("finding_reviews")

    op.drop_constraint(op.f("ck_findings_not_merged_into_itself"), "findings", type_="check")
    op.drop_constraint(op.f("fk_findings_merged_into_id_findings"), "findings", type_="foreignkey")
    op.drop_column("findings", "merged_into_id")

    op.drop_index(
        "ix_requirement_transitions_requirement_id_created_at",
        table_name="requirement_transitions",
    )
    op.drop_table("requirement_transitions")
