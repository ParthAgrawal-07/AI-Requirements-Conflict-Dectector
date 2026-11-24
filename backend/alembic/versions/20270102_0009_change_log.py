"""written change log, map snapshots for the time slider, last visit to the log

Sprint 6 (Dhavni — US-55, US-50, FR-85, FR-95, FR-96; design update §3.8, §4.1).

* ``graph_events`` — every template sentence of the map's written feed, with the map revision,
  the baseline revision, who did it, the kind (added, merged, conflict found…), the nodes and
  edges it is about (the Changes panel highlights them) and the counts a summary adds up.
  **Backfilled** from the audit log for changes made before this migration: posts, state
  changes, change requests opened and merged, issues opened and closed, concerns, owner changes
  and finding reviews. Backfilled rows have no map revision.
* ``graph_snapshots`` — the whole map frozen when a merge starts a new baseline revision and when
  a labelled baseline is frozen (the time slider shows them read-only).
* ``change_log_visits`` — when a member last read the log ("summarise since my last visit").

``work_item_links`` is not created: US-48 is deferred (design update rev. 5).

Revision ID: 0009
Revises: 0010c
Create Date: 2027-01-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | None = "0010c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KINDS = (
    "'added', 'changed', 'state', 'owner', 'analysed', 'conflict_found', 'conflict_resolved', "
    "'reviewed', 'issue', 'change_request', 'merged', 'concern', 'link'"
)

# Backfill: one INSERT … SELECT per audited action. Sentences follow app.graph.narrator; they
# name requirements by printed ID and people by name, never requirement text (CR-04).
_WHO = "COALESCE(u.full_name, 'Someone')"
_LABEL = "COALESCE(r.source_req_id, 'requirement ' || left(r.id::text, 8))"
_INSERT = """
INSERT INTO graph_events
    (project_id, revision, baseline_revision, actor_id, kind, sentence, node_ids, edge_ids,
     counts, backfilled, created_at)
"""
_STATE_WORDS = f"""
CASE a.details->>'to'
    WHEN 'Approved' THEN {_WHO} || ' approved ' || {_LABEL} || '.'
    WHEN 'Rejected' THEN {_WHO} || ' rejected ' || {_LABEL} || '.'
    WHEN 'Implemented' THEN {_WHO} || ' marked ' || {_LABEL} || ' implemented.'
    WHEN 'Under_Review' THEN {_WHO} || ' moved ' || {_LABEL} || ' to Under review.'
    ELSE {_WHO} || ' moved ' || {_LABEL} || ' to ' || (a.details->>'to') || '.'
