"""index documents by workspace and sha256

Supports the re-upload check in POST /documents ("has this workspace already uploaded
identical content?") without scanning every document in the workspace.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-30
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_documents_workspace_id_sha256", "documents", ["workspace_id", "sha256"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_documents_workspace_id_sha256", table_name="documents")
