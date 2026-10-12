"""Celery tasks for ingestion (Role 1). Discovered automatically by app.core.celery_app.

The upload endpoint enqueues extraction after saving the file and the Document row::

    from app.ingestion.tasks import extract_document_task
    result = extract_document_task.delay(str(document.id))
    document.task_id = result.id
"""

import uuid

from app.core.celery_app import celery_app
from app.core.database import session_scope
from app.ingestion.service import extract_document


@celery_app.task(name="ingestion.extract_document")
def extract_document_task(document_id: str) -> str | None:
    """Extract and store requirements; returns the document's final status."""
    with session_scope() as session:
        document = extract_document(session, uuid.UUID(document_id))
        return document.status.value if document else None