END
"""

BACKFILL = [
    # A requirement post.
    f"""{_INSERT}
    SELECT r.project_id, NULL, 0, a.actor_id, 'added',
           {_WHO} || ' added ' || {_LABEL} || ' (Proposed).',
           jsonb_build_array(r.id::text), '[]'::jsonb, '{{"requirements_added": 1}}'::jsonb,
           true, a.at
    FROM audit_log a
    JOIN requirements r ON r.id = a.requirement_id
    LEFT JOIN users u ON u.id = a.actor_id
    WHERE a.action = 'requirement_posted'
    """,
    # A lifecycle move.
    f"""{_INSERT}
    SELECT r.project_id, NULL, 0, a.actor_id, 'state', {_STATE_WORDS},
           jsonb_build_array(r.id::text), '[]'::jsonb,
           CASE WHEN a.details->>'to' = 'Deprecated'
                THEN '{{"requirements_deprecated": 1}}'::jsonb ELSE '{{}}'::jsonb END,
           true, a.at
    FROM audit_log a
    JOIN requirements r ON r.id = a.requirement_id
    LEFT JOIN users u ON u.id = a.actor_id
    WHERE a.action = 'state_changed' AND a.details ? 'to'
    """,
    # A change request opened.
    f"""{_INSERT}
    SELECT r.project_id, NULL, 0, a.actor_id, 'change_request',
           {_WHO} || CASE WHEN a.details->>'kind' = 'deprecate'
                          THEN ' proposed deprecating ' ELSE ' proposed a change to ' END
                 || {_LABEL} || ' (RCR-' || (a.details->>'number') || ').',
           jsonb_build_array(r.id::text), '[]'::jsonb, '{{}}'::jsonb, true, a.at
    FROM audit_log a
    JOIN requirements r ON r.id = a.requirement_id
    LEFT JOIN users u ON u.id = a.actor_id
    WHERE a.action = 'change_request_opened' AND a.details ? 'number'
    """,
    # A change request merged.
    f"""{_INSERT}
    SELECT r.project_id, NULL, 0, a.actor_id, 'merged',
           CASE WHEN a.details->>'kind' = 'deprecate'
                THEN {_WHO} || ' moved ' || {_LABEL} || ' to Deprecated.'
                ELSE {_WHO} || ' merged RCR-' || cr.number || ': ' || {_LABEL} || ' is now v'
                     || (a.details->>'version') || '.' END,
           jsonb_build_array(r.id::text), '[]'::jsonb,
           CASE WHEN a.details->>'kind' = 'deprecate'
                THEN '{{"change_requests_merged": 1, "requirements_deprecated": 1}}'::jsonb
                ELSE '{{"change_requests_merged": 1, "requirements_changed": 1}}'::jsonb END,
           true, a.at
    FROM audit_log a
    JOIN requirements r ON r.id = a.requirement_id
    JOIN change_requests cr ON cr.id = (a.details->>'change_request_id')::uuid
    LEFT JOIN users u ON u.id = a.actor_id
    WHERE a.action = 'change_request_merged'
    """,
    # An issue opened or closed by a person (auto issues have no audit row).
    f"""{_INSERT}
    SELECT i.project_id, NULL, 0, a.actor_id, 'issue',
           {_WHO} || CASE WHEN a.action = 'issue_opened' THEN ' opened ISS-' ELSE ' closed ISS-' END
                 || i.number || '.',
           COALESCE((SELECT jsonb_agg(ir.requirement_id::text) FROM issue_requirements ir
                     WHERE ir.issue_id = i.id), '[]'::jsonb),
           '[]'::jsonb, '{{}}'::jsonb, true, a.at
    FROM audit_log a
    JOIN issues i ON i.id = (a.details->>'issue_id')::uuid
    LEFT JOIN users u ON u.id = a.actor_id
    WHERE a.action IN ('issue_opened', 'issue_closed')
    """,
    # A concern raised (US-56).
    f"""{_INSERT}
    SELECT r.project_id, NULL, 0, a.actor_id, 'concern',
           {_WHO} || ' raised a concern: ' || lower(a.details->>'category') || ' on ' || {_LABEL}
                 || '.',
           a.details->'requirement_ids', '[]'::jsonb, '{{}}'::jsonb, true, a.at
    FROM audit_log a
    JOIN requirements r ON r.id = (a.details->'requirement_ids'->>0)::uuid
    LEFT JOIN users u ON u.id = a.actor_id
    WHERE a.action = 'concern_raised' AND jsonb_array_length(a.details->'requirement_ids') > 0
    """,
    # An owner change.
    f"""{_INSERT}
    SELECT r.project_id, NULL, 0, a.actor_id, 'owner',
           CASE WHEN o.id IS NULL THEN {_WHO} || ' removed the owner of ' || {_LABEL} || '.'
                ELSE {_WHO} || ' made ' || o.full_name || ' the owner of ' || {_LABEL} || '.' END,
           jsonb_build_array(r.id::text), '[]'::jsonb, '{{}}'::jsonb, true, a.at
    FROM audit_log a
    JOIN requirements r ON r.id = a.requirement_id
    LEFT JOIN users u ON u.id = a.actor_id
    LEFT JOIN users o ON o.id::text = a.details->>'after'
    WHERE a.action = 'owner_changed'
    """,
    # A finding review (US-10).
    f"""{_INSERT}
    SELECT f.project_id, NULL, 0, a.actor_id,
           CASE WHEN f.category = 'Conflicting' AND a.action IN ('dismissed', 'merged')
                THEN 'conflict_resolved' ELSE 'reviewed' END,
           {_WHO} || ' ' || a.action || ' a ' || lower(f.category) || ' finding.',
           '[]'::jsonb, jsonb_build_array(f.id::text),
           CASE WHEN f.category = 'Conflicting' AND a.action IN ('dismissed', 'merged')
                THEN '{{"conflicts_resolved": 1}}'::jsonb ELSE '{{}}'::jsonb END,
           true, a.at
    FROM audit_log a
    JOIN findings f ON f.id = a.finding_id
    LEFT JOIN users u ON u.id = a.actor_id
    WHERE a.action IN ('confirmed', 'dismissed', 'merged', 'reclassified')
    """,
]


def _jsonb(name: str, default: str) -> sa.Column[object]:
    return sa.Column(
        name,
        postgresql.JSONB(astext_type=sa.Text()),
        server_default=sa.text(f"'{default}'::jsonb"),
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "graph_events",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=True),
        sa.Column("baseline_revision", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("sentence", sa.Text(), nullable=False),
        _jsonb("node_ids", "[]"),
        _jsonb("edge_ids", "[]"),
        _jsonb("counts", "{}"),
        sa.Column("backfilled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(f"kind IN ({KINDS})", name=op.f("ck_graph_events_kind_values")),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_graph_events_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_graph_events_actor_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_graph_events")),
    )
    op.create_index(
        "ix_graph_events_project_id_created_at", "graph_events", ["project_id", "created_at"]
    )
    op.create_index("ix_graph_events_actor_id", "graph_events", ["actor_id"])
    op.create_index(
        "ix_graph_events_node_ids", "graph_events", ["node_ids"], postgresql_using="gin"
    )

    op.create_table(
        "graph_snapshots",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("graph_revision", sa.Integer(), nullable=False),
        sa.Column("baseline_revision", sa.Integer(), nullable=False),
        sa.Column("baseline_id", sa.Uuid(), nullable=True),
        sa.Column("nodes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("edges", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "captured_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_graph_snapshots_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["baseline_id"],
            ["baselines.id"],
            name=op.f("fk_graph_snapshots_baseline_id_baselines"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_graph_snapshots")),
        sa.UniqueConstraint("baseline_id", name=op.f("uq_graph_snapshots_baseline_id")),
    )
    op.create_index(
        "ix_graph_snapshots_project_id_captured_at",
        "graph_snapshots",
        ["project_id", "captured_at"],
    )
    op.create_index(
        "uq_graph_snapshots_project_id_baseline_revision",
        "graph_snapshots",
        ["project_id", "baseline_revision"],
        unique=True,
        postgresql_where=sa.text("baseline_id IS NULL"),
    )

    op.create_table(
        "change_log_visits",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_change_log_visits_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_change_log_visits_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "project_id", name=op.f("pk_change_log_visits")),
    )

    for statement in BACKFILL:
        op.execute(statement)


def downgrade() -> None:
    op.drop_table("change_log_visits")
    op.drop_index("uq_graph_snapshots_project_id_baseline_revision", table_name="graph_snapshots")
    op.drop_index("ix_graph_snapshots_project_id_captured_at", table_name="graph_snapshots")
    op.drop_table("graph_snapshots")
    op.drop_index("ix_graph_events_node_ids", table_name="graph_events")
    op.drop_index("ix_graph_events_actor_id", table_name="graph_events")
    op.drop_index("ix_graph_events_project_id_created_at", table_name="graph_events")
    op.drop_table("graph_events")
