"""Admin CLI: user creation and demo seeding."""

from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import cli
from app.models import Role, User
from app.services.users import authenticate_user


@pytest.fixture(autouse=True)
def _use_test_session(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    @contextmanager
    def scope() -> Iterator[Session]:
        yield db_session

    monkeypatch.setattr(cli, "session_scope", scope)


def test_create_user_creates_workspace_and_a_working_login(
    db_session: Session, capsys: pytest.CaptureFixture[str]
) -> None:
    code = cli.main(
        [
            "create-user",
            "--email",
            "Boss@Example.com",
            "--name",
            "The Boss",
            "--role",
            "admin",
            "--workspace",
            "Acme",
            "--password",
            "a-very-long-password",
        ]
    )

    assert code == 0
    assert "Created admin boss@example.com" in capsys.readouterr().out
    created = authenticate_user(db_session, "boss@example.com", "a-very-long-password")
    assert created is not None
    assert created.role is Role.ADMIN


def test_create_user_rejects_weak_password(capsys: pytest.CaptureFixture[str]) -> None:
    code = cli.main(
        ["create-user", "--email", "a@example.com", "--name", "A", "--password", "short"]
    )
    assert code == 1
    assert "at least 12 characters" in capsys.readouterr().err


def test_create_user_rejects_duplicate_email(capsys: pytest.CaptureFixture[str]) -> None:
    args = [
        "create-user",
        "--email",
        "dup@example.com",
        "--name",
        "D",
        "--password",
        "a-very-long-password",
    ]
    assert cli.main(args) == 0
    assert cli.main(args) == 1
    assert "already exists" in capsys.readouterr().err


def test_seed_demo_creates_one_user_per_role_and_is_idempotent(db_session: Session) -> None:
    assert cli.main(["seed-demo"]) == 0
    assert cli.main(["seed-demo"]) == 0  # second run must not fail or duplicate

    demo_users = db_session.scalars(select(User).where(User.email.like("%@demo.local"))).all()
    assert {u.role for u in demo_users} == set(Role)
    assert len(demo_users) == len(Role)
    assert authenticate_user(db_session, "admin@demo.local", cli.DEMO_PASSWORD) is not None


def test_seed_demo_is_refused_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "get_settings", lambda: SimpleNamespace(is_production=True))
    assert cli.main(["seed-demo"]) == 1
