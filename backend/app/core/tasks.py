"""Celery tasks owned by Role 5 (orchestration)."""

import logging
import uuid

from app.core.celery_app import celery_app
from app.core.database import session_scope

logger = logging.getLogger(__name__)


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
    from app.services.processing import ProcessingOutcome, process_document

    with session_scope() as db:
        outcome = process_document(db, uuid.UUID(document_id))
    if outcome is ProcessingOutcome.DONE:
        dispatch_embedding(document_id)
    return outcome.value


def dispatch_embedding(document_id: str) -> None:
    """Queue the embedding stage (Heet). By task name, so this module never imports the model
    stack. Best effort: the document is already ``done``, and embedding can be re-run."""
    try:
        celery_app.send_task("embeddings.embed_document", args=[document_id], retry=False)
    except Exception:
        logger.warning("Could not queue embedding of document %s", document_id, exc_info=True)
