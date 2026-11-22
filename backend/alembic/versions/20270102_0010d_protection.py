"""who protected a requirement, when and why

Sprint 6 (Parth — US-18, FR-21, FR-36, NFR-13, DR-05, DR-12).

* ``requirements.protected_by``, ``protected_at``, ``protection_reason`` — the current protection
  decision, shown on the requirement and in the compliance queue. Every change is also audited
  (``protection_changed``) in the immutable audit log, which is the record of history.
* Requirements already protected keep their flag; their protection is attributed to nobody
  (it predates this column).

The compliance guard itself (merge needs a compliance approval; only compliance reviewers act on
findings about protected requirements; approval needs a sign-off on the current version) came
with US-10, US-35 and US-37. The "Protected requirements" decision rule is seeded per project
since Sprint 5 (US-57).

Revision ID: 0010d
Revises: 0009a
Create Date: 2027-01-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010d"
down_revision: str | None = "0009a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("requirements", sa.Column("protected_by", sa.Uuid(), nullable=True))
    op.add_column(
        "requirements", sa.Column("protected_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("requirements", sa.Column("protection_reason", sa.Text(), nullable=True))
    op.create_foreign_key(
        op.f("fk_requirements_protected_by_users"),
        "requirements",
        "users",
        ["protected_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_requirements_project_id_protected",
        "requirements",
        ["project_id"],
        postgresql_where=sa.text("is_protected"),
    )


def downgrade() -> None:
    op.drop_index("ix_requirements_project_id_protected", table_name="requirements")
    op.drop_constraint(
        op.f("fk_requirements_protected_by_users"), "requirements", type_="foreignkey"
    )
    op.drop_column("requirements", "protection_reason")
    op.drop_column("requirements", "protected_at")
    op.drop_column("requirements", "protected_by")
