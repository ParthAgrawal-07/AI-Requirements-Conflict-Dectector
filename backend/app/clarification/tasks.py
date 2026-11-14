"""Clarification tasks (Madhav — US-09, FR-22; design update §3.1).

``clarifications.generate_for_run`` runs after an analysis run closes (queued by
``analysis.after_run``): one question per Conflicting, Ambiguous and Incomplete finding of the run
(``app.clarification.generator``). For a **posted** requirement the question is then posted as a
reply in its thread, @mentioning the owners of the requirements involved (US-36), and the result
card is rewritten to show it (US-31). Findings about extracted requirements have no thread: the
question shows on the finding card; for a conflict issue it becomes the first comment (S4).

An exhausted budget stops the batch (the rest wait for the next run or a manual request); a
model that keeps answering invalid or generic output skips that finding. An unavailable provider
retries the task with backoff. ``clarifications.generate_for_finding`` does the same for one
finding on request (``POST /findings/{id}/clarification``).
"""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clarification.generator import generate, needs_question
from app.classification.budget import BudgetExceededError
from app.classification.llm_client import (
    LLMClient,
    LLMOutputError,
    LLMRefusedError,
    LLMUnavailableError,
    get_llm_client,
)
from app.core.celery_app import celery_app
from app.core.database import session_scope
from app.graph.deltas import label_of
from app.models import (
    AnalysisRun,
    AnalysisScope,
    Channel,
    Clarification,
    Finding,
    Message,
    MessageKind,
)
from app.services import messages as message_service
from app.services.review_state import involved_requirements

logger = logging.getLogger(__name__)

GENERATE_FOR_RUN = "clarifications.generate_for_run"
GENERATE_FOR_FINDING = "clarifications.generate_for_finding"


def questions_for_run(db: Session, run_id: uuid.UUID, llm: LLMClient) -> list[Clarification]:
    run = db.get(AnalysisRun, run_id)
    if run is None:
        return []
    findings = [
        f
        for f in db.scalars(
            select(Finding)
            .where(Finding.analysis_run_id == run.id)
            .order_by(Finding.confidence.desc(), Finding.created_at)
        )
        if needs_question(f)
    ]
    created: list[Clarification] = []
    for finding in findings:
        try:
            clarification = _question(db, llm, finding)
        except BudgetExceededError:
            logger.info("Clarifications for project %s wait for budget", finding.project_id)
            break
        if clarification is not None:
            created.append(clarification)
    if created and run.scope is AnalysisScope.REQUIREMENT:
        from app.classification.result_card import publish_card

        publish_card(db, run)
    return created


def question_for_finding(
    db: Session, finding_id: uuid.UUID, llm: LLMClient
) -> Clarification | None:
    finding = db.get(Finding, finding_id)
    if finding is None:
        return None
    try:
        return _question(db, llm, finding)
    except BudgetExceededError:
        return None


def _question(db: Session, llm: LLMClient, finding: Finding) -> Clarification | None:
    """Generate (or find) the finding's question and post it once. Raises
    :class:`BudgetExceededError` (after rolling back) so a batch can stop."""
    already = finding.clarification
    try:
        clarification = generate(db, llm, finding)
    except BudgetExceededError:
        db.rollback()
        raise
    except (LLMOutputError, LLMRefusedError) as error:
        db.rollback()
        logger.warning("No clarification for finding %s: %s", finding.id, type(error).__name__)
        return None
    if clarification is not None and already is None and clarification.message_id is None:
        post_in_thread(db, clarification, finding)
    return clarification


def post_in_thread(db: Session, clarification: Clarification, finding: Finding) -> Message | None:
    """Reply in the thread of the posted requirement the finding is about, mentioning owners."""
    requirements = involved_requirements(db, finding)
    posted = next((r for r in requirements if r.origin_message_id is not None), None)
    if posted is None or posted.origin_message_id is None:
        return None
    root = db.get(Message, posted.origin_message_id)
    channel = db.get(Channel, root.channel_id) if root is not None else None
    if root is None or channel is None:
        return None
    owners: list[uuid.UUID] = []
    for requirement in requirements:
        if requirement.owner_id is not None and requirement.owner_id not in owners:
            owners.append(requirement.owner_id)
    names = " and ".join(label_of(r) for r in requirements)
    mentions = " ".join(f"<@{owner}>" for owner in owners)
    body = f"Clarification needed on {names} ({finding.category.value}): {clarification.question}"
    message = message_service.post_system_message(
        db,
        channel=channel,
        body=f"{body} {mentions}".strip(),
        kind=MessageKind.SYSTEM,
        parent_id=root.id,
        payload={"clarification_id": str(clarification.id), "finding_id": str(finding.id)},
    )
    clarification.message_id = message.id
    db.commit()
    return message


@celery_app.task(
    name=GENERATE_FOR_RUN,
    autoretry_for=(LLMUnavailableError,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=5,
)
def generate_for_run_task(run_id: str) -> int:
    llm = get_llm_client()
    if llm is None:
        return 0
    with session_scope() as db:
        return len(questions_for_run(db, uuid.UUID(run_id), llm))


@celery_app.task(
    name=GENERATE_FOR_FINDING,
    autoretry_for=(LLMUnavailableError,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=5,
)
def generate_for_finding_task(finding_id: str) -> str | None:
    llm = get_llm_client()
    if llm is None:
        return None
    with session_scope() as db:
        clarification = question_for_finding(db, uuid.UUID(finding_id), llm)
        return str(clarification.id) if clarification else None
