"""PR review fixes: workspace names are no longer unique; Owner role wording

A separate migration on purpose (not an edit of ``0004``): if ``0004`` has already been applied
anywhere — a preview or the Render database — editing it would never run there. This one applies
cleanly on top of ``0004`` whether or not that has happened.

* ``workspaces.name`` loses its UNIQUE constraint. A platform-wide unique display name let one
  tenant learn that another tenant's workspace exists (a 409 on create/rename), and a
  check-then-write rename could race into a 500. Workspaces are identified by id; project names
  stay unique *within* a workspace.
* The Owner role's description said "everything", but the Owner never holds
  ``protected.signoff`` (spec §1.22). Wording only.

Downgrade renames duplicate workspace names (``"Name (1a2b3c4d)"``) so the constraint can return.

Revision ID: 0004a
Revises: 0004
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004a"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_OWNER_DESCRIPTION = "Runs the workspace: everything, including settings and ownership transfer."
NEW_OWNER_DESCRIPTION = (
    "Runs the workspace: every permission except the compliance sign-off, including "
    "settings and ownership transfer."
)


def _set_owner_description(text: str) -> None:
    op.get_bind().execute(
        sa.text("UPDATE roles SET description = :d WHERE is_default AND name = 'Owner'"),
        {"d": text},
    )


def upgrade() -> None:
    op.drop_constraint(op.f("uq_workspaces_name"), "workspaces", type_="unique")
    _set_owner_description(NEW_OWNER_DESCRIPTION)


def downgrade() -> None:
    # Keep the oldest workspace of each name as is; suffix the others so UNIQUE can be restored.
    op.execute(
        """
        UPDATE workspaces w
        SET name = left(w.name, 100) || ' (' || left(w.id::text, 8) || ')'
        FROM (
            SELECT id, row_number() OVER (PARTITION BY name ORDER BY created_at, id) AS rn
            FROM workspaces
        ) AS ranked
        WHERE ranked.id = w.id AND ranked.rn > 1
        """
    )
    op.create_unique_constraint(op.f("uq_workspaces_name"), "workspaces", ["name"])
    _set_owner_description(OLD_OWNER_DESCRIPTION)
