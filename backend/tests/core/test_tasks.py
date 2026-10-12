"""The Celery side of document processing: dispatch, task wiring, and the whole flow end to end."""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core import tasks
from app.core.celery_app import celery_app
from app.core.tasks import process_document_task
from app.models import Document, DocumentStatus
from app.services import documents as document_service
from app.services import processing
from app.services.processing import ProcessingOutcome
from app.services.storage import LocalFileStorage, get_storage
from tests.api.conftest import DOCUMENTS
from tests.factories import make_docx


@pytest.fixture
def storage(tmp_path: Path) -> LocalFileStorage:
    return LocalFileStorage(tmp_path / "uploads")


@pytest.fixture
def worker_uses_test_session(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    """The task opens its own session; point it at the rolled-back test transaction instead."""

    @contextmanager
    def scope() -> Iterator[Session]:
        yield db_session

    monkeypatch.setattr(tasks, "session_scope", scope)


def test_dispatch_sends_the_document_id_as_a_string_and_returns_the_task_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[tuple[object, ...]] = []

    def fake_delay(*args: object) -> SimpleNamespace:
        sent.append(args)
        return SimpleNamespace(id="abc-123")

    monkeypatch.setattr(process_document_task, "delay", fake_delay)
    document_id = uuid.uuid4()

    assert document_service.dispatch_processing(document_id) == "abc-123"
    assert sent == [(str(document_id),)]  # JSON-serialisable: a str, not a UUID


def test_the_task_is_registered_under_a_stable_name() -> None:
    assert process_document_task.name == "documents.process"
    assert "documents.process" in celery_app.tasks


def test_task_parses_the_id_runs_the_service_and_returns_the_outcome(
    worker_uses_test_session: None, monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    calls: list[tuple[Session, uuid.UUID]] = []

    def fake_process(db: Session, document_id: uuid.UUID) -> ProcessingOutcome:
        calls.append((db, document_id))
        return ProcessingOutcome.DONE

    monkeypatch.setattr(processing, "process_document", fake_process)
    document_id = uuid.uuid4()

    assert process_document_task(str(document_id)) == "done"
    assert calls == [(db_session, document_id)]


@pytest.fixture
def eager_celery(monkeypatch: pytest.MonkeyPatch, storage: LocalFileStorage) -> None:
    """Run tasks synchronously in-process, with the worker reading the same temp storage."""
    monkeypatch.setattr(celery_app.conf, "task_always_eager", True)
    monkeypatch.setattr(celery_app.conf, "task_eager_propagates", True)
    monkeypatch.setattr(processing, "get_storage", lambda: storage)


def test_upload_to_requirement_list_end_to_end(
    client: TestClient,
    storage: LocalFileStorage,
    auth_headers: dict[str, str],
    worker_uses_test_session: None,
    eager_celery: None,
    db_session: Session,
) -> None:
    """US-01 -> US-02 -> US-04 through the real HTTP API, real task, real parsing, real database."""
    from app.main import app

    app.dependency_overrides[get_storage] = lambda: storage
    try:
        docx = make_docx(
            "REQ-001: The system shall allow user login.",
            "REQ-002: The system shall support logout.",
            "Customers may request a refund within 30 days.",
        )
        upload = client.post(
            DOCUMENTS,
            files={"file": ("srs.docx", docx, "application/octet-stream")},
            headers=auth_headers,
        )
        assert upload.status_code == 202
        document_id = upload.json()["document_id"]

        document = client.get(f"{DOCUMENTS}/{document_id}", headers=auth_headers).json()
        assert document["status"] == "done"
        assert document["progress_percent"] == 100
        assert document["requirement_count"] == 3

        listing = client.get(f"{DOCUMENTS}/{document_id}/requirements", headers=auth_headers).json()
        assert [(r["source_req_id"], r["body"]) for r in listing["items"]] == [
            ("REQ-001", "REQ-001: The system shall allow user login."),
            ("REQ-002", "REQ-002: The system shall support logout."),
            (None, "Customers may request a refund within 30 days."),
        ]
        found = client.get(
            f"{DOCUMENTS}/{document_id}/requirements", params={"q": "refund"}, headers=auth_headers
        ).json()
        assert found["total"] == 1

        stored = db_session.get(Document, uuid.UUID(document_id))
        assert stored is not None and stored.task_id  # the task id was recorded on the row
    finally:
        app.dependency_overrides.pop(get_storage, None)


def test_a_document_that_cannot_be_read_ends_failed_with_a_reason_through_the_api(
    client: TestClient,
    storage: LocalFileStorage,
    auth_headers: dict[str, str],
    worker_uses_test_session: None,
    eager_celery: None,
) -> None:
    from app.main import app

    app.dependency_overrides[get_storage] = lambda: storage
    try:
        # A valid ZIP containing the two parts upload validation looks for, but no real document.
        import io
        import zipfile

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("[Content_Types].xml", "<Types/>")
            archive.writestr("word/document.xml", "<broken")
        upload = client.post(
            DOCUMENTS,
            files={"file": ("srs.docx", buffer.getvalue(), "application/octet-stream")},
            headers=auth_headers,
        )
        assert upload.status_code == 202  # passes the cheap upload checks...

        document = client.get(
            f"{DOCUMENTS}/{upload.json()['document_id']}", headers=auth_headers
        ).json()
        assert (
            document["status"] == DocumentStatus.FAILED.value
        )  # ...and the worker says why it can't go on
        assert document["error_message"].startswith("[extraction]")
        assert document["requirement_count"] == 0
    finally:
        app.dependency_overrides.pop(get_storage, None)
