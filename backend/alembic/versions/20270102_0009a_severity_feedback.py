"""severity provenance on findings; feedback-loop threshold per project

Sprint 6 (Keval — US-08, US-15, FR-18, FR-42, NFR-22).

* ``findings.severity_source`` — who set the severity now in force: ``system`` (proposed by
  ``app.classification.severity`` or a rule check), ``person`` (chosen by whoever raised a
  concern) or ``reviewer`` (an override). ``severity_proposed`` keeps what the system proposed,
  so an override never hides it; ``severity_reason``, ``severity_set_by``, ``severity_set_at``
  record the override (also audited as ``severity_changed``).
* Backfill: AI findings stored before Sprint 6 had no severity. They get the base severity of
  their category (Conflicting, Ambiguous, Incomplete → medium; Duplicate, Dependent → low),
  marked ``system``; findings that already had one keep it.
* ``projects.feedback_alert_threshold`` — how many false-positive dismissals of one pattern
  surface it for tuning in the AI feedback report (US-15; default 5). Nothing retrains itself.

Revision ID: 0009a
Revises: 0008a
Create Date: 2027-01-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009a"
down_revision: str | None = "0008a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("findings", sa.Column("severity_source", sa.String(length=16), nullable=True))
    op.add_column("findings", sa.Column("severity_proposed", sa.String(length=8), nullable=True))
    op.add_column("findings", sa.Column("severity_reason", sa.Text(), nullable=True))
    op.add_column("findings", sa.Column("severity_set_by", sa.Uuid(), nullable=True))
    op.add_column(
        "findings", sa.Column("severity_set_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_foreign_key(
        op.f("fk_findings_severity_set_by_users"),
        "findings",
        "users",
        ["severity_set_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        op.f("ck_findings_severity_source_values"),
        "findings",
        "severity_source IS NULL OR severity_source IN ('system', 'person', 'reviewer')",
    )
    op.create_check_constraint(
        op.f("ck_findings_severity_proposed_values"),
        "findings",
        "severity_proposed IS NULL OR severity_proposed IN ('low', 'medium', 'high')",
    )
    op.execute(
        """
        UPDATE findings SET
            severity = CASE WHEN category IN ('Duplicate', 'Dependent') THEN 'low' ELSE 'medium' END,
            severity_source = 'system',
            severity_reason = 'Base severity of the category (set when severity was introduced)'
        WHERE severity IS NULL
        """
    )
    op.execute(
        """
        UPDATE findings SET severity_source = CASE WHEN source = 'person' THEN 'person'
                                                   ELSE 'system' END
        WHERE severity_source IS NULL
        """
    )
    op.execute("UPDATE findings SET severity_proposed = severity WHERE severity_source = 'system'")
    op.add_column(
        "projects",
        sa.Column(
            "feedback_alert_threshold", sa.Integer(), server_default=sa.text("5"), nullable=False
        ),
    )
    op.create_check_constraint(
        op.f("ck_projects_feedback_alert_threshold_range"),
        "projects",
        "feedback_alert_threshold BETWEEN 1 AND 100",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_projects_feedback_alert_threshold_range"), "projects", type_="check"
    )
    op.drop_column("projects", "feedback_alert_threshold")
    op.drop_constraint(op.f("ck_findings_severity_proposed_values"), "findings", type_="check")
    op.drop_constraint(op.f("ck_findings_severity_source_values"), "findings", type_="check")
    op.drop_constraint(op.f("fk_findings_severity_set_by_users"), "findings", type_="foreignkey")
    op.drop_column("findings", "severity_set_at")
    op.drop_column("findings", "severity_set_by")
    op.drop_column("findings", "severity_reason")
    op.drop_column("findings", "severity_proposed")
    op.drop_column("findings", "severity_source")
