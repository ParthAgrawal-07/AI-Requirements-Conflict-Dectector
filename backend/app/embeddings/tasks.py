"""Celery tasks of the embedding stage and of candidate pairs (Heet), on the ``analysis`` queue."""

import uuid

from sqlalchemy import select

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


@celery_app.task(name="embeddings.generate_candidates")
def generate_candidates_task(document_id: str) -> list[str]:
    """Candidate pairs for a document's requirements against its project; returns pending ids."""
    from app.embeddings.candidates import generate_candidates
    from app.models import Document, Requirement

    with session_scope() as db:
        document = db.get(Document, uuid.UUID(document_id))
        if document is None:
            return []
        requirement_ids = list(
            db.scalars(select(Requirement.id).where(Requirement.document_id == document.id))
        )
        result = generate_candidates(db, document.project_id, requirement_ids=requirement_ids)
        return [str(pair_id) for pair_id in result.pending]
