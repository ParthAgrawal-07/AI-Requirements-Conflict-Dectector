"""Migration health: single head, models == migrations, and a clean up/down round trip."""

from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, inspect, text

from app.models import Base
from tests.conftest import BACKEND_DIR

EXPECTED_TABLES = {
    "workspaces",
    "users",
    "documents",
    "requirements",
    "requirement_versions",
    "embeddings",
    "candidate_pairs",
    "findings",
    "clarifications",
    "audit_log",
    # Sprint 0 (0004_tenancy_roles)
    "projects",
    "roles",
    "role_permissions",
    "memberships",
    "project_members",
    # Sprint 1 (0011_project_context)
    "project_contexts",
    "document_sections",
    # Sprint 1 (0005_collaboration, join tables)
    "join_codes",
    "join_requests",
    # Sprint 2 (0006b_drafts_posts)
    "requirement_drafts",
    # Sprint 2 (0005b_channels_messages)
    "channels",
    "channel_members",
    "channel_reads",
    "messages",
}


def _config() -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.attributes["configure_logger"] = False
    return config


def test_there_is_exactly_one_migration_head() -> None:
    """Two PRs that both add a migration create two heads — catch that before merge."""
    heads = ScriptDirectory.from_config(_config()).get_heads()
    assert len(heads) == 1, f"Multiple Alembic heads: {heads}. Run `alembic merge heads`."


def test_migration_files_live_where_expected() -> None:
    assert list((Path(BACKEND_DIR) / "alembic" / "versions").glob("*_initial_schema.py"))


def test_upgrade_creates_every_table(db_engine: Engine) -> None:
    assert set(inspect(db_engine).get_table_names()) >= EXPECTED_TABLES


def test_pgvector_extension_is_installed(db_engine: Engine) -> None:
    with db_engine.connect() as conn:
        assert conn.scalar(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")) == 1


def test_models_and_migrations_are_in_sync(db_engine: Engine) -> None:
    """Fails if someone edits a model without generating a migration (or vice versa)."""
    with db_engine.connect() as conn:
        context = MigrationContext.configure(conn, opts={"compare_type": True})
        diff = compare_metadata(context, Base.metadata)
    assert diff == [], (
        f"Models differ from migrations — run `alembic revision --autogenerate`: {diff}"
    )


def test_downgrade_to_base_and_back(scratch_engine: Engine) -> None:
    config = _config()
    with scratch_engine.begin() as conn:
        config.attributes["connection"] = conn
        command.upgrade(config, "head")
    assert set(inspect(scratch_engine).get_table_names()) >= EXPECTED_TABLES

    with scratch_engine.begin() as conn:
        config.attributes["connection"] = conn
        command.downgrade(config, "base")
    remaining = set(inspect(scratch_engine).get_table_names()) - {"alembic_version"}
    assert remaining == set()
    with scratch_engine.connect() as conn:
        assert (
            conn.scalar(
                text("SELECT count(*) FROM pg_proc WHERE proname = 'audit_log_reject_mutation'")
            )
            == 0
        )

    with scratch_engine.begin() as conn:
        config.attributes["connection"] = conn
        command.upgrade(config, "head")
    assert set(inspect(scratch_engine).get_table_names()) >= EXPECTED_TABLES


def test_downgrade_of_0006b_refuses_while_posted_requirements_exist(
    scratch_engine: Engine,
) -> None:
    config = _config()
    with scratch_engine.begin() as conn:
        config.attributes["connection"] = conn
        command.upgrade(config, "head")
        workspace_id = conn.scalar(text("INSERT INTO workspaces (name) VALUES ('W') RETURNING id"))
        project_id = conn.scalar(
            text("INSERT INTO projects (workspace_id, name) VALUES (:w, 'P') RETURNING id"),
            {"w": workspace_id},
        )
        conn.execute(
            text(
                "INSERT INTO requirements (project_id, document_id, origin, body)"
                " VALUES (:p, NULL, 'post', 'The system shall log out idle users.')"
            ),
            {"p": project_id},
        )
        head = conn.scalar(text("SELECT version_num FROM alembic_version"))

    with (
        pytest.raises(RuntimeError, match="posted requirement"),
        scratch_engine.begin() as conn,
    ):
        config.attributes["connection"] = conn
        command.downgrade(config, "0006")
    with scratch_engine.connect() as conn:
        # The refused downgrade rolls back whole, including the revisions above 0006b.
        assert conn.scalar(text("SELECT version_num FROM alembic_version")) == head


def test_downgrade_of_0006c_keeps_the_live_finding_of_a_pair(scratch_engine: Engine) -> None:
    config = _config()
    with scratch_engine.begin() as conn:
        config.attributes["connection"] = conn
        command.upgrade(config, "head")

        def insert(sql: str, **values: object) -> object:
            return conn.scalar(text(sql), values)

        workspace = insert("INSERT INTO workspaces (name) VALUES ('W') RETURNING id")
        project = insert(
            "INSERT INTO projects (workspace_id, name) VALUES (:w, 'P') RETURNING id", w=workspace
        )
        user = insert(
            "INSERT INTO users (email, full_name, hashed_password)"
            " VALUES ('u@example.com', 'U', 'x') RETURNING id"
        )
        document = insert(
            "INSERT INTO documents (workspace_id, project_id, uploaded_by, filename, format,"
            " size_bytes, sha256, storage_path)"
            " VALUES (:w, :p, :u, 'srs.docx', 'docx', 1, :sha, 'srs.docx') RETURNING id",
            w=workspace,
            p=project,
            u=user,
            sha="0" * 64,
        )
        a, b = (
            insert(
                "INSERT INTO requirements (project_id, document_id, body)"
                " VALUES (:p, :d, :body) RETURNING id",
                p=project,
                d=document,
                body=body,
            )
            for body in ("Replies within 2 s.", "Replies within 10 s.")
        )
        first, second = sorted([str(a), str(b)])
        pair = insert(
            "INSERT INTO candidate_pairs (requirement_a_id, requirement_b_id, similarity_score)"
            " VALUES (:a, :b, 0.9) RETURNING id",
            a=first,
            b=second,
        )
        findings = (
            "INSERT INTO findings (project_id, document_id, candidate_pair_id, category,"
            " confidence, rationale, original_ai_output, is_stale)"
            " VALUES (:p, :d, :pair, 'Conflicting', 0.8, :r, '{}', :stale) RETURNING id"
        )
        insert(findings, p=project, d=document, pair=pair, r="old", stale=True)
        live = insert(findings, p=project, d=document, pair=pair, r="new", stale=False)

    with scratch_engine.begin() as conn:
        config.attributes["connection"] = conn
        command.downgrade(config, "0006b")
    with scratch_engine.connect() as conn:
        assert [str(row) for row in conn.scalars(text("SELECT id FROM findings"))] == [str(live)]
