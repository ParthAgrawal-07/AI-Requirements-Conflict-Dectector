"""The embedding stage is chained after extraction and runs on the analysis queue."""

import uuid

import pytest

from app.core import tasks
from app.core.celery_app import celery_app
from app.embeddings.tasks import embed_document_task


def test_the_task_has_a_stable_name_and_goes_to_the_analysis_queue() -> None:
    assert embed_document_task.name == "embeddings.embed_document"
    route = celery_app.amqp.router.route({}, "embeddings.embed_document")
    assert route["queue"].name == "analysis"


def test_a_done_document_queues_its_analysis_which_embeds_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[tuple[str, list[str]]] = []

    def record(name: str, args: list[str], **_: object) -> None:
        sent.append((name, args))

    monkeypatch.setattr(celery_app, "send_task", record)
    document_id = str(uuid.uuid4())

    tasks.dispatch_analysis(document_id)

    assert sent == [("analysis.run_document", [document_id])]


def test_a_failed_document_does_not_queue_analysis(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failed extraction must not trigger the analysis."""
    from app.core.tasks import process_document_task
    from app.services.processing import ProcessingOutcome

    dispatched: list[str] = []
    monkeypatch.setattr(tasks, "dispatch_analysis", dispatched.append)

    class FakeSessionScope:
        def __enter__(self) -> object:
            return None

        def __exit__(self, *_: object) -> None:
            pass

    monkeypatch.setattr(tasks, "session_scope", lambda: FakeSessionScope())

    import app.services.processing as processing_mod

    monkeypatch.setattr(processing_mod, "process_document", lambda *_: ProcessingOutcome.FAILED)

    document_id = str(uuid.uuid4())
    outcome = process_document_task(document_id)

    assert outcome == ProcessingOutcome.FAILED.value
    assert dispatched == []


def test_a_skipped_document_does_not_queue_analysis(monkeypatch: pytest.MonkeyPatch) -> None:
    """A skipped extraction (e.g. duplicate hash) must not trigger the analysis."""
    from app.core.tasks import process_document_task
    from app.services.processing import ProcessingOutcome

    dispatched: list[str] = []
    monkeypatch.setattr(tasks, "dispatch_analysis", dispatched.append)

    class FakeSessionScope:
        def __enter__(self) -> object:
            return None

        def __exit__(self, *_: object) -> None:
            pass

    monkeypatch.setattr(tasks, "session_scope", lambda: FakeSessionScope())

    import app.services.processing as processing_mod

    monkeypatch.setattr(processing_mod, "process_document", lambda *_: ProcessingOutcome.SKIPPED)

    document_id = str(uuid.uuid4())
    outcome = process_document_task(document_id)

    assert outcome == ProcessingOutcome.SKIPPED.value
    assert dispatched == []


def test_a_broker_outage_does_not_fail_the_extraction_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def down(*_: object, **__: object) -> None:
        raise ConnectionError("broker down")

    monkeypatch.setattr(celery_app, "send_task", down)

    tasks.dispatch_analysis(str(uuid.uuid4()))  # logs, does not raise
