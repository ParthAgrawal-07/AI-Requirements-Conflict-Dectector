"""US-03: every committed stage of document processing is announced on the event bus."""

from collections.abc import Callable

import pytest
from sqlalchemy.orm import Session

from app.models import Document
from app.realtime import bus
from app.realtime.events import ANALYSIS_PROGRESS
from app.services.processing import process_document
from app.services.storage import LocalFileStorage
from tests.factories import make_docx


@pytest.fixture
def events(monkeypatch: pytest.MonkeyPatch) -> bus.InProcessEventBus:
    test_bus = bus.InProcessEventBus()
    monkeypatch.setattr(bus, "get_bus", lambda: test_bus)
    return test_bus


def test_progress_is_announced_for_each_stage_in_order(
    db_session: Session,
    storage: LocalFileStorage,
    make_stored_document: Callable[..., Document],
    events: bus.InProcessEventBus,
) -> None:
    document = make_stored_document(make_docx("REQ-001: The system shall allow user login."))

    process_document(db_session, document.id, storage=storage)

    progress = [e.data for e in events.published if e.type == ANALYSIS_PROGRESS]
    assert [(p["status"], p["progress_percent"], p["stage"]) for p in progress] == [
        ("processing", 10, "extraction"),
        ("processing", 60, "persistence"),
        ("done", 100, None),
    ]
    assert all(e.entity_id == document.id for e in events.published)
    assert all(e.project_id == document.project_id for e in events.published)


def test_a_failure_is_announced_with_its_stage_and_reason(
    db_session: Session,
    storage: LocalFileStorage,
    make_stored_document: Callable[..., Document],
    events: bus.InProcessEventBus,
) -> None:
    document = make_stored_document(b"", write_file=False)

    process_document(db_session, document.id, storage=storage)

    last = events.published[-1].data
    assert last["status"] == "failed"
    assert last["stage"] == "storage"
    assert last["error_message"].startswith("[storage]")


def test_a_bus_outage_does_not_fail_processing(
    db_session: Session,
    storage: LocalFileStorage,
    make_stored_document: Callable[..., Document],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Broken:
        def publish(self, event: object) -> None:
            raise RuntimeError("bus down")

    monkeypatch.setattr(bus, "get_bus", lambda: Broken())
    document = make_stored_document(make_docx("REQ-001: The system shall allow user login."))

    assert process_document(db_session, document.id, storage=storage).value == "done"
