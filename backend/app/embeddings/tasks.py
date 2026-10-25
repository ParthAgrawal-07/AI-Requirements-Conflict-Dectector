"""Celery tasks of the embedding stage (Heet). Routed to the ``analysis`` queue."""

import uuid

from app.core.celery_app import celery_app
from app.core.database import session_scope


@celery_app.task(
    name="embeddings.embed_document",
    autoretry_for=(OSError,),  # model download / file system hiccups; data errors are not retried
    retry_backoff=True,
    max_retries=3,
)
def embed_document_task(document_id: str) -> int:
    """Embed a processed document's requirements and sections; returns how many requirements."""
    from app.embeddings.model import get_embedder
    from app.embeddings.store import embed_document

    with session_scope() as db:
        return embed_document(db, uuid.UUID(document_id), get_embedder()).requirements
