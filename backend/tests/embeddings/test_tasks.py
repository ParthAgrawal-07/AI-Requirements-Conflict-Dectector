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


def test_a_done_document_queues_its_embedding(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[tuple[str, list[str]]] = []

    def record(name: str, args: list[str], **_: object) -> None:
        sent.append((name, args))

    monkeypatch.setattr(celery_app, "send_task", record)
    document_id = str(uuid.uuid4())

    tasks.dispatch_embedding(document_id)

    assert sent == [("embeddings.embed_document", [document_id])]


def test_a_broker_outage_does_not_fail_the_extraction_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def down(*_: object, **__: object) -> None:
        raise ConnectionError("broker down")

    monkeypatch.setattr(celery_app, "send_task", down)

    tasks.dispatch_embedding(str(uuid.uuid4()))  # logs, does not raise
