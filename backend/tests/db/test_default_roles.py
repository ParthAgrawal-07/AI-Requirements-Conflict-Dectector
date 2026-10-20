"""The seeded default roles equal the constants in ``app.core.permissions``.

Migration 0004 seeds from a *frozen copy* (migrations must never change retroactively). This test
is what stops that copy and ``app.core.permissions`` from drifting apart: if someone edits the
catalogue they must also write a migration that updates the rows, or this fails.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.permissions import (
    DEFAULT_ROLE_DESCRIPTIONS,
    DEFAULT_ROLE_PERMISSIONS,
    PROTECTED_ONLY_GRANTS,
    DefaultRole,
)
from app.models import Role


def _seeded(db: Session) -> dict[str, Role]:
    roles = db.scalars(
        select(Role).where(Role.is_default).options(selectinload(Role.permissions))
    ).all()
    return {role.name: role for role in roles}


def test_exactly_the_nine_default_roles_exist(db_session: Session) -> None:
    assert set(_seeded(db_session)) == {role.value for role in DefaultRole}


def test_every_role_holds_exactly_the_documented_permissions(db_session: Session) -> None:
    seeded = _seeded(db_session)
    for role in DefaultRole:
        assert seeded[role.value].permission_names == DEFAULT_ROLE_PERMISSIONS[role], role.value


def test_descriptions_match(db_session: Session) -> None:
    seeded = _seeded(db_session)
    for role in DefaultRole:
        assert seeded[role.value].description == DEFAULT_ROLE_DESCRIPTIONS[role]


def test_protected_only_flags_match(db_session: Session) -> None:
    seeded = _seeded(db_session)
    flagged = {
        (DefaultRole(role.name), grant.permission)
        for role in seeded.values()
        for grant in role.permissions
        if grant.protected_only
    }
    assert flagged == set(PROTECTED_ONLY_GRANTS)
