"""``session_scope`` transaction semantics, checked against a real (scratch) database."""

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core import database
from app.models import Workspace


@pytest.fixture
def scoped(scratch_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Engine:
    Workspace.__table__.create(scratch_engine)  # only this table: no pgvector needed here
    factory = sessionmaker(bind=scratch_engine, expire_on_commit=False)
    monkeypatch.setattr(database, "get_sessionmaker", lambda: factory)
    return scratch_engine


def _count(engine: Engine) -> int:
    with Session(engine) as session:
        return session.scalar(select(func.count()).select_from(Workspace)) or 0


def test_session_scope_commits_on_success(scoped: Engine) -> None:
    with database.session_scope() as db:
        db.add(Workspace(name="kept"))
    assert _count(scoped) == 1


def test_session_scope_rolls_back_on_error(scoped: Engine) -> None:
    with pytest.raises(RuntimeError), database.session_scope() as db:
        db.add(Workspace(name="discarded"))
        db.flush()
        raise RuntimeError("boom")
    assert _count(scoped) == 0
