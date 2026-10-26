"""Vector store on pgvector (Heet — FR-07, FR-08, US-05 groundwork).

* :func:`embed_document` — the embedding stage after extraction: one row in ``embeddings`` per
  requirement of the document, and ``document_sections.embedding`` for its sections (the context
  pack picks the most relevant sections with them, FR-105). Idempotent: rows already embedded with
  the current model are skipped, stale ones are replaced.
* :func:`nearest_requirements` — top-*k* requirements of **one project** by cosine similarity,
  using the HNSW index (``ix_embeddings_vector_hnsw``). Project scoping is in the query, so a
  search can never return another tenant's requirement.

Embedding does not call an LLM and costs nothing per call, so it runs while a project is still in
Setup — unlike classification, which the ContextGate holds back.
"""

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.embeddings.model import Embedder
from app.models import Document, DocumentSection, Embedding, Requirement

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmbedResult:
    requirements: int  # newly embedded (or re-embedded) requirements
    sections: int


@dataclass(frozen=True)
class Neighbour:
    requirement_id: uuid.UUID
    similarity: float  # cosine similarity, -1..1 (normalised vectors: 0..1 in practice)


def embed_document(db: Session, document_id: uuid.UUID, embedder: Embedder) -> EmbedResult:
    """Embed every requirement and section of a document that lacks a current vector."""
    if db.get(Document, document_id) is None:
        logger.info("Embedding skipped: document %s no longer exists", document_id)
        return EmbedResult(0, 0)

    rows = db.execute(
        select(Requirement, Embedding)
        .outerjoin(Embedding, Embedding.requirement_id == Requirement.id)
        .where(Requirement.document_id == document_id)
        .order_by(Requirement.order_index)
    ).all()
    todo = [
        (requirement, existing)
        for requirement, existing in rows
        if existing is None or existing.model_version != embedder.version
    ]
    vectors = embedder.embed([requirement.body for requirement, _ in todo])
    for (requirement, existing), vector in zip(todo, vectors, strict=True):
        if existing is None:
            db.add(
                Embedding(
                    requirement_id=requirement.id, vector=vector, model_version=embedder.version
                )
            )
        else:
            existing.vector = vector
            existing.model_version = embedder.version

    sections = list(
        db.scalars(
            select(DocumentSection).where(
                DocumentSection.document_id == document_id, DocumentSection.embedding.is_(None)
            )
        )
    )
    section_vectors = embedder.embed([_section_text(section) for section in sections])
    for section, vector in zip(sections, section_vectors, strict=True):
        section.embedding = vector

    db.commit()
    logger.info(
        "Embedded document %s: %d requirements, %d sections", document_id, len(todo), len(sections)
    )
    return EmbedResult(requirements=len(todo), sections=len(sections))


def _section_text(section: DocumentSection) -> str:
    return f"{section.heading}\n{section.body}" if section.heading else section.body


def _configure_hnsw_scan(db: Session, ef_search: int = 100) -> None:
    """Ensure filtered HNSW searches find enough candidates across multiple tenants.

    pgvector 0.8+ supports iterative scans with ``relaxed_order`` to scan the index until
    enough matching rows are found for the tenant filter. On older pgvector versions, we
    fall back to raising ``hnsw.ef_search``.
    """
    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        return

    try:
        with db.begin_nested():
            db.execute(text("SET LOCAL hnsw.iterative_scan = 'relaxed_order'"))
    except Exception:
        db.execute(text(f"SET LOCAL hnsw.ef_search = {ef_search}"))
    else:
        db.execute(text(f"SET LOCAL hnsw.ef_search = {ef_search}"))


def nearest_requirements(
    db: Session,
    project_id: uuid.UUID,
    vector: list[float],
    *,
    k: int = 10,
    min_similarity: float | None = None,
    exclude: set[uuid.UUID] | None = None,
) -> list[Neighbour]:
    """The ``k`` most similar requirements of ``project_id``, most similar first."""
    _configure_hnsw_scan(db, ef_search=max(40, (k + len(exclude or ())) * 5, 100))
    distance = Embedding.vector.cosine_distance(vector)
    query = (
        select(Embedding.requirement_id, distance.label("distance"))
        .join(Requirement, Requirement.id == Embedding.requirement_id)
        .where(Requirement.project_id == project_id)
        .order_by(distance)
        .limit(k + len(exclude or ()))
    )
    if min_similarity is not None:
        query = query.where(distance <= 1 - min_similarity)
    neighbours = [
        Neighbour(requirement_id=row.requirement_id, similarity=1 - float(row.distance))
        for row in db.execute(query)
        if not exclude or row.requirement_id not in exclude
    ]
    return neighbours[:k]


def nearest_sections(
    db: Session, project_id: uuid.UUID, vector: list[float], *, k: int = 3
) -> list[DocumentSection]:
    """The ``k`` sections of the project's documents closest to ``vector`` (context pack)."""
    _configure_hnsw_scan(db, ef_search=max(40, k * 5, 100))
    distance = DocumentSection.embedding.cosine_distance(vector)
    return list(
        db.scalars(
            select(DocumentSection)
            .where(DocumentSection.project_id == project_id, DocumentSection.embedding.is_not(None))
            .order_by(distance)
            .limit(k)
        )
    )
