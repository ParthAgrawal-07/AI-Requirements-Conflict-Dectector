"""tenancy and permission-based roles: projects, memberships, roles, role_permissions

Sprint 0 (rev. 5 plan, design update §4.3 and ADR-14, ADR-20, SX-06).

What this migration does
------------------------
1. Creates ``projects``, ``roles``, ``role_permissions``, ``memberships`` and ``project_members``.
2. Seeds the nine **default roles** with the permissions of spec §1.22 (a frozen copy — see
   ``SEED_ROLES`` below; ``tests/db/test_default_roles.py`` checks it against
   ``app.core.permissions``).
3. Adds ``project_id`` to ``documents`` and ``requirements`` and the requirement lifecycle
   columns Sprint 1 needs (``state``, ``origin``, ``owner_id``), plus ``documents.import_mode``
   and ``documents.stakeholder_group`` (US-01).
4. **Backfills existing data** so nothing is lost: one project per workspace (status
   ``active``), one membership per user, the first user of each workspace becomes Owner.
5. Drops the old single-workspace columns ``users.role`` and ``users.workspace_id``.

Role mapping (design update §4.3): ``analyst -> Business Analyst``, ``admin -> Admin``,
``compliance_reviewer -> Compliance Reviewer``, ``read_only -> Viewer``; the first admin of each
workspace (else its earliest active user) becomes ``Owner``. ``service`` accounts get
``users.platform_role = 'service'`` and no membership. Existing documents are treated as
baseline imports and their requirements as ``Approved`` (the old system analysed them as the
specification).

Deviation from the design-update table, deliberate and flagged to the team: ``projects.status``
and ``projects.context_version`` are created here (not in ``0011_project_context``) because
US-24 creates projects in ``setup`` state in Sprint 1; likewise ``requirements.state/origin/
owner_id`` are created here (not in ``0006``) because US-02/US-04 read and write them in
Sprint 1. ``0006`` keeps ``origin_message_id`` and the composer fields; ``0011`` keeps
``project_contexts``, ``document_sections`` and ``findings.context_version``.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-17
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# ── Frozen seed: (role name, description, permissions). Do not edit — add a new migration. ──
SEED_ROLES: list[tuple[str, str, list[str]]] = [
    (
        "Owner",
        "Runs the workspace: everything, including settings and ownership transfer.",
        [
            "workspace.manage",
            "roles.manage",
            "members.manage",
            "joincode.manage",
            "project.manage",
            "project.context",
            "srs.generate",
            "srs.publish",
            "channel.manage",
            "message.post",
            "req.propose",
            "req.comment",
            "req.vote",
            "req.link",
            "doc.upload",
            "baseline.manage",
            "issue.open",
            "issue.manage",
            "rcr.open",
            "rcr.review",
            "rcr.merge",
            "finding.review",
            "req.protect",
            "req.implement",
            "audit.export",
            "view",
        ],
    ),
    (
        "Admin",
        "Manages members, roles and projects; cannot transfer or delete the workspace.",
        [
            "roles.manage",
            "members.manage",
            "joincode.manage",
            "project.manage",
            "project.context",
            "srs.generate",
            "srs.publish",
            "channel.manage",
            "message.post",
            "req.propose",
            "req.comment",
            "req.vote",
            "req.link",
            "doc.upload",
            "baseline.manage",
            "issue.open",
            "issue.manage",
            "rcr.open",
            "rcr.review",
            "rcr.merge",
            "finding.review",
            "req.protect",
            "req.implement",
            "audit.export",
            "view",
        ],
    ),
    (
        "Project Manager",
        "Runs a project: context, join codes, members, settings and SRS publishing.",
        [
            "members.manage",
            "joincode.manage",
            "project.manage",
            "project.context",
            "srs.generate",
            "srs.publish",
            "channel.manage",
            "message.post",
            "req.propose",
            "req.comment",
            "req.vote",
            "req.link",
            "doc.upload",
            "baseline.manage",
            "issue.open",
            "issue.manage",
            "rcr.open",
            "rcr.review",
            "rcr.merge",
            "finding.review",
            "req.implement",
            "view",
        ],
    ),
    (
        "Business Analyst",
        "Reviews findings, manages the baseline and merges approved changes.",
        [
            "srs.generate",
            "channel.manage",
            "message.post",
            "req.propose",
            "req.comment",
            "req.vote",
            "req.link",
            "doc.upload",
            "baseline.manage",
            "issue.open",
            "issue.manage",
            "rcr.open",
            "rcr.review",
            "rcr.merge",
            "finding.review",
            "req.implement",
            "view",
        ],
    ),
    (
        "Developer",
        "Proposes requirements, opens issues and change requests, reviews changes.",
        [
            "message.post",
            "req.propose",
            "req.comment",
            "req.vote",
            "req.link",
            "doc.upload",
            "issue.open",
            "rcr.open",
            "rcr.review",
            "req.implement",
            "view",
        ],
    ),
    (
        "QA Engineer",
        "Proposes requirements, opens issues and change requests, reviews changes.",
        [
            "message.post",
            "req.propose",
            "req.comment",
            "req.vote",
            "req.link",
            "doc.upload",
            "issue.open",
            "rcr.open",
            "rcr.review",
            "view",
        ],
    ),
    (
        "Stakeholder",
        "Client or domain expert: proposes, discusses, votes and reviews.",
        [
            "message.post",
            "req.propose",
            "req.comment",
            "req.vote",
            "doc.upload",
            "issue.open",
            "rcr.open",
            "rcr.review",
            "view",
        ],
    ),
    (
        "Compliance Reviewer",
        "Signs off protected requirements; discusses and reviews; no proposing.",
        [
            "message.post",
            "req.comment",
            "issue.open",
            "rcr.review",
            "finding.review",
            "req.protect",
            "protected.signoff",
            "audit.export",
            "view",
        ],
    ),
    (
        "Viewer",
        "Read-only access to dashboards, the map and reports.",
        [
            "view",
        ],
    ),
]

PROTECTED_ONLY = {("Compliance Reviewer", "finding.review")}

REQUIREMENT_STATES = (
    "Proposed",
    "Under_Review",
    "Approved",
    "Rejected",
    "Implemented",
    "Deprecated",
)
REQUIREMENT_ORIGINS = ("document", "post", "change_request")
PROJECT_STATUSES = ("setup", "active", "archived")
IMPORT_MODES = ("baseline", "proposals")
PLATFORM_ROLES = ("platform_admin", "service")
LEGACY_ROLES = ("analyst", "admin", "compliance_reviewer", "read_only", "service")


def _in_list(column: str, values: Sequence[str]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _id_column() -> sa.Column:
    return sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def _timestamps() -> list[sa.Column]:
    return [
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
    ]


def upgrade() -> None:
    # ── 1. new tables ────────────────────────────────────────────────────────────────────
    op.create_table(
        "projects",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                *PROJECT_STATUSES,
                name="project_status",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            server_default="setup",
            nullable=False,
        ),
        sa.Column("context_version", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "similarity_threshold", sa.Float(), server_default=sa.text("0.75"), nullable=False
        ),
        sa.Column(
            "confidence_threshold", sa.Float(), server_default=sa.text("0.5"), nullable=False
        ),
        sa.Column(
            "llm_budget_monthly_calls", sa.Integer(), server_default=sa.text("2000"), nullable=False
        ),
        sa.Column(
            "chat_detection_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("required_approvals", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        _id_column(),
        *_timestamps(),
        sa.CheckConstraint(
            _in_list("status", PROJECT_STATUSES), name=op.f("ck_projects_project_status")
        ),
        sa.CheckConstraint(
            "similarity_threshold BETWEEN 0 AND 1",
            name=op.f("ck_projects_similarity_threshold_range"),
        ),
        sa.CheckConstraint(
            "confidence_threshold BETWEEN 0 AND 1",
            name=op.f("ck_projects_confidence_threshold_range"),
        ),
        sa.CheckConstraint(
            "llm_budget_monthly_calls >= 0", name=op.f("ck_projects_llm_budget_non_negative")
        ),
        sa.CheckConstraint(
            "required_approvals BETWEEN 1 AND 3", name=op.f("ck_projects_required_approvals_range")
        ),
        sa.CheckConstraint(
            "context_version >= 0", name=op.f("ck_projects_context_version_non_negative")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_projects_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_projects_workspace_id_workspaces"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_projects")),
        sa.UniqueConstraint("workspace_id", "name", name=op.f("uq_projects_workspace_id_name")),
    )
    op.create_index(
        "ix_projects_workspace_id_status", "projects", ["workspace_id", "status"], unique=False
    )

    op.create_table(
        "roles",
        sa.Column("workspace_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        _id_column(),
        *_timestamps(),
        sa.CheckConstraint(
            "(is_default AND workspace_id IS NULL) OR (NOT is_default AND workspace_id IS NOT NULL)",
            name=op.f("ck_roles_default_roles_are_global"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_roles_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_roles")),
    )
    op.create_index(
        "uq_roles_default_name",
        "roles",
        ["name"],
        unique=True,
        postgresql_where=sa.text("workspace_id IS NULL"),
    )
    op.create_index(
        "uq_roles_workspace_id_name",
        "roles",
        ["workspace_id", "name"],
        unique=True,
        postgresql_where=sa.text("workspace_id IS NOT NULL"),
    )

    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("permission", sa.String(length=64), nullable=False),
        sa.Column("protected_only", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["roles.id"],
            name=op.f("fk_role_permissions_role_id_roles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("role_id", "permission", name=op.f("pk_role_permissions")),
    )

    op.create_table(
        "memberships",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("stakeholder_group", sa.String(length=120), nullable=True),
        sa.Column(
            "joined_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        _id_column(),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["roles.id"],
            name=op.f("fk_memberships_role_id_roles"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_memberships_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_memberships_workspace_id_workspaces"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_memberships")),
    )
    op.create_index(
        "uq_memberships_active_user_workspace",
        "memberships",
        ["user_id", "workspace_id"],
        unique=True,
        postgresql_where=sa.text("ended_at IS NULL"),
    )
    op.create_index(
        "ix_memberships_workspace_id_ended_at",
        "memberships",
        ["workspace_id", "ended_at"],
        unique=False,
    )
    op.create_index("ix_memberships_user_id", "memberships", ["user_id"], unique=False)

    op.create_table(
        "project_members",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role_override_id", sa.Uuid(), nullable=True),
        sa.Column(
            "added_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_project_members_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["role_override_id"],
            ["roles.id"],
            name=op.f("fk_project_members_role_override_id_roles"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_project_members_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("project_id", "user_id", name=op.f("pk_project_members")),
    )

    # ── 2. new columns (nullable first, so existing rows can be backfilled) ───────────────
    op.add_column(
        "users",
        sa.Column(
            "platform_role",
            sa.Enum(
                *PLATFORM_ROLES,
                name="user_platform_role",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        op.f("ck_users_user_platform_role"), "users", _in_list("platform_role", PLATFORM_ROLES)
    )

    op.add_column("documents", sa.Column("project_id", sa.Uuid(), nullable=True))
    op.add_column(
        "documents",
        sa.Column(
            "import_mode",
            sa.Enum(
                *IMPORT_MODES,
                name="document_import_mode",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            server_default="proposals",
            nullable=False,
        ),
    )
    op.add_column("documents", sa.Column("stakeholder_group", sa.String(length=120), nullable=True))
    op.create_check_constraint(
        op.f("ck_documents_document_import_mode"),
        "documents",
        _in_list("import_mode", IMPORT_MODES),
    )

    op.add_column("requirements", sa.Column("project_id", sa.Uuid(), nullable=True))
    op.add_column(
        "requirements",
        sa.Column(
            "state",
            sa.Enum(
                *REQUIREMENT_STATES,
                name="requirement_state",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            server_default="Proposed",
            nullable=False,
        ),
    )
    op.add_column(
        "requirements",
        sa.Column(
            "origin",
            sa.Enum(
                *REQUIREMENT_ORIGINS,
                name="requirement_origin",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            server_default="document",
            nullable=False,
        ),
    )
    op.add_column("requirements", sa.Column("owner_id", sa.Uuid(), nullable=True))
    op.create_check_constraint(
        op.f("ck_requirements_requirement_state"),
        "requirements",
        _in_list("state", REQUIREMENT_STATES),
    )
    op.create_check_constraint(
        op.f("ck_requirements_requirement_origin"),
        "requirements",
        _in_list("origin", REQUIREMENT_ORIGINS),
    )

    # ── 3. seed the nine default roles ───────────────────────────────────────────────────
    connection = op.get_bind()
    role_ids: dict[str, uuid.UUID] = {}
    roles_table = sa.table(
        "roles",
        sa.column("id", sa.Uuid()),
        sa.column("name", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("is_default", sa.Boolean()),
    )
    grants_table = sa.table(
        "role_permissions",
        sa.column("role_id", sa.Uuid()),
        sa.column("permission", sa.String()),
        sa.column("protected_only", sa.Boolean()),
    )
    for name, description, permissions in SEED_ROLES:
        role_id = uuid.uuid4()
        role_ids[name] = role_id
        connection.execute(
            sa.insert(roles_table).values(
                id=role_id, name=name, description=description, is_default=True
            )
        )
        connection.execute(
            sa.insert(grants_table),
            [
                {
                    "role_id": role_id,
                    "permission": permission,
                    "protected_only": (name, permission) in PROTECTED_ONLY,
                }
                for permission in permissions
            ],
        )

    # ── 4. backfill existing data ────────────────────────────────────────────────────────
    # One project per workspace. Existing data was analysed as "the" specification, so the
    # project starts active (no setup gate on data that predates the context requirement).
    op.execute(
        """
        INSERT INTO projects (id, workspace_id, name, status, similarity_threshold)
        SELECT gen_random_uuid(), w.id, w.name, 'active', w.similarity_threshold
        FROM workspaces w
        """
    )

    # One membership per human user. The first user of each workspace (admins first, active
    # first, then oldest) becomes Owner so every workspace keeps an owner.
    op.execute(
        """
        INSERT INTO memberships (id, user_id, workspace_id, role_id)
        SELECT gen_random_uuid(), ranked.id, ranked.workspace_id, r.id
        FROM (
            SELECT u.id, u.workspace_id, u.role,
                   row_number() OVER (
                       PARTITION BY u.workspace_id
                       ORDER BY u.is_active DESC, (u.role = 'admin') DESC, u.created_at, u.id
                   ) AS rn
            FROM users u
            WHERE u.role <> 'service'
        ) AS ranked
        JOIN roles r ON r.workspace_id IS NULL AND r.name = CASE
            WHEN ranked.rn = 1 THEN 'Owner'
            WHEN ranked.role = 'admin' THEN 'Admin'
            WHEN ranked.role = 'analyst' THEN 'Business Analyst'
            WHEN ranked.role = 'compliance_reviewer' THEN 'Compliance Reviewer'
            WHEN ranked.role = 'read_only' THEN 'Viewer'
        END
        """
    )
    op.execute("UPDATE users SET platform_role = 'service' WHERE role = 'service'")

    op.execute(
        """
        UPDATE documents d
        SET project_id = p.id, import_mode = 'baseline'
        FROM projects p
        WHERE p.workspace_id = d.workspace_id
        """
    )
    op.execute(
        """
        UPDATE requirements r
        SET project_id = d.project_id, state = 'Approved'
        FROM documents d
        WHERE d.id = r.document_id
        """
    )

    # ── 5. tighten, index, link ──────────────────────────────────────────────────────────
    op.alter_column("documents", "project_id", nullable=False)
    op.alter_column("requirements", "project_id", nullable=False)
    op.create_foreign_key(
        op.f("fk_documents_project_id_projects"),
        "documents",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_requirements_project_id_projects"),
        "requirements",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_requirements_owner_id_users"),
        "requirements",
        "users",
        ["owner_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_documents_project_id_uploaded_at",
        "documents",
        ["project_id", "uploaded_at"],
        unique=False,
    )
    op.create_index(
        "ix_requirements_project_id_state", "requirements", ["project_id", "state"], unique=False
    )
    op.create_index(op.f("ix_requirements_owner_id"), "requirements", ["owner_id"], unique=False)

    # ── 6. retire the single-workspace columns ───────────────────────────────────────────
    op.drop_index(op.f("ix_users_workspace_id"), table_name="users")
    op.drop_column("users", "workspace_id")  # also drops its foreign key
    op.drop_column("users", "role")  # also drops ck_users_user_role


def downgrade() -> None:
    connection = op.get_bind()

    # ── restore users.role / users.workspace_id from memberships (best effort) ────────────
    op.add_column("users", sa.Column("workspace_id", sa.Uuid(), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "role",
            sa.Enum(
                *LEGACY_ROLES,
                name="user_role",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            nullable=True,
        ),
    )
    # Each user keeps their oldest active membership. Owner/Admin -> admin, Compliance Reviewer
    # -> compliance_reviewer, Viewer -> read_only, every other role (including custom) -> analyst.
    op.execute(
        """
        UPDATE users u
        SET workspace_id = m.workspace_id,
            role = CASE r.name
                WHEN 'Owner' THEN 'admin'
                WHEN 'Admin' THEN 'admin'
                WHEN 'Compliance Reviewer' THEN 'compliance_reviewer'
                WHEN 'Viewer' THEN 'read_only'
                ELSE 'analyst'
            END
        FROM (
            SELECT DISTINCT ON (user_id) user_id, workspace_id, role_id
            FROM memberships
            WHERE ended_at IS NULL
            ORDER BY user_id, joined_at, id
        ) m
        JOIN roles r ON r.id = m.role_id
        WHERE u.id = m.user_id
        """
    )
    op.execute("UPDATE users SET role = 'service' WHERE platform_role = 'service'")
    # Users with no active membership (platform admins, service accounts, removed members) need
    # *some* workspace to satisfy NOT NULL. Service accounts keep their role; their original
    # workspace is not recoverable because they never had a membership.
    orphans = connection.scalar(sa.text("SELECT count(*) FROM users WHERE workspace_id IS NULL"))
    if orphans:
        op.execute(
            "INSERT INTO workspaces (id, name) VALUES (gen_random_uuid(), 'Recovered users') "
            "ON CONFLICT (name) DO NOTHING"
        )
        op.execute(
            """
            UPDATE users
            SET workspace_id = (SELECT id FROM workspaces WHERE name = 'Recovered users'),
                role = CASE
                    WHEN role = 'service' THEN 'service'
                    WHEN platform_role = 'platform_admin' THEN 'admin'
                    ELSE 'read_only'
                END
            WHERE workspace_id IS NULL
            """
        )
    op.alter_column("users", "workspace_id", nullable=False)
    op.alter_column("users", "role", nullable=False)
    op.create_foreign_key(
        op.f("fk_users_workspace_id_workspaces"),
        "users",
        "workspaces",
        ["workspace_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(op.f("ix_users_workspace_id"), "users", ["workspace_id"], unique=False)
    op.create_check_constraint(op.f("ck_users_user_role"), "users", _in_list("role", LEGACY_ROLES))

    # ── undo the column additions ────────────────────────────────────────────────────────
    op.drop_index(op.f("ix_requirements_owner_id"), table_name="requirements")
    op.drop_index("ix_requirements_project_id_state", table_name="requirements")
    op.drop_index("ix_documents_project_id_uploaded_at", table_name="documents")
    op.drop_constraint(op.f("fk_requirements_owner_id_users"), "requirements", type_="foreignkey")
    op.drop_constraint(
        op.f("fk_requirements_project_id_projects"), "requirements", type_="foreignkey"
    )
    op.drop_constraint(op.f("fk_documents_project_id_projects"), "documents", type_="foreignkey")
    op.drop_constraint(op.f("ck_requirements_requirement_origin"), "requirements", type_="check")
    op.drop_constraint(op.f("ck_requirements_requirement_state"), "requirements", type_="check")
    op.drop_column("requirements", "owner_id")
    op.drop_column("requirements", "origin")
    op.drop_column("requirements", "state")
    op.drop_column("requirements", "project_id")
    op.drop_constraint(op.f("ck_documents_document_import_mode"), "documents", type_="check")
    op.drop_column("documents", "stakeholder_group")
    op.drop_column("documents", "import_mode")
    op.drop_column("documents", "project_id")
    op.drop_constraint(op.f("ck_users_user_platform_role"), "users", type_="check")
    op.drop_column("users", "platform_role")

    # ── drop the new tables, children first ──────────────────────────────────────────────
    op.drop_table("project_members")
    op.drop_index("ix_memberships_user_id", table_name="memberships")
    op.drop_index("ix_memberships_workspace_id_ended_at", table_name="memberships")
    op.drop_index(
        "uq_memberships_active_user_workspace",
        table_name="memberships",
        postgresql_where=sa.text("ended_at IS NULL"),
    )
    op.drop_table("memberships")
    op.drop_table("role_permissions")
    op.drop_index(
        "uq_roles_workspace_id_name",
        table_name="roles",
        postgresql_where=sa.text("workspace_id IS NOT NULL"),
    )
    op.drop_index(
        "uq_roles_default_name",
        table_name="roles",
        postgresql_where=sa.text("workspace_id IS NULL"),
    )
    op.drop_table("roles")
    op.drop_index("ix_projects_workspace_id_status", table_name="projects")
    op.drop_table("projects")
