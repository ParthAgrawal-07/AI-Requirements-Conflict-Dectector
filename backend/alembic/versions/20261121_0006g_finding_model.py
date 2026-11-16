"""lifecycle and runs part 7: which model produced a finding

Sprint 3 (Keval — US-05, US-31; ADR-31 "record the provider and model on every stored AI
result").

``findings.llm_model`` — ``"<provider>/<model>"`` that answered, e.g. ``gemini/gemini-2.5-flash``
or ``groq/llama-3.3-70b-versatile`` after a fall-over. NULL for findings stored before Sprint 3.

Revision ID: 0006g
Revises: 0006f
Create Date: 2026-11-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006g"
down_revision: str | None = "0006c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("findings", sa.Column("llm_model", sa.String(length=80), nullable=True))


def downgrade() -> None:
    op.drop_column("findings", "llm_model")
