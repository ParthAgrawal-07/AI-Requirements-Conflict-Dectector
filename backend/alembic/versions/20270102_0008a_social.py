"""votes, watches and human requirement links

Sprint 6 (Madhav — US-53, FR-80, FR-90, FR-91, DR-17, DR-19; design update §4.1).

* ``votes`` — support or oppose a requirement or a change request, one per member and subject,
  with an optional reason. Display only: no state or agreement rule reads them (DR-17).
* ``watches`` — a member follows a requirement, issue or change request (notifications, US-38).
* ``requirement_links`` — *depends on*, *refines*, *related to*, asserted by a person. Read by
  impact analysis and the map; never removed by anything automatic (DR-19).

Requirement comments reuse ``comments`` (0007), whose ``subject_type`` already allows
``requirement``.

Revision ID: 0008a
Revises: 0009
Create Date: 2027-01-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008a"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _created_at() -> sa.Column[object]:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )


def _fk(table: str, column: str, target: str, ondelete: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [column], [f"{target}.id"], name=op.f(f"fk_{table}_{column}_{target}"), ondelete=ondelete
    )


def upgrade() -> None:
    op.create_table(
        "votes",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("subject_type", sa.String(length=16), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("stance", sa.String(length=8), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        _created_at(),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "subject_type IN ('requirement', 'change_request')",
            name=op.f("ck_votes_subject_type_values"),
        ),
        sa.CheckConstraint("stance IN ('support', 'oppose')", name=op.f("ck_votes_stance_values")),
        _fk("votes", "project_id", "projects", "CASCADE"),
        _fk("votes", "user_id", "users", "CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_votes")),
        sa.UniqueConstraint(
            "subject_type",
            "subject_id",
            "user_id",
            name=op.f("uq_votes_subject_type_subject_id_user_id"),
        ),
    )
    op.create_index("ix_votes_project_id", "votes", ["project_id"])

    op.create_table(
        "watches",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("subject_type", sa.String(length=16), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        _created_at(),
        sa.CheckConstraint(
            "subject_type IN ('requirement', 'issue', 'change_request')",
            name=op.f("ck_watches_subject_type_values"),
        ),
        _fk("watches", "user_id", "users", "CASCADE"),
        _fk("watches", "project_id", "projects", "CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "subject_type", "subject_id", name=op.f("pk_watches")),
    )
    op.create_index("ix_watches_subject_type_subject_id", "watches", ["subject_type", "subject_id"])

    op.create_table(
        "requirement_links",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        _created_at(),
        sa.CheckConstraint("source_id <> target_id", name=op.f("ck_requirement_links_not_self")),
        sa.CheckConstraint(
            "kind IN ('depends_on', 'refines', 'related_to')",
            name=op.f("ck_requirement_links_kind_values"),
        ),
        _fk("requirement_links", "project_id", "projects", "CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["requirements.id"],
            name=op.f("fk_requirement_links_source_id_requirements"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_id"],
            ["requirements.id"],
            name=op.f("fk_requirement_links_target_id_requirements"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_requirement_links_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_requirement_links")),
        sa.UniqueConstraint(
            "source_id",
            "target_id",
            "kind",
            name=op.f("uq_requirement_links_source_id_target_id_kind"),
        ),
    )
    op.create_index("ix_requirement_links_project_id", "requirement_links", ["project_id"])
    op.create_index("ix_requirement_links_target_id", "requirement_links", ["target_id"])


def downgrade() -> None:
    op.drop_index("ix_requirement_links_target_id", table_name="requirement_links")
    op.drop_index("ix_requirement_links_project_id", table_name="requirement_links")
    op.drop_table("requirement_links")
    op.drop_index("ix_watches_subject_type_subject_id", table_name="watches")
    op.drop_table("watches")
    op.drop_index("ix_votes_project_id", table_name="votes")
    op.drop_table("votes")
