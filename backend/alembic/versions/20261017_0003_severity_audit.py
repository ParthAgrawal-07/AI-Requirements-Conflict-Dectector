"""severity becomes low/medium/high; escalated audit action

Sprint 0 (rev. 5 plan, design update §4.3). Follow-up actions A1 and A2 of the Step 6 review:

* **A1** — the ``critical`` severity is retired (FR-42 uses Low, Medium, High). Existing
  ``critical`` findings become ``high``, and the CHECK constraint is narrowed.
* **A2** — ``escalated`` joins the well-known audit actions (``app.models.enums.AuditAction``).
  ``audit_log.action`` is a free-form VARCHAR(64), so no schema change is needed for it; it is
  listed here so the Sprint 0 migration history records the decision.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-17
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSTRAINT = "ck_findings_finding_severity"


def upgrade() -> None:
    # Data first: the narrower CHECK would reject existing 'critical' rows.
    op.execute("UPDATE findings SET severity = 'high' WHERE severity = 'critical'")
    op.drop_constraint(op.f(CONSTRAINT), "findings", type_="check")
    op.create_check_constraint(
        op.f(CONSTRAINT), "findings", "severity IN ('low', 'medium', 'high')"
    )


def downgrade() -> None:
    # Rows that were 'critical' stay 'high': the original value is not recoverable.
    op.drop_constraint(op.f(CONSTRAINT), "findings", type_="check")
    op.create_check_constraint(
        op.f(CONSTRAINT), "findings", "severity IN ('low', 'medium', 'high', 'critical')"
    )
