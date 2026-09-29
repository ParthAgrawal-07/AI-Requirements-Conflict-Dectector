"""initial schema — 10 tables, HNSW vector index, append-only audit log

Revision ID: 0001
Revises:
Create Date: 2026-09-28 18:51:33.633339+00:00
"""

from collections.abc import Sequence

import pgvector.sqlalchemy  # noqa: F401
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


AUDIT_GUARD_FUNCTION = """
CREATE FUNCTION audit_log_reject_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only: % is not permitted', TG_OP
        USING ERRCODE = 'integrity_constraint_violation';
END;
$$
"""


def upgrade() -> None:
    # pgvector must exist before the embeddings table. Managed Postgres (Railway/Render/RDS)
    # allows this for the database owner; on locked-down servers an admin must run it once.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "workspaces",
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column(
            "similarity_threshold", sa.Float(), server_default=sa.text("0.75"), nullable=False
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "similarity_threshold BETWEEN 0 AND 1",
            name=op.f("ck_workspaces_similarity_threshold_range"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workspaces")),
        sa.UniqueConstraint("name", name=op.f("uq_workspaces_name")),
    )
    op.create_table(
        "users",
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column(
            "role",
            sa.Enum(
                "analyst",
                "admin",
                "compliance_reviewer",
                "read_only",
                "service",
                name="user_role",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('analyst', 'admin', 'compliance_reviewer', 'read_only', 'service')",
            name=op.f("ck_users_user_role"),
        ),
        sa.CheckConstraint("email = lower(email)", name=op.f("ck_users_email_lowercase")),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_users_workspace_id_workspaces"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_index(op.f("ix_users_workspace_id"), "users", ["workspace_id"], unique=False)
    op.create_table(
        "documents",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("uploaded_by", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column(
            "format",
            sa.Enum(
                "pdf",
                "docx",
                "txt",
                "reqif",
                name="document_format",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_path", sa.String(length=1024), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "queued",
                "processing",
                "done",
                "failed",
                name="document_status",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            server_default="queued",
            nullable=False,
        ),
        sa.Column("progress_percent", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("task_id", sa.String(length=64), nullable=True),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "format IN ('pdf', 'docx', 'txt', 'reqif')", name=op.f("ck_documents_document_format")
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'processing', 'done', 'failed')",
            name=op.f("ck_documents_document_status"),
        ),
        sa.CheckConstraint(
            "progress_percent BETWEEN 0 AND 100", name=op.f("ck_documents_progress_range")
        ),
        sa.CheckConstraint("size_bytes >= 0", name=op.f("ck_documents_size_non_negative")),
        sa.ForeignKeyConstraint(
            ["uploaded_by"],
            ["users.id"],
            name=op.f("fk_documents_uploaded_by_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_documents_workspace_id_workspaces"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_documents")),
    )
    op.create_index("ix_documents_status", "documents", ["status"], unique=False)
    op.create_index(
        "ix_documents_workspace_id_uploaded_at",
        "documents",
        ["workspace_id", "uploaded_at"],
        unique=False,
    )
    op.create_table(
        "requirements",
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("source_req_id", sa.String(length=64), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("location", sa.String(length=64), nullable=True),
        sa.Column("order_index", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("stakeholder_group", sa.String(length=120), nullable=True),
        sa.Column("is_protected", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("current_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("current_version >= 1", name=op.f("ck_requirements_version_positive")),
        sa.CheckConstraint("order_index >= 0", name=op.f("ck_requirements_order_non_negative")),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_requirements_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_requirements")),
    )
    op.create_index(
        "ix_requirements_document_id_order_index",
        "requirements",
        ["document_id", "order_index"],
        unique=False,
    )
    op.create_table(
        "candidate_pairs",
        sa.Column("requirement_a_id", sa.Uuid(), nullable=False),
        sa.Column("requirement_b_id", sa.Uuid(), nullable=False),
        sa.Column("similarity_score", sa.Float(), nullable=False),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "requirement_a_id < requirement_b_id", name=op.f("ck_candidate_pairs_canonical_order")
        ),
        sa.CheckConstraint(
            "similarity_score BETWEEN -1 AND 1", name=op.f("ck_candidate_pairs_similarity_range")
        ),
        sa.ForeignKeyConstraint(
            ["requirement_a_id"],
            ["requirements.id"],
            name=op.f("fk_candidate_pairs_requirement_a_id_requirements"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requirement_b_id"],
            ["requirements.id"],
            name=op.f("fk_candidate_pairs_requirement_b_id_requirements"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_candidate_pairs")),
        sa.UniqueConstraint(
            "requirement_a_id",
            "requirement_b_id",
            name=op.f("uq_candidate_pairs_requirement_a_id_requirement_b_id"),
        ),
    )
    op.create_index(
        "ix_candidate_pairs_requirement_b_id", "candidate_pairs", ["requirement_b_id"], unique=False
    )
    op.create_table(
        "embeddings",
        sa.Column("requirement_id", sa.Uuid(), nullable=False),
        sa.Column("vector", pgvector.sqlalchemy.vector.VECTOR(dim=384), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["requirement_id"],
            ["requirements.id"],
            name=op.f("fk_embeddings_requirement_id_requirements"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_embeddings")),
        sa.UniqueConstraint("requirement_id", name=op.f("uq_embeddings_requirement_id")),
    )
    op.create_index(
        "ix_embeddings_vector_hnsw",
        "embeddings",
        ["vector"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"vector": "vector_cosine_ops"},
    )
    op.create_table(
        "requirement_versions",
        sa.Column("requirement_id", sa.Uuid(), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("body_snapshot", sa.Text(), nullable=False),
        sa.Column("changed_by", sa.Uuid(), nullable=True),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "version_no >= 1", name=op.f("ck_requirement_versions_version_positive")
        ),
        sa.ForeignKeyConstraint(
            ["changed_by"],
            ["users.id"],
            name=op.f("fk_requirement_versions_changed_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["requirement_id"],
            ["requirements.id"],
            name=op.f("fk_requirement_versions_requirement_id_requirements"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_requirement_versions")),
        sa.UniqueConstraint(
            "requirement_id",
            "version_no",
            name=op.f("uq_requirement_versions_requirement_id_version_no"),
        ),
    )
    op.create_table(
        "findings",
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_pair_id", sa.Uuid(), nullable=True),
        sa.Column("requirement_id", sa.Uuid(), nullable=True),
        sa.Column(
            "category",
            sa.Enum(
                "Conflicting",
                "Duplicate",
                "Ambiguous",
                "Incomplete",
                "Dependent",
                name="finding_category",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "flagged",
                "confirmed",
                "dismissed",
                "merged",
                "reclassified",
                name="finding_status",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            server_default="flagged",
            nullable=False,
        ),
        sa.Column(
            "severity",
            sa.Enum(
                "low",
                "medium",
                "high",
                "critical",
                name="finding_severity",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            nullable=True,
        ),
        sa.Column("original_ai_output", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("reviewed_by", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "category IN ('Conflicting', 'Duplicate', 'Ambiguous', 'Incomplete', 'Dependent')",
            name=op.f("ck_findings_finding_category"),
        ),
        sa.CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name=op.f("ck_findings_finding_severity"),
        ),
        sa.CheckConstraint(
            "status IN ('flagged', 'confirmed', 'dismissed', 'merged', 'reclassified')",
            name=op.f("ck_findings_finding_status"),
        ),
        sa.CheckConstraint("confidence BETWEEN 0 AND 1", name=op.f("ck_findings_confidence_range")),
        sa.CheckConstraint(
            "num_nonnulls(candidate_pair_id, requirement_id) = 1", name=op.f("ck_findings_subject")
        ),
        sa.ForeignKeyConstraint(
            ["candidate_pair_id"],
            ["candidate_pairs.id"],
            name=op.f("fk_findings_candidate_pair_id_candidate_pairs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_findings_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requirement_id"],
            ["requirements.id"],
            name=op.f("fk_findings_requirement_id_requirements"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"],
            ["users.id"],
            name=op.f("fk_findings_reviewed_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_findings")),
    )
    op.create_index(
        "ix_findings_document_id_category", "findings", ["document_id", "category"], unique=False
    )
    op.create_index(
        "ix_findings_document_id_status", "findings", ["document_id", "status"], unique=False
    )
    op.create_index(
        op.f("ix_findings_requirement_id"), "findings", ["requirement_id"], unique=False
    )
    op.create_table(
        "audit_log",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("finding_id", sa.Uuid(), nullable=True),
        sa.Column("requirement_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_audit_log_actor_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["finding_id"],
            ["findings.id"],
            name=op.f("fk_audit_log_finding_id_findings"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["requirement_id"],
            ["requirements.id"],
            name=op.f("fk_audit_log_requirement_id_requirements"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_audit_log_workspace_id_workspaces"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
    )
    op.create_index("ix_audit_log_actor_id", "audit_log", ["actor_id"], unique=False)
    op.create_index("ix_audit_log_finding_id", "audit_log", ["finding_id"], unique=False)
    op.create_index("ix_audit_log_requirement_id", "audit_log", ["requirement_id"], unique=False)
    op.create_index(
        "ix_audit_log_workspace_id_at", "audit_log", ["workspace_id", "at"], unique=False
    )
    op.create_table(
        "clarifications",
        sa.Column("finding_id", sa.Uuid(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("resolved_by", sa.Uuid(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["finding_id"],
            ["findings.id"],
            name=op.f("fk_clarifications_finding_id_findings"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["resolved_by"],
            ["users.id"],
            name=op.f("fk_clarifications_resolved_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_clarifications")),
        sa.UniqueConstraint("finding_id", name=op.f("uq_clarifications_finding_id")),
    )

    # Append-only audit trail (FR-36, NFR-13): the database itself refuses UPDATE/DELETE/TRUNCATE.
    op.execute(AUDIT_GUARD_FUNCTION)
    op.execute(
        "CREATE TRIGGER audit_log_no_update_delete BEFORE UPDATE OR DELETE ON audit_log "
        "FOR EACH ROW EXECUTE FUNCTION audit_log_reject_mutation()"
    )
    op.execute(
        "CREATE TRIGGER audit_log_no_truncate BEFORE TRUNCATE ON audit_log "
        "FOR EACH STATEMENT EXECUTE FUNCTION audit_log_reject_mutation()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_truncate ON audit_log")
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_update_delete ON audit_log")
    op.execute("DROP FUNCTION IF EXISTS audit_log_reject_mutation()")
    op.drop_table("clarifications")
    op.drop_index("ix_audit_log_workspace_id_at", table_name="audit_log")
    op.drop_index("ix_audit_log_requirement_id", table_name="audit_log")
    op.drop_index("ix_audit_log_finding_id", table_name="audit_log")
    op.drop_index("ix_audit_log_actor_id", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_index(op.f("ix_findings_requirement_id"), table_name="findings")
    op.drop_index("ix_findings_document_id_status", table_name="findings")
    op.drop_index("ix_findings_document_id_category", table_name="findings")
    op.drop_table("findings")
    op.drop_table("requirement_versions")
    op.drop_index(
        "ix_embeddings_vector_hnsw",
        table_name="embeddings",
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"vector": "vector_cosine_ops"},
    )
    op.drop_table("embeddings")
    op.drop_index("ix_candidate_pairs_requirement_b_id", table_name="candidate_pairs")
    op.drop_table("candidate_pairs")
    op.drop_index("ix_requirements_document_id_order_index", table_name="requirements")
    op.drop_table("requirements")
    op.drop_index("ix_documents_workspace_id_uploaded_at", table_name="documents")
    op.drop_index("ix_documents_status", table_name="documents")
    op.drop_table("documents")
    op.drop_index(op.f("ix_users_workspace_id"), table_name="users")
    op.drop_table("users")
    op.drop_table("workspaces")
    # The vector extension is intentionally left installed: dropping it would also destroy
    # any other schema's vector columns, and needs privileges managed hosts may not grant.
