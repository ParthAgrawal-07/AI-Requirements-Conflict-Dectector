"""issues and change requests part 1: issues, their requirements and assignees, comments

Sprint 4 (Dhavni — US-52, FR-86, FR-87; design update §3.5, §4.1.1, §7.4).

* ``issues`` — ISS-n, numbered per project; ``open`` or ``closed`` with a ``close_reason``
  (``resolved_by_merge``, ``finding_resolved``, ``manual``). An **auto** conflict issue names its
  finding, and there is at most one auto issue per finding.
* ``issue_requirements`` and ``issue_assignees`` — the requirements an issue is about and the
  people it is assigned to (for an auto issue: every owner involved).
* ``comments`` — one table for comments on issues now and on requirements and change requests
  later (``subject_type``, ``subject_id``); ``author_id`` is NULL for a comment the app wrote
  (an auto issue's clarification question).

Change requests, consequence reports and reviews follow in 0007a–0007c.

Revision ID: 0007
Revises: 0006h
Create Date: 2026-12-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006h"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column[sa.DateTime]]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "issues",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), server_default="", nullable=False),
        sa.Column("status", sa.String(length=16), server_default="open", nullable=False),
        sa.Column("close_reason", sa.String(length=32), nullable=True),
        sa.Column("auto", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("finding_id", sa.Uuid(), nullable=True),
        sa.Column("author_id", sa.Uuid(), nullable=True),
        sa.Column(
            "labels",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("closed_by", sa.Uuid(), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("status IN ('open', 'closed')", name=op.f("ck_issues_status_values")),
        sa.CheckConstraint(
            "close_reason IS NULL OR close_reason IN "
            "('resolved_by_merge', 'finding_resolved', 'manual')",
            name=op.f("ck_issues_close_reason_values"),
        ),
        sa.CheckConstraint(
            "(status = 'closed') = (close_reason IS NOT NULL)",
            name=op.f("ck_issues_closed_has_reason"),
        ),
        sa.CheckConstraint("number >= 1", name=op.f("ck_issues_number_positive")),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_issues_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["finding_id"],
            ["findings.id"],
            name=op.f("fk_issues_finding_id_findings"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["author_id"], ["users.id"], name=op.f("fk_issues_author_id_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["closed_by"], ["users.id"], name=op.f("fk_issues_closed_by_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_issues")),
        sa.UniqueConstraint("project_id", "number", name=op.f("uq_issues_project_id_number")),
    )
    op.create_index("ix_issues_project_id_status", "issues", ["project_id", "status"])
    op.create_index(
        "uq_issues_auto_finding_id",
        "issues",
        ["finding_id"],
        unique=True,
        postgresql_where=sa.text("auto AND finding_id IS NOT NULL"),
    )

    op.create_table(
        "issue_requirements",
        sa.Column("issue_id", sa.Uuid(), nullable=False),
        sa.Column("requirement_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["issue_id"],
            ["issues.id"],
            name=op.f("fk_issue_requirements_issue_id_issues"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requirement_id"],
            ["requirements.id"],
            name=op.f("fk_issue_requirements_requirement_id_requirements"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("issue_id", "requirement_id", name=op.f("pk_issue_requirements")),
    )
    op.create_index(
        "ix_issue_requirements_requirement_id", "issue_requirements", ["requirement_id"]
    )

    op.create_table(
        "issue_assignees",
        sa.Column("issue_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["issue_id"],
            ["issues.id"],
            name=op.f("fk_issue_assignees_issue_id_issues"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_issue_assignees_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("issue_id", "user_id", name=op.f("pk_issue_assignees")),
    )
    op.create_index("ix_issue_assignees_user_id", "issue_assignees", ["user_id"])

    op.create_table(
        "comments",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("subject_type", sa.String(length=16), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "subject_type IN ('requirement', 'issue', 'change_request')",
            name=op.f("ck_comments_subject_type_values"),
        ),
        sa.CheckConstraint("length(body) > 0", name=op.f("ck_comments_body_not_empty")),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["users.id"],
            name=op.f("fk_comments_author_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_comments")),
    )
    op.create_index(
        "ix_comments_subject_type_subject_id_created_at",
        "comments",
        ["subject_type", "subject_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_comments_subject_type_subject_id_created_at", table_name="comments")
    op.drop_table("comments")
    op.drop_index("ix_issue_assignees_user_id", table_name="issue_assignees")
    op.drop_table("issue_assignees")
    op.drop_index("ix_issue_requirements_requirement_id", table_name="issue_requirements")
    op.drop_table("issue_requirements")
    op.drop_index("uq_issues_auto_finding_id", table_name="issues")
    op.drop_index("ix_issues_project_id_status", table_name="issues")
    op.drop_table("issues")
