"""issues and change requests part 2: change requests, their proposal revisions, resolved issues

Sprint 4 (Bansil — US-33, FR-62, FR-65, FR-89, FR-98; design update §3.2, §7.2, §11.1).

* ``change_requests`` — RCR-n per project, against one requirement: ``modify`` (new text) or
  ``deprecate`` (no text). ``base_version`` is the requirement version the proposal was written
  against; ``proposal_revision`` starts at 1 and goes up on every edit of the proposal, so
  approvals and checks bind to exact text (``checks_proposal_revision`` /
  ``checks_base_version`` record what the checks last ran on). Status: ``draft``, ``open``,
  ``needs_update``, ``approved``, ``merged``, ``closed``, ``withdrawn``.
* ``change_request_revisions`` — every proposal revision as written (append-only), for the
  history and the diff between revisions.
* ``change_request_issues`` — "Resolves ISS-n": the issues a merge closes.

Revision ID: 0007a
Revises: 0007
Create Date: 2026-12-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007a"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATUSES = "'draft', 'open', 'needs_update', 'approved', 'merged', 'closed', 'withdrawn'"


def upgrade() -> None:
    op.create_table(
        "change_requests",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("requirement_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("proposer_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=16), server_default="modify", nullable=False),
        sa.Column("status", sa.String(length=16), server_default="open", nullable=False),
        sa.Column("base_version", sa.Integer(), nullable=False),
        sa.Column("proposal_revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("proposed_body", sa.Text(), nullable=True),
        sa.Column("proposed_fields", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("checks_proposal_revision", sa.Integer(), nullable=True),
        sa.Column("checks_base_version", sa.Integer(), nullable=True),
        sa.Column("merged_version", sa.Integer(), nullable=True),
        sa.Column("merged_by", sa.Uuid(), nullable=True),
        sa.Column("merged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by", sa.Uuid(), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("close_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "kind IN ('modify', 'deprecate')", name=op.f("ck_change_requests_kind_values")
        ),
        sa.CheckConstraint(
            f"status IN ({STATUSES})", name=op.f("ck_change_requests_status_values")
        ),
        sa.CheckConstraint(
            "(kind = 'deprecate') = (proposed_body IS NULL)",
            name=op.f("ck_change_requests_body_matches_kind"),
        ),
        sa.CheckConstraint(
            "base_version >= 1", name=op.f("ck_change_requests_base_version_positive")
        ),
        sa.CheckConstraint(
            "proposal_revision >= 1", name=op.f("ck_change_requests_proposal_revision_positive")
        ),
        sa.CheckConstraint("number >= 1", name=op.f("ck_change_requests_number_positive")),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_change_requests_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requirement_id"],
            ["requirements.id"],
            name=op.f("fk_change_requests_requirement_id_requirements"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["proposer_id"],
            ["users.id"],
            name=op.f("fk_change_requests_proposer_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["merged_by"],
            ["users.id"],
            name=op.f("fk_change_requests_merged_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["closed_by"],
            ["users.id"],
            name=op.f("fk_change_requests_closed_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_change_requests")),
        sa.UniqueConstraint(
            "project_id", "number", name=op.f("uq_change_requests_project_id_number")
        ),
    )
    op.create_index(
        "ix_change_requests_requirement_id_status", "change_requests", ["requirement_id", "status"]
    )
    op.create_index(
        "ix_change_requests_project_id_status", "change_requests", ["project_id", "status"]
    )

    op.create_table(
        "change_request_revisions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("change_request_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("proposed_body", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["change_request_id"],
            ["change_requests.id"],
            name=op.f("fk_change_request_revisions_change_request_id_change_requests"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["users.id"],
            name=op.f("fk_change_request_revisions_author_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_change_request_revisions")),
        sa.UniqueConstraint(
            "change_request_id",
            "revision",
            name=op.f("uq_change_request_revisions_change_request_id_revision"),
        ),
    )

    op.create_table(
        "change_request_issues",
        sa.Column("change_request_id", sa.Uuid(), nullable=False),
        sa.Column("issue_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["change_request_id"],
            ["change_requests.id"],
            name=op.f("fk_change_request_issues_change_request_id_change_requests"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["issue_id"],
            ["issues.id"],
            name=op.f("fk_change_request_issues_issue_id_issues"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "change_request_id", "issue_id", name=op.f("pk_change_request_issues")
        ),
    )
    op.create_index("ix_change_request_issues_issue_id", "change_request_issues", ["issue_id"])


def downgrade() -> None:
    op.drop_index("ix_change_request_issues_issue_id", table_name="change_request_issues")
    op.drop_table("change_request_issues")
    op.drop_table("change_request_revisions")
    op.drop_index("ix_change_requests_project_id_status", table_name="change_requests")
    op.drop_index("ix_change_requests_requirement_id_status", table_name="change_requests")
    op.drop_table("change_requests")
