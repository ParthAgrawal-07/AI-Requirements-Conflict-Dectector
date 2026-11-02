"""collaboration part 1: join_codes, join_requests

Sprint 1, US-25 (Madhav; design update §7.3, §12.1). Only the join tables: ``channels``,
``channel_members`` and ``messages`` are added to this revision family in Sprint 2 as a new file
(a merged migration is never edited).

* ``join_codes`` — a keyed hash of each code (never the code), its last four characters as a
  hint, the role it grants, optional project scope, expiry, use limit and approval flag.
* ``join_requests`` — made by approval-gated codes; at most one *pending* request per user and
  workspace (partial unique index).

There is deliberately no CHECK on the role: "never Owner or Admin" is a rule about permissions,
enforced by ``app.services.membership`` so that custom roles are covered too (ADR-20).

Numbered ``0005`` as in the design-update plan but placed after ``0011``, which merged first
(see the note in ``0011``).

Revision ID: 0005
Revises: 0011
Create Date: 2026-10-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Frozen copies of the enums: a migration must not change when the application code does.
JOIN_CODE_STATUSES = ("active", "revoked", "expired", "exhausted")
JOIN_REQUEST_STATUSES = ("pending", "approved", "denied", "expired")


def _in_list(column: str, values: Sequence[str]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _status_column(values: Sequence[str], name: str, default: str) -> sa.Column:
    return sa.Column(
        "status",
        sa.Enum(*values, name=name, native_enum=False, create_constraint=False, length=32),
        server_default=default,
        nullable=False,
    )


def _timestamps() -> list[sa.Column]:
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
        "join_codes",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("code_hint", sa.String(length=4), nullable=False),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("max_uses", sa.Integer(), nullable=True),
        sa.Column("uses", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "requires_approval", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        _status_column(JOIN_CODE_STATUSES, "join_code_status", "active"),
        sa.Column("revoked_by", sa.Uuid(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            _in_list("status", JOIN_CODE_STATUSES), name=op.f("ck_join_codes_join_code_status")
        ),
        sa.CheckConstraint("uses >= 0", name=op.f("ck_join_codes_uses_non_negative")),
        sa.CheckConstraint(
            "max_uses IS NULL OR max_uses > 0", name=op.f("ck_join_codes_max_uses_positive")
        ),
        sa.CheckConstraint(
            "max_uses IS NULL OR uses <= max_uses", name=op.f("ck_join_codes_uses_within_max")
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_join_codes_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_join_codes_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["role_id"], ["roles.id"], name=op.f("fk_join_codes_role_id_roles"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_join_codes_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["revoked_by"],
            ["users.id"],
            name=op.f("fk_join_codes_revoked_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_join_codes")),
        sa.UniqueConstraint("code_hash", name=op.f("uq_join_codes_code_hash")),
    )
    op.create_index("ix_join_codes_workspace_id_status", "join_codes", ["workspace_id", "status"])

    op.create_table(
        "join_requests",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("join_code_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        _status_column(JOIN_REQUEST_STATUSES, "join_request_status", "pending"),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("decided_by", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            _in_list("status", JOIN_REQUEST_STATUSES),
            name=op.f("ck_join_requests_join_request_status"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_join_requests_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_join_requests_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["join_code_id"],
            ["join_codes.id"],
            name=op.f("fk_join_requests_join_code_id_join_codes"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_join_requests_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["roles.id"],
            name=op.f("fk_join_requests_role_id_roles"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["decided_by"],
            ["users.id"],
            name=op.f("fk_join_requests_decided_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_join_requests")),
    )
    op.create_index(
        "uq_join_requests_pending_user_workspace",
        "join_requests",
        ["user_id", "workspace_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        "ix_join_requests_workspace_id_status", "join_requests", ["workspace_id", "status"]
    )


def downgrade() -> None:
    op.drop_index("ix_join_requests_workspace_id_status", table_name="join_requests")
    op.drop_index("uq_join_requests_pending_user_workspace", table_name="join_requests")
    op.drop_table("join_requests")
    op.drop_index("ix_join_codes_workspace_id_status", table_name="join_codes")
    op.drop_table("join_codes")
