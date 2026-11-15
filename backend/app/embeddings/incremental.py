"""Incremental retrieval for one requirement or one draft (Heet — US-31, FR-56, FR-83; ADR-16).

The retrieval half of ``IncrementalAnalyzer`` (``app.embeddings.contract``): everything up to,
but not including, the LLM. Used by

* a **posted requirement** (US-31): :func:`candidates_for_requirement` embeds it and pairs it with
  its top-*k* neighbours among the project's Approved/Implemented baseline and open proposals —
  the same pre-filter as document analysis (FR-56), never the whole project (SX-16);
* the composer's **similar requirements** panel (US-51, FR-83): :func:`similar_to_text` embeds a
  draft that is not stored anywhere and returns the closest requirements. Embedding only, no LLM.

Rejected and Deprecated requirements are never neighbours: they are filtered inside the vector
query, so a project full of rejected look-alikes still yields ``k`` real neighbours.

Posted requirements have no document, so ``embed_document`` never sees them;
:func:`embed_requirements` embeds any requirement by id, with the same idempotency rule (skip a
current vector, replace one from an older model).
"""

import logging
import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.embeddings.candidates import EXCLUDED_STATES, CandidateResult, generate_candidates
from app.embeddings.contract import SimilarHint
from app.embeddings.model import Embedder
from app.embeddings.store import nearest_requirements
from app.models import Embedding, Requirement

logger = logging.getLogger(__name__)

MAX_HINTS = 10


def embed_requirements(
    db: Session, requirement_ids: Sequence[uuid.UUID], embedder: Embedder
) -> int:
    """Embed the given requirements that lack a current vector; returns how many were embedded."""
    if not requirement_ids:
        return 0
    rows = db.execute(
        select(Requirement, Embedding)
        .outerjoin(Embedding, Embedding.requirement_id == Requirement.id)
        .where(Requirement.id.in_(list(requirement_ids)))
    ).all()
    todo = [
        (requirement, existing)
        for requirement, existing in rows
        if existing is None or existing.model_version != embedder.version
    ]
    if not todo:
        return 0
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
    db.commit()
    return len(todo)


def candidates_for_requirement(
    db: Session, requirement: Requirement, embedder: Embedder, *, k: int | None = None
) -> CandidateResult:
    """Embed one requirement and pair it with its nearest neighbours in its project.

    Unchanged pairs already classified are not returned as pending (G1), so analysing the same
    text twice costs nothing the second time.
    """
    embed_requirements(db, [requirement.id], embedder)
    if requirement.state in EXCLUDED_STATES:
        return CandidateResult()
    return generate_candidates(db, requirement.project_id, requirement_ids=[requirement.id], k=k)


def similar_to_text(
    db: Session,
    project_id: uuid.UUID,
    text: str,
    embedder: Embedder,
    *,
    k: int = 3,
    min_similarity: float | None = None,
    exclude: set[uuid.UUID] | None = None,
) -> list[SimilarHint]:
    """The ``k`` requirements of the project most similar to ``text``, most similar first.

    Nothing is stored. ``min_similarity`` defaults to ``SIMILAR_HINT_MIN_SIMILARITY``.
    """
    if not text.strip():
        return []
    floor = get_settings().similar_hint_min_similarity if min_similarity is None else min_similarity
    vector = embedder.embed([text])[0]
    neighbours = nearest_requirements(
        db,
        project_id,
        vector,
        k=min(k, MAX_HINTS),
        min_similarity=floor,
        exclude=exclude,
        exclude_states=EXCLUDED_STATES,
    )
    # ``.all()``: a Result has ``keys()``, so ``dict(result)`` would treat it as a mapping.
    labels: dict[uuid.UUID, str | None] = dict(
        db.execute(
            select(Requirement.id, Requirement.source_req_id).where(
                Requirement.id.in_([n.requirement_id for n in neighbours])
            )
        )
        .tuples()
        .all()
    )
    return [
        SimilarHint(
            requirement_id=n.requirement_id,
            label=labels.get(n.requirement_id),
            similarity=min(1.0, max(-1.0, n.similarity)),
        )
        for n in neighbours
    ]
