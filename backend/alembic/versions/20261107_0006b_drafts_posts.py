"""lifecycle and runs part 2: requirement drafts and requirement posts

Sprint 2 (Bansil; design update §4.1, §4.3 ``0006_lifecycle_runs``; composer contract in
``docs/contracts/composer-and-context.md``).

* ``requirement_drafts`` — the composer's private autosave (FR-81).
* ``requirements`` — a requirement can now be *posted* in a channel instead of extracted:
  ``document_id`` becomes nullable (but stays required for ``origin = 'document'``),
  ``origin_message_id`` links the requirement to the message that created it (at most one
  requirement per message), and ``req_type``, ``priority`` and ``composer_fields`` keep the
  composer's input (FR-55).

Downgrade deletes posted requirements (they have no document) before restoring NOT NULL.

Revision ID: 0006b
Revises: 0006
Create Date: 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006b"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "requirement_drafts",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("fields", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["users.id"],
            name=op.f("fk_requirement_drafts_author_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_requirement_drafts_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_requirement_drafts")),
    )
    op.create_index(
        "ix_requirement_drafts_author_id_project_id",
        "requirement_drafts",
        ["author_id", "project_id"],
    )

    op.alter_column("requirements", "document_id", existing_type=sa.Uuid(), nullable=True)
    op.add_column("requirements", sa.Column("origin_message_id", sa.Uuid(), nullable=True))
    op.add_column("requirements", sa.Column("req_type", sa.String(length=32), nullable=True))
    op.add_column("requirements", sa.Column("priority", sa.String(length=32), nullable=True))
    op.add_column(
        "requirements",
        sa.Column("composer_fields", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_requirements_origin_message_id_messages"),
        "requirements",
        "messages",
        ["origin_message_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "uq_requirements_origin_message_id",
        "requirements",
        ["origin_message_id"],
        unique=True,
        postgresql_where=sa.text("origin_message_id IS NOT NULL"),
    )
    op.create_check_constraint(
        op.f("ck_requirements_req_type_values"),
        "requirements",
        "req_type IS NULL OR req_type IN ('functional', 'non_functional', 'constraint')",
    )
    op.create_check_constraint(
        op.f("ck_requirements_priority_values"),
        "requirements",
        "priority IS NULL OR priority IN ('must', 'should', 'could', 'wont')",
    )
    op.create_check_constraint(
        op.f("ck_requirements_document_origin_has_document"),
        "requirements",
        "document_id IS NOT NULL OR origin <> 'document'",
    )


def downgrade() -> None:
    for name in (
        "document_origin_has_document",
        "priority_values",
        "req_type_values",
    ):
        op.drop_constraint(op.f(f"ck_requirements_{name}"), "requirements", type_="check")
    op.drop_index("uq_requirements_origin_message_id", table_name="requirements")
    op.drop_constraint(
        op.f("fk_requirements_origin_message_id_messages"), "requirements", type_="foreignkey"
    )
    for column in ("composer_fields", "priority", "req_type", "origin_message_id"):
        op.drop_column("requirements", column)
    op.execute("DELETE FROM requirements WHERE document_id IS NULL")
    op.alter_column("requirements", "document_id", existing_type=sa.Uuid(), nullable=False)

    op.drop_index("ix_requirement_drafts_author_id_project_id", table_name="requirement_drafts")
    op.drop_table("requirement_drafts")
