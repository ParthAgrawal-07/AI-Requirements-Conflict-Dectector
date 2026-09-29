"""Shared pytest configuration and fixtures (Role 5).

Environment
-----------
Tests never touch the development database: ``DATABASE_URL`` is rewritten to a dedicated
``<db>_test`` database (or ``TEST_DATABASE_URL`` if set) *before* the app is imported.

Integration tests (marked ``integration``) need PostgreSQL with pgvector. If it is
unreachable they are skipped locally; set ``REQUIRE_DB=1`` (CI does) to make that a failure
instead, so a broken service container can never masquerade as a green build.
"""

import os
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session


def _ensure_psycopg2_driver(url_str: str) -> str:
    """Force the psycopg2 driver explicitly.

    A bare "postgresql://" (no driver suffix) lets SQLAlchemy pick whichever PostgreSQL
    DBAPI it resolves to by default — in practice that has been ``psycopg`` (v3, not
    installed) rather than ``psycopg2-binary`` (the one we actually install). Every call
    site that turns a connection string into an Engine routes through this first, rather
    than relying on the string having been normalized exactly once upstream.
    """
    url = make_url(url_str)
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+psycopg2")
    return url.render_as_string(hide_password=False)


def _resolve_test_database_url() -> str:
    explicit = os.environ.get("TEST_DATABASE_URL")
    if explicit:
        return _ensure_psycopg2_driver(explicit)
    base = os.environ.get(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/requirements_conflict_detector",
    )
    if base.startswith("postgres://"):
        base = "postgresql://" + base.removeprefix("postgres://")
    url = make_url(_ensure_psycopg2_driver(base))
    return url.set(database=f"{url.database}_test").render_as_string(hide_password=False)


# Must run before anything imports app.core.config (settings are cached on first use).
os.environ["ENVIRONMENT"] = "test"
os.environ["JWT_SECRET"] = "test-only-secret-not-for-production-use-0123456789abcdef"
os.environ["DATABASE_URL"] = _resolve_test_database_url()
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from app.core import security  # noqa: E402
from app.models import Document, DocumentFormat, Requirement, Role, User, Workspace  # noqa: E402
from app.services.users import create_user  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[1]
TEST_PASSWORD = "correct-horse-battery-staple"


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Anything using the database fixtures is an integration test — mark it automatically."""
    for item in items:
        if {"db_engine", "db_session", "client", "scratch_engine"} & set(
            getattr(item, "fixturenames", ())
        ):
            item.add_marker(pytest.mark.integration)


@pytest.fixture(autouse=True)
def _fast_password_hashing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Argon2 with production parameters costs ~100 ms per hash; use minimal cost in tests."""
    monkeypatch.setattr(
        security, "_hasher", PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)
    )
    security.dummy_password_hash.cache_clear()


# ── Database ─────────────────────────────────────────────────────────────────
def _ensure_database(url_str: str) -> None:
    """Create the target database if it does not exist yet."""
    url = make_url(_ensure_psycopg2_driver(url_str))
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            exists = conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": url.database}
            )
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    finally:
        admin.dispose()


def _run_migrations(engine: Engine, revision: str = "head") -> None:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.attributes["configure_logger"] = False
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, revision)


def _reset_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))


@pytest.fixture(scope="session")
def db_engine() -> Iterator[Engine]:
    """A migrated, empty PostgreSQL database. Built with Alembic, so migrations are exercised."""
    url = _ensure_psycopg2_driver(os.environ["DATABASE_URL"])
    try:
        _ensure_database(url)
    except OperationalError as exc:
        message = f"PostgreSQL is not reachable for integration tests: {exc.orig}"
        if os.environ.get("REQUIRE_DB") == "1":
            pytest.fail(message)
        pytest.skip(message)
    engine = create_engine(url)
    _reset_schema(engine)
    _run_migrations(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def scratch_engine() -> Iterator[Engine]:
    """A throw-away empty database, for tests that must migrate up/down themselves."""
    base = make_url(_ensure_psycopg2_driver(os.environ["DATABASE_URL"]))
    name = f"{base.database}_scratch_{uuid.uuid4().hex[:8]}"
    url = base.set(database=name).render_as_string(hide_password=False)
    try:
        _ensure_database(url)
    except OperationalError as exc:
        if os.environ.get("REQUIRE_DB") == "1":
            pytest.fail(f"PostgreSQL is not reachable: {exc.orig}")
        pytest.skip(f"PostgreSQL is not reachable: {exc.orig}")
    engine = create_engine(url)
    yield engine
    engine.dispose()
    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    admin.dispose()


@pytest.fixture
def db_session(db_engine: Engine) -> Iterator[Session]:
    """A session inside a transaction that is rolled back after the test.

    ``create_savepoint`` means code under test may call ``session.commit()`` freely — it only
    releases a savepoint; nothing is ever persisted.
    """
    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
        autoflush=False,
        expire_on_commit=False,
    )
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


# ── HTTP clients ─────────────────────────────────────────────────────────────
@pytest.fixture
def plain_client() -> Iterator[TestClient]:
    """App client with no database override — for behaviour that never reaches the DB."""
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    """App client whose every request uses the rolled-back test session."""
    from app.core.database import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)


# ── Factories ────────────────────────────────────────────────────────────────
@pytest.fixture
def workspace(db_session: Session) -> Workspace:
    ws = Workspace(name=f"Workspace {uuid.uuid4().hex[:8]}")
    db_session.add(ws)
    db_session.commit()
    return ws


@pytest.fixture
def make_user(db_session: Session, workspace: Workspace) -> Callable[..., User]:
    def factory(
        *,
        role: Role = Role.ANALYST,
        email: str | None = None,
        password: str = TEST_PASSWORD,
        is_active: bool = True,
    ) -> User:
        user = create_user(
            db_session,
            email=email or f"user-{uuid.uuid4().hex[:8]}@example.com",
            password=password,
            full_name="Test User",
            role=role,
            workspace=workspace,
        )
        if not is_active:
            user.is_active = False
            db_session.commit()
        return user

    return factory


@pytest.fixture
def user(make_user: Callable[..., User]) -> User:
    return make_user()


@pytest.fixture
def make_requirement(
    db_session: Session, workspace: Workspace, user: User
) -> Callable[..., Requirement]:
    document = Document(
        workspace_id=workspace.id,
        uploaded_by=user.id,
        filename="srs.docx",
        format=DocumentFormat.DOCX,
        size_bytes=1024,
        sha256="0" * 64,
        storage_path="/data/uploads/srs.docx",
    )
    db_session.add(document)
    db_session.commit()

    def factory(
        body: str = "The system shall log every login attempt.", **kwargs: object
    ) -> Requirement:
        requirement = Requirement(document_id=document.id, body=body, **kwargs)
        db_session.add(requirement)
        db_session.commit()
        return requirement

    return factory


@pytest.fixture
def auth_headers(user: User) -> dict[str, str]:
    token, _ = security.create_access_token(user.id)
    return {"Authorization": f"Bearer {token}"}
