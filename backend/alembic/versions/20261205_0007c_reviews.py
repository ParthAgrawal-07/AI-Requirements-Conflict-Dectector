"""issues and change requests part 4: review requests, reviews, inline comments, version links

Sprint 4 (Parth — US-35, US-12, FR-65, FR-66, FR-98, SX-13, CR-19; design update §3.2, §11.3).

* ``review_requests`` — who was asked to review a change request and why (``owner``,
  ``direct_conflict``, ``merge_quota``, ``compliance``, ``transitive``), required or optional.
* ``reviews`` — ``approve``, ``request_changes`` or ``comment``, bound to the
  ``proposal_revision`` and base version it was given on: a review of an older revision counts
  as dismissed (FR-98). A trigger refuses an approving review by the change request's proposer,
  whatever path writes it (SX-13: no self-approval).
* ``review_comments`` — inline comments on a part of the proposal (``field``, offsets).
* ``requirement_versions.change_request_id`` — the change request a version was merged from
  (version history, US-12).

Revision ID: 0007c
Revises: 0007b
Create Date: 2026-12-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007c"
down_revision: str | None = "0007b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NO_SELF_APPROVAL = """
CREATE FUNCTION reviews_no_self_approval() RETURNS trigger AS $$
BEGIN
    IF NEW.decision = 'approve' AND EXISTS (
        SELECT 1 FROM change_requests
        WHERE id = NEW.change_request_id AND proposer_id = NEW.reviewer_id
    ) THEN
        RAISE EXCEPTION 'the proposer of a change request cannot approve it'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER reviews_no_self_approval
    BEFORE INSERT OR UPDATE ON reviews
    FOR EACH ROW EXECUTE FUNCTION reviews_no_self_approval();
"""


def upgrade() -> None:
    op.create_table(
        "review_requests",
        sa.Column("change_request_id", sa.Uuid(), nullable=False),
        sa.Column("reviewer_id", sa.Uuid(), nullable=False),
        sa.Column("required", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("reason", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "reason IN ('owner', 'direct_conflict', 'merge_quota', 'compliance', 'transitive', "
            "'requested')",
            name=op.f("ck_review_requests_reason_values"),
        ),
        sa.ForeignKeyConstraint(
            ["change_request_id"],
            ["change_requests.id"],
            name=op.f("fk_review_requests_change_request_id_change_requests"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_id"],
            ["users.id"],
            name=op.f("fk_review_requests_reviewer_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "change_request_id", "reviewer_id", name=op.f("pk_review_requests")
        ),
    )
    op.create_index("ix_review_requests_reviewer_id", "review_requests", ["reviewer_id"])

    op.create_table(
        "reviews",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("change_request_id", sa.Uuid(), nullable=False),
        sa.Column("reviewer_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("proposal_revision", sa.Integer(), nullable=False),
        sa.Column("reviewed_base_version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "decision IN ('approve', 'request_changes', 'comment')",
            name=op.f("ck_reviews_decision_values"),
        ),
        sa.CheckConstraint(
            "decision <> 'request_changes' OR rationale IS NOT NULL",
            name=op.f("ck_reviews_request_changes_has_rationale"),
        ),
        sa.ForeignKeyConstraint(
            ["change_request_id"],
            ["change_requests.id"],
            name=op.f("fk_reviews_change_request_id_change_requests"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_id"],
            ["users.id"],
            name=op.f("fk_reviews_reviewer_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reviews")),
    )
    op.create_index(
        "ix_reviews_change_request_id_created_at", "reviews", ["change_request_id", "created_at"]
    )
    op.execute(NO_SELF_APPROVAL)

    op.create_table(
        "review_comments",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("review_id", sa.Uuid(), nullable=False),
        sa.Column("field", sa.String(length=32), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=True),
        sa.Column("end_offset", sa.Integer(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "start_offset IS NULL OR (start_offset >= 0 AND end_offset >= start_offset)",
            name=op.f("ck_review_comments_offsets_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["review_id"],
            ["reviews.id"],
            name=op.f("fk_review_comments_review_id_reviews"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_review_comments")),
    )
    op.create_index("ix_review_comments_review_id", "review_comments", ["review_id"])

    op.add_column("requirement_versions", sa.Column("change_request_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_requirement_versions_change_request_id_change_requests"),
        "requirement_versions",
        "change_requests",
        ["change_request_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_requirement_versions_change_request_id_change_requests"),
        "requirement_versions",
        type_="foreignkey",
    )
    op.drop_column("requirement_versions", "change_request_id")
    op.drop_index("ix_review_comments_review_id", table_name="review_comments")
    op.drop_table("review_comments")
    op.execute("DROP TRIGGER reviews_no_self_approval ON reviews")
    op.execute("DROP FUNCTION reviews_no_self_approval()")
    op.drop_index("ix_reviews_change_request_id_created_at", table_name="reviews")
    op.drop_table("reviews")
    op.drop_index("ix_review_requests_reviewer_id", table_name="review_requests")
    op.drop_table("review_requests")
