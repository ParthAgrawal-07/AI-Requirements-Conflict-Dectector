"""Celery tasks owned by Role 5 (orchestration)."""

import uuid

from app.core.celery_app import celery_app
from app.core.database import session_scope


@celery_app.task(name="system.ping")
def ping() -> str:
    """Round-trips API -> Redis -> worker; used by the smoke test to prove the queue works."""
    return "pong"


@celery_app.task(name="documents.process")
def process_document_task(document_id: str) -> str:
    """Extract and persist the requirements of an uploaded document (US-01 -> US-02 -> US-04).

    Takes the id as a string because task arguments travel as JSON. Returns the outcome
    (``done`` / ``failed`` / ``skipped``). See ``app.services.processing`` for semantics.
    """
    # Imported here so the API process, which only *sends* this task, never loads the PDF/DOCX
    # parsing stack.
    from app.services.processing import process_document

    with session_scope() as db:
        return process_document(db, uuid.UUID(document_id)).value
