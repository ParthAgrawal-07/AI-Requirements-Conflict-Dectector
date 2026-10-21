"""project context: project_contexts, document_sections, extraction review flags

Sprint 1, US-60 and US-02 (Bansil; design update §12.1, ADR-28).

* ``project_contexts`` — the versioned project brief (FR-103 to FR-105). ``projects.status`` and
  ``projects.context_version`` already exist (created early in ``0004`` so the ContextGate could
  ship with the project table).
* ``document_sections`` — each heading of an uploaded document and the verbatim text under it,
  for the brief drafter and the context pack. ``embedding`` stays NULL until the embedding stage
  fills it (Heet).
* ``findings.context_version`` — which context the classifier was given (FR-105).
* ``requirements.section_heading``, ``needs_review``, ``review_reasons`` — the segmenter's review
  flags, so uncertain extractions are surfaced instead of lost (US-02).

No context is backfilled. Projects that ``0004`` created as ``active`` keep
``context_version = 0``; their manager can draft a brief from an existing document with
``POST /projects/{p}/context/draft``. Drafting needs the LLM, which a migration must not call.

Numbered ``0011`` as in the design-update plan, and placed directly after ``0004a`` because it is
a Sprint 1 migration: whichever of ``0005`` (join codes) and this one merges second re-points its
``down_revision`` (``test_there_is_exactly_one_migration_head`` catches it).

Revision ID: 0011
Revises: 0004a
Create Date: 2026-10-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str | None = "0004a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBEDDING_DIM = 384  # frozen copy of app.models.embedding.EMBEDDING_DIM


def upgrade() -> None:
    op.create_table(
        "project_contexts",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=True),
        sa.Column("scope_in", sa.Text(), nullable=True),
        sa.Column("scope_out", sa.Text(), nullable=True),
        sa.Column("actors", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("environment", sa.Text(), nullable=True),
        sa.Column("glossary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("constraints", sa.Text(), nullable=True),
        sa.Column("quality_goals", sa.Text(), nullable=True),
        sa.Column("regulations", sa.Text(), nullable=True),
        sa.Column("references", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source_document_id", sa.Uuid(), nullable=True),
        sa.Column(
            "field_status",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_project_contexts_version_positive")),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_project_contexts_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_document_id"],
            ["documents.id"],
            name=op.f("fk_project_contexts_source_document_id_documents"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_project_contexts_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_contexts")),
        sa.UniqueConstraint(
            "project_id", "version", name=op.f("uq_project_contexts_project_id_version")
        ),
    )

    op.create_table(
        "document_sections",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("heading", sa.Text(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=True),
        sa.CheckConstraint(
            "order_index >= 0", name=op.f("ck_document_sections_order_non_negative")
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_document_sections_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_document_sections_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_sections")),
    )
    op.create_index(
        "ix_document_sections_document_id_order_index",
        "document_sections",
        ["document_id", "order_index"],
    )
    op.create_index("ix_document_sections_project_id", "document_sections", ["project_id"])

    op.add_column("findings", sa.Column("context_version", sa.Integer(), nullable=True))

    op.add_column("requirements", sa.Column("section_heading", sa.Text(), nullable=True))
    op.add_column(
        "requirements",
        sa.Column("needs_review", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "requirements",
        sa.Column(
            "review_reasons",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("requirements", "review_reasons")
    op.drop_column("requirements", "needs_review")
    op.drop_column("requirements", "section_heading")
    op.drop_column("findings", "context_version")
    op.drop_index("ix_document_sections_project_id", table_name="document_sections")
    op.drop_index("ix_document_sections_document_id_order_index", table_name="document_sections")
    op.drop_table("document_sections")
    op.drop_table("project_contexts")
