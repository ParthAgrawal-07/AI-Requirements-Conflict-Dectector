"""Suggestion tasks (Madhav — US-45, NFR-36; design update §3.7).

``suggestions.generate`` runs on its own ``suggestions`` queue, so options never delay findings,
the map or the result card. ``after_run`` queues one per new finding of a closed analysis run
(the finding is already committed and on the map); opening a finding without a suggestion queues
one too, which covers rule and person findings and anything parked for budget.
"""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.classification.llm_client import LLMUnavailableError, get_llm_client
from app.core.celery_app import celery_app
from app.core.database import session_scope
from app.models import AnalysisRun, Finding
from app.suggestions import service

logger = logging.getLogger(__name__)


def enqueue(suggestion_id: uuid.UUID) -> None:
    from app.services import analysis_orchestrator

    # The orchestrator's ``send`` (looked up now): tests record it instead of needing a broker.
    analysis_orchestrator.send(service.GENERATE, [str(suggestion_id)])


def for_run(db: Session, run: AnalysisRun) -> list[uuid.UUID]:
    """Request a suggestion for every live finding of the run; returns those queued."""
    findings = db.scalars(
        select(Finding)
        .where(Finding.analysis_run_id == run.id, ~Finding.is_stale)
        .order_by(Finding.created_at, Finding.id)
    ).all()
    queued: list[uuid.UUID] = []
    for finding in findings:
        suggestion, created = service.request(db, finding)
        if created:
            queued.append(suggestion.id)
    for suggestion_id in queued:
        enqueue(suggestion_id)
    return queued


@celery_app.task(
    name=service.GENERATE,
    autoretry_for=(LLMUnavailableError,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=5,
)
def generate_task(suggestion_id: str) -> str | None:
    llm = get_llm_client()
    if llm is None:
        logger.info("No LLM configured: suggestion %s stays pending", suggestion_id)
        return None
    with session_scope() as db:
        row = service.generate(db, uuid.UUID(suggestion_id), llm)
        return row.status if row else None
