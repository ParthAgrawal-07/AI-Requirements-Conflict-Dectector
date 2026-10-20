"""Admin CLI: platform-admin creation and demo seeding."""

from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import cli
from app.core.config import Environment
from app.core.permissions import DefaultRole
from app.models import Membership, PlatformRole, Project, ProjectStatus, Role, User, Workspace
from app.services.users import authenticate_user, create_user


@pytest.fixture(autouse=True)
def _use_test_session(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    @contextmanager
    def scope() -> Iterator[Session]:
        yield db_session
        db_session.commit()  # like the real session_scope: commit when the block succeeds

    monkeypatch.setattr(cli, "session_scope", scope)


def _admin_args(email: str = "boss@example.com", *extra: str) -> list[str]:
    return [
        "create-admin",
        "--email",
        email,
        "--name",
        "The Boss",
        "--password",
        "a-very-long-password",
        *extra,
    ]


def test_create_admin_makes_a_platform_admin_with_no_workspace_and_a_working_login(
    db_session: Session, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(_admin_args("Boss@Example.com")) == 0

    assert "Created platform administrator boss@example.com" in capsys.readouterr().out
    created = authenticate_user(db_session, "boss@example.com", "a-very-long-password")
    assert created is not None
    assert created.platform_role is PlatformRole.PLATFORM_ADMIN and created.is_platform_admin
    assert (
        db_session.scalars(select(Membership).where(Membership.user_id == created.id)).all() == []
    )


def test_create_admin_rejects_weak_password(capsys: pytest.CaptureFixture[str]) -> None:
    code = cli.main(
        ["create-admin", "--email", "a@example.com", "--name", "A", "--password", "short"]
    )
    assert code == 1
    assert "at least 12 characters" in capsys.readouterr().err


def test_create_admin_rejects_duplicate_email_without_promote(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(_admin_args("dup@example.com")) == 0
    assert cli.main(_admin_args("dup@example.com")) == 1
    err = capsys.readouterr().err
    assert "already exists" in err and "--promote" in err


def test_promote_turns_an_existing_user_into_a_platform_admin(
    db_session: Session, capsys: pytest.CaptureFixture[str]
) -> None:
    existing = create_user(
        db_session,
        email="owner@example.com",
        password="a-very-long-password",
        full_name="Owner",
    )
    assert existing.platform_role is None

    assert cli.main(_admin_args("owner@example.com", "--promote")) == 0

    assert "Promoted owner@example.com" in capsys.readouterr().out
    db_session.refresh(existing)
    assert existing.platform_role is PlatformRole.PLATFORM_ADMIN


def test_seed_demo_creates_one_member_per_default_role_and_is_idempotent(
    db_session: Session,
) -> None:
    assert cli.main(["seed-demo"]) == 0
    assert cli.main(["seed-demo"]) == 0  # second run must not fail or duplicate

    demo_users = db_session.scalars(select(User).where(User.email.like("%@demo.local"))).all()
    assert len(demo_users) == len(DefaultRole)

    workspace = db_session.scalars(
        select(Workspace).where(Workspace.name == cli.DEMO_WORKSPACE)
    ).one()
    memberships = db_session.execute(
        select(Role.name, User.email)
        .join(Membership, Membership.role_id == Role.id)
        .join(User, User.id == Membership.user_id)
        .where(Membership.workspace_id == workspace.id, Membership.ended_at.is_(None))
    ).all()
    assert {name for name, _ in memberships} == {role.value for role in DefaultRole}
    assert len(memberships) == len(DefaultRole)  # exactly one active membership each
    assert dict(memberships)["Owner"] == "owner@demo.local"
    assert authenticate_user(db_session, "admin@demo.local", cli.DEMO_PASSWORD) is not None
    assert (
        authenticate_user(db_session, "project.manager@demo.local", cli.DEMO_PASSWORD) is not None
    )


def test_seed_demo_creates_an_active_demo_project(db_session: Session) -> None:
    cli.main(["seed-demo"])
    project = db_session.scalars(select(Project).where(Project.name == cli.DEMO_PROJECT)).one()
    assert project.status is ProjectStatus.ACTIVE  # dev convenience; real projects start in Setup


@pytest.mark.parametrize("environment", [Environment.PRODUCTION, Environment.STAGING])
def test_seed_demo_is_refused_in_staging_and_production(
    environment: Environment, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Demo accounts have a published password: a staging environment is reachable too."""
    monkeypatch.setattr(cli, "get_settings", lambda: SimpleNamespace(environment=environment))
    assert cli.main(["seed-demo"]) == 1
    assert "development only" in capsys.readouterr().err


@pytest.mark.parametrize("environment", [Environment.DEVELOPMENT, Environment.TEST])
def test_seed_demo_is_allowed_in_development_and_test(
    environment: Environment, monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    monkeypatch.setattr(cli, "get_settings", lambda: SimpleNamespace(environment=environment))
    assert cli.main(["seed-demo"]) == 0
    assert db_session.scalars(select(User).where(User.email == "owner@demo.local")).one()
