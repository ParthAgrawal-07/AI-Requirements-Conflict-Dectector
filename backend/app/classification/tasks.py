"""Classification of one candidate pair as a Celery task (Keval — Sprint 1 skeleton).

``classify_pair`` loads the pair, refuses while the project is in Setup (ContextGate, FR-103),
builds the context pack, asks the classifier and stores a ``Finding`` when there is an issue, with
the context version it was given (FR-105) and the verbatim model output (FR-20). Running it twice
for the same pair is harmless: an existing finding for the pair is left as it is.

Retries: an unavailable provider is retried with exponential backoff (the SDK has already retried
the individual HTTP call); an invalid reply, a refusal or an exhausted budget are not — they are
logged and the pair is left unclassified for the orchestrator (Sprint 2) to report.
"""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.classification.budget import BudgetExceededError
from app.classification.classifier import Classifier, as_input
from app.classification.context_pack import ContextPackBuilder
from app.classification.llm_client import (
    LLMClient,
    LLMError,
    LLMUnavailableError,
    get_llm_client,
)
from app.context import service as context_service
from app.core.celery_app import celery_app
from app.core.database import session_scope
from app.core.errors import AppError
from app.models import CandidatePair, Finding, FindingCategory, Project, Requirement

logger = logging.getLogger(__name__)


def classify_candidate_pair(db: Session, pair_id: uuid.UUID, llm: LLMClient) -> Finding | None:
    """Classify one pair; returns the new finding, or ``None`` (no issue, or already done)."""
    pair = db.get(CandidatePair, pair_id)
    if pair is None:
        return None
    if db.scalar(select(Finding.id).where(Finding.candidate_pair_id == pair.id)) is not None:
        return None
    a = db.get(Requirement, pair.requirement_a_id)
    b = db.get(Requirement, pair.requirement_b_id)
    if a is None or b is None:
        return None
    project = db.get(Project, a.project_id)
    if project is None:
        return None
    context_service.ensure_analysis_allowed(db, project)  # 409 project_in_setup in Setup

    vector = a.embedding.vector if a.embedding else (b.embedding.vector if b.embedding else None)
    pack = ContextPackBuilder(db).build(
        project, query_text=f"{a.body}\n{b.body}", query_vector=vector
    )
    output = Classifier(llm).classify_pair(
        as_input(a), as_input(b), pack=pack, project_id=project.id
    )
    if not output.is_issue:
        return None
    finding = Finding(
        document_id=a.document_id,
        candidate_pair_id=pair.id,
        category=FindingCategory(output.category),
        confidence=output.confidence,
        rationale=output.rationale,
        original_ai_output=output.model_dump(mode="json"),
        context_version=pack.context_version,
    )
    db.add(finding)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        logger.info("Finding for pair %s already exists (concurrent insert)", pair.id)
        return None
    return finding


@celery_app.task(
    name="classification.classify_pair",
    bind=True,
    autoretry_for=(LLMUnavailableError,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=5,
)
def classify_pair_task(self: object, pair_id: str) -> str | None:
    """Returns the finding id, or ``None``."""
    llm = get_llm_client()
    if llm is None:
        logger.warning("Pair %s not classified: no LLM is configured", pair_id)
        return None
    with session_scope() as db:
        try:
            finding = classify_candidate_pair(db, uuid.UUID(pair_id), llm)
        except LLMUnavailableError:
            raise
        except (LLMError, BudgetExceededError, AppError) as exc:
            logger.warning("Pair %s not classified: %s", pair_id, exc)
            return None
        return str(finding.id) if finding else None
