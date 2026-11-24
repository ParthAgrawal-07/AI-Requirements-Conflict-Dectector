"""updated SRS documents and their sections

Sprint 6 (Bansil — US-61, US-41, FR-106, FR-107, NFR-38, DR-25; design update §12.1, ADR-29).

* ``srs_documents`` — a draft or published updated SRS: the baseline it is built from, the
  requirements frozen from it, the readiness checklist as it stood, an override reason and the
  open-items report attached to an override, the fidelity report, and the published version
  label (v1.0, v1.1…, unique per project among published versions).
* ``srs_sections`` — one row per section of the ISO/IEC/IEEE 29148 outline, with its kind,
  Markdown body, source (llm, template, system, edited) and review status. Requirement sections
  are system text: a CHECK keeps them ``source = 'system'``.
* Published documents and their sections are **immutable**: triggers refuse UPDATE and DELETE
  (a deleted project still cascades).

``suggestions.context_version`` (also listed for this migration in the design) already came with
0008.

Revision ID: 0012a
Revises: 0010d
Create Date: 2027-01-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012a"
down_revision: str | None = "0010d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

IMMUTABLE = """
CREATE OR REPLACE FUNCTION srs_published_immutable() RETURNS trigger AS $$
DECLARE
    published boolean;
BEGIN
    IF pg_trigger_depth() > 1 THEN  -- the cascade of a deleted project
        RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
    END IF;
    IF TG_TABLE_NAME = 'srs_documents' THEN
        published := OLD.status = 'published';
    ELSE
        SELECT d.status = 'published' INTO published FROM srs_documents d WHERE d.id = OLD.srs_id;
    END IF;
    IF published THEN
        RAISE EXCEPTION 'a published SRS is immutable (%)', TG_OP
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$ LANGUAGE plpgsql;
"""


def _jsonb(name: str, default: str | None) -> sa.Column[object]:
    return sa.Column(
        name,
        postgresql.JSONB(astext_type=sa.Text()),
        server_default=sa.text(f"'{default}'::jsonb") if default else None,
        nullable=default is None,
    )


def _timestamps() -> list[sa.Column[object]]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def _user_fk(table: str, column: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [column], ["users.id"], name=op.f(f"fk_{table}_{column}_users"), ondelete="SET NULL"
    )


def upgrade() -> None:
    op.create_table(
        "srs_documents",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("baseline_id", sa.Uuid(), nullable=True),
        sa.Column("baseline_revision", sa.Integer(), nullable=False),
        sa.Column("version_label", sa.String(length=16), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("context_version", sa.Integer(), nullable=True),
        _jsonb("requirements", "[]"),
        _jsonb("readiness", "[]"),
        sa.Column("override_reason", sa.Text(), nullable=True),
        _jsonb("open_items", None),
        _jsonb("fidelity_report", None),
        sa.Column("llm_calls", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("published_by", sa.Uuid(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "status IN ('generating', 'draft', 'published', 'discarded')",
            name=op.f("ck_srs_documents_status_values"),
        ),
        sa.CheckConstraint(
            "status <> 'published' OR (published_at IS NOT NULL AND version_label IS NOT NULL)",
            name=op.f("ck_srs_documents_published_has_version"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_srs_documents_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["baseline_id"],
            ["baselines.id"],
            name=op.f("fk_srs_documents_baseline_id_baselines"),
            ondelete="SET NULL",
        ),
        _user_fk("srs_documents", "created_by"),
        _user_fk("srs_documents", "published_by"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_srs_documents")),
    )
    op.create_index(
        "uq_srs_documents_project_id_version_label",
        "srs_documents",
        ["project_id", "version_label"],
        unique=True,
        postgresql_where=sa.text("status = 'published'"),
    )
    op.create_index(
        "ix_srs_documents_project_id_created_at", "srs_documents", ["project_id", "created_at"]
    )

    op.create_table(
        "srs_sections",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("srs_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=48), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("body", sa.Text(), server_default="", nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("regenerations", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("instruction", sa.Text(), nullable=True),
        sa.Column("llm_calls", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("llm_model", sa.String(length=80), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("accepted_by", sa.Uuid(), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "kind IN ('narrative', 'requirements', 'appendix')",
            name=op.f("ck_srs_sections_kind_values"),
        ),
        sa.CheckConstraint(
            "source IN ('llm', 'template', 'system', 'edited')",
            name=op.f("ck_srs_sections_source_values"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'generating', 'accepted')",
            name=op.f("ck_srs_sections_status_values"),
        ),
        sa.CheckConstraint(
            "kind <> 'requirements' OR source = 'system'",
            name=op.f("ck_srs_sections_requirements_system"),
        ),
        sa.ForeignKeyConstraint(
            ["srs_id"],
            ["srs_documents.id"],
            name=op.f("fk_srs_sections_srs_id_srs_documents"),
            ondelete="CASCADE",
        ),
        _user_fk("srs_sections", "accepted_by"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_srs_sections")),
        sa.UniqueConstraint("srs_id", "key", name=op.f("uq_srs_sections_srs_id_key")),
    )

    op.execute(IMMUTABLE)
    for table in ("srs_documents", "srs_sections"):
        op.execute(
            f"CREATE TRIGGER {table}_published_immutable BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION srs_published_immutable()"
        )


def downgrade() -> None:
    for table in ("srs_sections", "srs_documents"):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_published_immutable ON {table}")
    op.execute("DROP FUNCTION IF EXISTS srs_published_immutable()")
    op.drop_table("srs_sections")
    op.drop_index("ix_srs_documents_project_id_created_at", table_name="srs_documents")
    op.drop_index("uq_srs_documents_project_id_version_label", table_name="srs_documents")
    op.drop_table("srs_documents")
