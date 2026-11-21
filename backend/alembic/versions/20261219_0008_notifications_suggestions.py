"""notifications, AI suggestions and their append-only feedback

Sprint 5 (Madhav — US-38, US-45, FR-68, FR-69, FR-70, FR-94, NFR-36; design update §3.7, §4.1,
§11.1; ADR-24).

* ``notifications`` — one row per person and thing that needs them (review requested, assigned,
  mentioned, watching, results on their requirements, join requests, decisions, merges). The
  payload holds IDs and titles only, never requirement or message text (CR-04).
* ``suggestions`` — up to three AI options per finding (``options`` jsonb, schema-validated by
  ``app.classification.suggest``), ``pending → ready | failed | waiting_budget``, and
  ``superseded`` when regenerated. At most one live suggestion per finding.
* ``suggestion_feedback`` — every human response, **append-only**: a trigger rejects UPDATE and
  DELETE (except the cascades of a deleted finding or user). ``final_text`` is required for an
  edited acceptance, an option for a choice, an instruction for a regeneration, a 1–5 rating
  for an expert rating (the CP2 correctness study).
* ``change_requests.source_suggestion_id`` — the suggestion a pre-filled request came from.
* ``projects.use_feedback_examples`` — the example re-use experiment, **off** by default (SX-30).

Revision ID: 0008
Revises: 0010b
Create Date: 2026-12-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0010b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KINDS = (
    "'review_requested', 'assigned', 'mentioned', 'watching', 'results', 'join_request', "
    "'decision', 'merged'"
)
STATUSES = "'pending', 'waiting_budget', 'ready', 'failed', 'superseded'"
ACTIONS = (
    "'accepted', 'accepted_edited', 'rejected_meaning', 'rejected_infeasible', "
    "'rejected_missing_context', 'deferred', 'regenerate', 'prefer', 'rate_up', 'rate_down', "
    "'expert_rating'"
)
CHOICES = (
    "'accepted', 'accepted_edited', 'rejected_meaning', 'rejected_infeasible', "
    "'rejected_missing_context', 'prefer', 'rate_up', 'rate_down', 'expert_rating'"
)

APPEND_ONLY = """
CREATE OR REPLACE FUNCTION suggestion_feedback_append_only() RETURNS trigger AS $$
BEGIN
    -- Cascades (a finding or user deleted) run inside a referential-action trigger.
    IF pg_trigger_depth() > 1 THEN
        RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
    END IF;
    RAISE EXCEPTION 'suggestion_feedback is append-only (%)', TG_OP
        USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql;
