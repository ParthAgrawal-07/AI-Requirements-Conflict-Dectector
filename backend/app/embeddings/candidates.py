"""Candidate pairs (Heet — US-05 task 5a groundwork, FR-09, FR-10).

The embedding pre-filter decides which pairs are worth an LLM call: for each requirement in scope,
its top-*k* neighbours in the same project whose cosine similarity is at least the project's
``similarity_threshold``. Similarity only *selects* pairs — it never decides a category (US-05).

Pairs are stored once in canonical order with their classification status (gap G1):

* a new pair is ``pending``;
* a pair already classified (``done``) for the **same requirement versions** is left alone —
  nobody pays twice for an unchanged pair;
* a pair whose requirements changed since, or that ``failed`` before, goes back to ``pending``.

Rejected and Deprecated requirements are not paired. :func:`generate_candidates` returns the ids
of the pending pairs, which the orchestrator hands to the classifier.

Recall matters more than precision here (the headline number, US-05): a conflict that never
becomes a candidate can never be found. ``eval/run_benchmark.py`` reports candidate recall on the
labelled pairs; planted conflicts below the threshold are what US-58's rule checks complement.
"""

import logging
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.embeddings.store import configure_hnsw_scan, nearest_requirements
from app.models import (
    CandidatePair,
    ClassificationStatus,
    Embedding,
    Project,
    Requirement,
    RequirementState,
)

logger = logging.getLogger(__name__)

EXCLUDED_STATES = (RequirementState.REJECTED, RequirementState.DEPRECATED)


@dataclass
class CandidateResult:
    pending: list[uuid.UUID] = field(default_factory=list)  # to classify, in creation order
    created: int = 0
    reopened: int = 0  # requirements changed since they were classified, or a failure to retry
    unchanged: int = 0  # already classified for the current versions


def generate_candidates(
    db: Session,
    project_id: uuid.UUID,
    *,
    requirement_ids: list[uuid.UUID] | None = None,
    k: int | None = None,
    threshold: float | None = None,
) -> CandidateResult:
    """Pair each requirement in scope (default: the whole project) with its nearest neighbours.

    ``k`` defaults to ``CANDIDATE_TOP_K``; ``threshold`` to the project's similarity threshold.
    Commits once at the end.
    """
    project = db.get(Project, project_id)
    if project is None:
        return CandidateResult()
    k = k or get_settings().candidate_top_k
    min_similarity = project.similarity_threshold if threshold is None else threshold

    query = (
        select(Requirement.id, Embedding.vector)
        .join(Embedding, Embedding.requirement_id == Requirement.id)
        .where(Requirement.project_id == project_id, Requirement.state.not_in(EXCLUDED_STATES))
        .order_by(Requirement.order_index, Requirement.id)
    )
    if requirement_ids is not None:
        query = query.where(Requirement.id.in_(requirement_ids))
    sources = db.execute(query).all()
    if not sources:
        return CandidateResult()

    # Configure HNSW scan once for the entire candidate generation run instead of
    # repeating SET LOCAL on every source requirement (reduces round-trips).
    configure_hnsw_scan(db, ef_search=max(40, (k + 1) * 5, 100))

    eligible = set(
        db.scalars(
            select(Requirement.id).where(
                Requirement.project_id == project_id, Requirement.state.not_in(EXCLUDED_STATES)
            )
        )
    )
    versions = {
        row.id: row.current_version
        for row in db.execute(
            select(Requirement.id, Requirement.current_version).where(
                Requirement.project_id == project_id
            )
        )
    }

    best: dict[tuple[uuid.UUID, uuid.UUID], float] = {}
    for requirement_id, vector in sources:
        for neighbour in nearest_requirements(
            db,
            project_id,
            list(vector),
            k=k,
            min_similarity=min_similarity,
            exclude={requirement_id},
            excluded_states=EXCLUDED_STATES,
            configure_hnsw=False,
        ):
            if neighbour.requirement_id not in eligible:
                continue
            key = CandidatePair.ordered(requirement_id, neighbour.requirement_id)
            best[key] = max(best.get(key, -1.0), neighbour.similarity)

    result = CandidateResult()
    if not best:
        return result

    existing = {
        (pair.requirement_a_id, pair.requirement_b_id): pair
        for pair in db.scalars(
            select(CandidatePair).where(
                CandidatePair.requirement_a_id.in_([a for a, _ in best]),
            )
        )
        if (pair.requirement_a_id, pair.requirement_b_id) in best
    }

    new_pairs: list[CandidatePair] = []
    pending_pairs: list[CandidatePair] = []

    for (a, b), similarity in best.items():
        similarity = min(1.0, max(-1.0, similarity))  # float noise on identical vectors
        pair = existing.get((a, b))
        if pair is None:
            pair = CandidatePair(
                requirement_a_id=a, requirement_b_id=b, similarity_score=similarity
            )
            new_pairs.append(pair)
            pending_pairs.append(pair)
            continue
        pair.similarity_score = similarity
        current = (versions.get(a), versions.get(b))
        if pair.classification_status is ClassificationStatus.DONE:
            if (pair.a_version, pair.b_version) == current:
                result.unchanged += 1
                continue
            if pair.a_version is None and pair.b_version is None:
                # Pairs from Sprint 1 backfilled as done without versions: stamp
                # current versions so they stay done and are not sent to the LLM again.
                pair.a_version, pair.b_version = current
                result.unchanged += 1
                continue
        if pair.classification_status is not ClassificationStatus.PENDING:
            pair.classification_status = ClassificationStatus.PENDING
            pair.attempts = 0
            pair.last_error = None
            result.reopened += 1
        pending_pairs.append(pair)

    if new_pairs:
        db.add_all(new_pairs)
        result.created = len(new_pairs)

    db.flush()
    result.pending = [p.id for p in pending_pairs]
    db.commit()
    logger.info(
        "Candidates for project %s: %d new, %d reopened, %d unchanged",
        project_id,
        result.created,
        result.reopened,
        result.unchanged,
    )
    return result
