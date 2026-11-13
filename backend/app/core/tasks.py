"""Celery tasks owned by Role 5 (orchestration)."""

import logging
import uuid

from celery import Task

from app.core.celery_app import celery_app
from app.core.database import session_scope
from app.core.errors import AppError

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
        dispatch_analysis(document_id)
    return outcome.value


def dispatch_analysis(document_id: str) -> None:
    """Queue the analysis of a processed document: embedding, candidates, classification
    (``app.services.analysis_orchestrator``). By task name, so this module never imports the model
    stack. Best effort: the document is already ``done``, and the analysis can be re-run."""
    try:
        celery_app.send_task("analysis.run_document", args=[document_id], retry=False)
    except Exception:
        logger.warning("Could not queue analysis of document %s", document_id, exc_info=True)


@celery_app.task(name="join_codes.expire")
def expire_join_codes_task() -> list[int]:
    """Mark expired join codes and 14-day-old join requests (US-25; scheduled by Celery beat)."""
    from app.services.join_codes import expire_stale

    with session_scope() as db:
        return list(expire_stale(db))


# ── Analysis (Parth — orchestration of Heet's and Keval's stages, US-05) ───────────────────
@celery_app.task(name="analysis.run_document")
def run_document_task(document_id: str) -> str | None:
    """Embed a processed document, then (once the project is active) find candidate pairs and fan
    out their classification. Returns the analysis run id, or ``None`` while in Setup."""
    from app.classification.llm_client import get_llm_client
    from app.embeddings.model import get_embedder
    from app.embeddings.store import embed_document
    from app.services.analysis_orchestrator import start_document_run

    with session_scope() as db:
        embed_document(db, uuid.UUID(document_id), get_embedder())
        run = start_document_run(
            db, uuid.UUID(document_id), llm_configured=get_llm_client() is not None
        )
        return str(run.id) if run else None


def _backoff(retries: int) -> int:
    return int(min(300, 10 * 2**retries))


@celery_app.task(name="analysis.classify_pair", bind=True, max_retries=5)
def classify_pair_in_run_task(self: Task, run_id: str, pair_id: str) -> str:
    """Classify one pair of a run and count it (done, failed or waiting for budget)."""
    from app.classification.budget import BudgetExceededError
    from app.classification.llm_client import LLMUnavailableError, get_llm_client
    from app.classification.tasks import classify_candidate_pair
    from app.models import CandidatePair, ClassificationStatus
    from app.services import analysis_orchestrator as orchestrator

    llm = get_llm_client()
    with session_scope() as db:
        try:
            if llm is not None:
                classify_candidate_pair(db, uuid.UUID(pair_id), llm, run_id=uuid.UUID(run_id))
        except LLMUnavailableError as exc:
            if self.request.retries < (self.max_retries or 0):
                raise self.retry(exc=exc, countdown=_backoff(self.request.retries)) from exc
            db.rollback()
            pair = db.get(CandidatePair, uuid.UUID(pair_id))
            if pair is not None:  # gave up: recorded, never dropped (G1)
                pair.classification_status = ClassificationStatus.FAILED
                pair.last_error = "provider_unavailable"
                db.commit()
        except BudgetExceededError:
            db.rollback()
        except AppError:  # e.g. the project went back to Setup
            db.rollback()
        outcome = orchestrator.pair_outcome(db, uuid.UUID(pair_id))
        orchestrator.record(db, uuid.UUID(run_id), "pair", outcome)
        return outcome


@celery_app.task(name="analysis.check_requirement", bind=True, max_retries=5)
def check_requirement_in_run_task(self: Task, run_id: str, requirement_id: str) -> str:
    """Check one requirement of a run for Ambiguous / Incomplete and count it."""
    from app.classification.budget import BudgetExceededError
    from app.classification.llm_client import LLMUnavailableError, get_llm_client
    from app.classification.tasks import classify_requirement
    from app.services import analysis_orchestrator as orchestrator

    llm = get_llm_client()
    budget = False
    with session_scope() as db:
        try:
            if llm is not None:
                classify_requirement(db, uuid.UUID(requirement_id), llm, run_id=uuid.UUID(run_id))
        except LLMUnavailableError as exc:
            if self.request.retries < (self.max_retries or 0):
                raise self.retry(exc=exc, countdown=_backoff(self.request.retries)) from exc
            db.rollback()
        except BudgetExceededError:
            db.rollback()
            budget = True
        except AppError:
            db.rollback()
        outcome = "budget" if budget else orchestrator.check_outcome(db, uuid.UUID(requirement_id))
        orchestrator.record(db, uuid.UUID(run_id), "check", outcome)
        return outcome
