"""Migration health: single head, models == migrations, and a clean up/down round trip."""

from pathlib import Path

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
