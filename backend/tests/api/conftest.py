"""Fixtures shared by the document API tests."""

import uuid
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core import security
from app.models import Role, User
from app.services import documents as document_service
from app.services.storage import LocalFileStorage, get_storage

DOCUMENTS = "/api/v1/documents"


@pytest.fixture
def storage(tmp_path: Path) -> LocalFileStorage:
    return LocalFileStorage(tmp_path / "uploads")


@pytest.fixture
def dispatched(monkeypatch: pytest.MonkeyPatch) -> list[uuid.UUID]:
    """Replaces the Celery hand-off with a recorder, so no broker is needed."""
    calls: list[uuid.UUID] = []

    def fake_dispatch(document_id: uuid.UUID) -> str:
        calls.append(document_id)
        return f"task-{len(calls)}"

    monkeypatch.setattr(document_service, "dispatch_processing", fake_dispatch)
    return calls


@pytest.fixture
def api(
    client: TestClient, storage: LocalFileStorage, dispatched: list[uuid.UUID]
) -> Iterator[TestClient]:
    """The app client with uploads going to a temp dir and no real job queue."""
    from app.main import app

    app.dependency_overrides[get_storage] = lambda: storage
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_storage, None)


def headers_for(user: User) -> dict[str, str]:
    token, _ = security.create_access_token(user.id)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def as_role(make_user: Callable[..., User]) -> Callable[[Role], dict[str, str]]:
    """Auth headers for a fresh user with the given role, in the default test workspace."""

    def build(role: Role) -> dict[str, str]:
        return headers_for(make_user(role=role))

    return build


def stored_files(storage: LocalFileStorage) -> list[Path]:
    """Every file left under the storage root (including staging)."""
    return (
        [path for path in storage.root.rglob("*") if path.is_file()]
        if storage.root.exists()
        else []
    )