"""


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
        "notifications",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("subject_type", sa.String(length=32), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(f"kind IN ({KINDS})", name=op.f("ck_notifications_kind_values")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_notifications_user_id_users"),
            ondelete="CASCADE",
        ),  # fmt: skip
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_notifications_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_notifications_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_notifications_actor_id_users"),
            ondelete="SET NULL",
        ),  # fmt: skip
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
    )
    op.create_index(
        "ix_notifications_user_id_updated_at", "notifications", ["user_id", "updated_at"]
    )
    op.create_index(
        "ix_notifications_user_id_unread",
        "notifications",
        ["user_id", "kind"],
        postgresql_where=sa.text("read_at IS NULL"),
    )

    op.create_table(
        "suggestions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("finding_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("change_request_id", sa.Uuid(), nullable=True),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column(
            "options",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("prompt_version", sa.String(length=16), nullable=True),
        sa.Column("model", sa.String(length=80), nullable=True),
        sa.Column("instruction", sa.Text(), nullable=True),
        sa.Column("requested_by", sa.Uuid(), nullable=True),
        sa.Column("error", sa.String(length=64), nullable=True),
        sa.Column("llm_calls", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("context_version", sa.Integer(), nullable=True),
        sa.Column("ready_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(f"status IN ({STATUSES})", name=op.f("ck_suggestions_status_values")),
        sa.CheckConstraint("llm_calls >= 0", name=op.f("ck_suggestions_llm_calls_non_negative")),
        sa.ForeignKeyConstraint(
            ["finding_id"],
            ["findings.id"],
            name=op.f("fk_suggestions_finding_id_findings"),
            ondelete="CASCADE",
        ),  # fmt: skip
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_suggestions_project_id_projects"),
            ondelete="CASCADE",
        ),  # fmt: skip
        sa.ForeignKeyConstraint(
            ["change_request_id"],
            ["change_requests.id"],
            name=op.f("fk_suggestions_change_request_id_change_requests"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["users.id"],
            name=op.f("fk_suggestions_requested_by_users"),
            ondelete="SET NULL",
        ),  # fmt: skip
        sa.PrimaryKeyConstraint("id", name=op.f("pk_suggestions")),
    )
    op.create_index(
        "uq_suggestions_live_finding_id",
        "suggestions",
        ["finding_id"],
        unique=True,
        postgresql_where=sa.text("status <> 'superseded'"),
    )
    op.create_index("ix_suggestions_project_id_status", "suggestions", ["project_id", "status"])

    op.create_table(
        "suggestion_feedback",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("suggestion_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("option_index", sa.Integer(), nullable=True),
        sa.Column("final_text", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("instruction", sa.Text(), nullable=True),
        sa.Column("expert_rating", sa.Integer(), nullable=True),
        sa.Column("change_request_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            f"action IN ({ACTIONS})", name=op.f("ck_suggestion_feedback_action_values")
        ),
        sa.CheckConstraint(
            f"(action IN ({CHOICES})) = (option_index IS NOT NULL)",
            name=op.f("ck_suggestion_feedback_option_for_choices"),
        ),
        sa.CheckConstraint(
            "option_index IS NULL OR option_index BETWEEN 0 AND 2",
            name=op.f("ck_suggestion_feedback_option_range"),
        ),
        sa.CheckConstraint(
            "action <> 'accepted_edited' OR coalesce(length(trim(final_text)), 0) > 0",
            name=op.f("ck_suggestion_feedback_edit_has_text"),
        ),
        sa.CheckConstraint(
            "action <> 'regenerate' OR coalesce(length(trim(instruction)), 0) > 0",
            name=op.f("ck_suggestion_feedback_regenerate_has_instruction"),
        ),
        sa.CheckConstraint(
            "(action = 'expert_rating') = (expert_rating IS NOT NULL)",
            name=op.f("ck_suggestion_feedback_rating_for_experts"),
        ),
        sa.CheckConstraint(
            "expert_rating IS NULL OR expert_rating BETWEEN 1 AND 5",
            name=op.f("ck_suggestion_feedback_rating_range"),
        ),
        sa.ForeignKeyConstraint(
            ["suggestion_id"],
            ["suggestions.id"],
            name=op.f("fk_suggestion_feedback_suggestion_id_suggestions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_suggestion_feedback_user_id_users"),
            ondelete="SET NULL",
        ),  # fmt: skip
        sa.ForeignKeyConstraint(
            ["change_request_id"],
            ["change_requests.id"],
            name=op.f("fk_suggestion_feedback_change_request_id_change_requests"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_suggestion_feedback")),
    )
    op.create_index(
        "ix_suggestion_feedback_suggestion_id_created_at",
        "suggestion_feedback",
        ["suggestion_id", "created_at"],
    )
    op.execute(APPEND_ONLY)
    op.execute(
        "CREATE TRIGGER suggestion_feedback_append_only BEFORE UPDATE OR DELETE ON "
        "suggestion_feedback FOR EACH ROW EXECUTE FUNCTION suggestion_feedback_append_only()"
    )

    op.add_column("change_requests", sa.Column("source_suggestion_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_change_requests_source_suggestion_id_suggestions"),
        "change_requests",
        "suggestions",
        ["source_suggestion_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "projects",
        sa.Column(
            "use_feedback_examples", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_column("projects", "use_feedback_examples")
    op.drop_constraint(
        op.f("fk_change_requests_source_suggestion_id_suggestions"),
        "change_requests",
        type_="foreignkey",
    )
    op.drop_column("change_requests", "source_suggestion_id")
    op.execute("DROP TRIGGER IF EXISTS suggestion_feedback_append_only ON suggestion_feedback")
    op.execute("DROP FUNCTION IF EXISTS suggestion_feedback_append_only()")
    op.drop_index(
        "ix_suggestion_feedback_suggestion_id_created_at", table_name="suggestion_feedback"
    )
    op.drop_table("suggestion_feedback")
    op.drop_index("ix_suggestions_project_id_status", table_name="suggestions")
    op.drop_index("uq_suggestions_live_finding_id", table_name="suggestions")
    op.drop_table("suggestions")
    op.drop_index("ix_notifications_user_id_unread", table_name="notifications")
    op.drop_index("ix_notifications_user_id_updated_at", table_name="notifications")
    op.drop_table("notifications")
