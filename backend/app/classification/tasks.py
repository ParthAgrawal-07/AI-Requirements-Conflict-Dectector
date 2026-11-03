"""Classification of candidate pairs and single requirements (Keval — US-05, US-07; G1).

``classify_candidate_pair`` (Conflicting / Duplicate / Dependent) and ``classify_requirement``
(Ambiguous / Incomplete) each:

1. lock their subject row, and skip it if it was already classified for the current requirement
   versions (no second LLM call for an unchanged pair or requirement);
2. refuse while the project is in Setup (ContextGate, FR-103);
3. build the context pack and call the classifier — re-asking up to 3 times on invalid output;
4. store a ``Finding`` when there is an issue, with its explanation and located evidence
   (US-07), the context version (FR-105), the prompt version and the verbatim model output (FR-20).

Per-pair status (gap G1): a pair ends ``done`` (with or without a finding) or ``failed`` with a
machine-readable ``last_error`` — invalid output after the retries, or a refusal — and is never
silently dropped. An unavailable provider leaves it ``pending`` and the Celery task retries with
backoff; an exhausted budget leaves it ``pending`` with ``last_error = "budget_exhausted"`` for the
orchestrator to park the run (``waiting_budget``).

A single requirement has no status row: ``requirements.single_checked_version`` records the version
checked, and stays behind on failure so the next run tries again.
"""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.classification.budget import BudgetExceededError
from app.classification.classifier import Classifier, as_input
from app.classification.context_pack import ContextPackBuilder
from app.classification.explain import Subject, explain_pair, explain_single
from app.classification.llm_client import (
    LLMClient,
    LLMError,
    LLMOutputError,
    LLMRefusedError,
    LLMUnavailableError,
    get_llm_client,
)
from app.classification.prompting import PROMPT_VERSION
from app.context import service as context_service
from app.core.celery_app import celery_app
from app.core.database import session_scope
from app.models import (
    CandidatePair,
    ClassificationStatus,
    Finding,
    FindingCategory,
    Project,
    Requirement,
    RequirementState,
)

logger = logging.getLogger(__name__)

NOT_ANALYSED = (RequirementState.REJECTED, RequirementState.DEPRECATED)


def _subject(requirement: Requirement) -> Subject:
    return Subject(id=requirement.id, label=as_input(requirement).id, text=requirement.body)


def _live_pair_finding(db: Session, pair_id: uuid.UUID) -> Finding | None:
    return db.scalar(
        select(Finding).where(Finding.candidate_pair_id == pair_id, Finding.is_stale.is_(False))
    )


def _finish(pair: CandidatePair, a: Requirement, b: Requirement) -> None:
    pair.classification_status = ClassificationStatus.DONE
    pair.attempts += 1
    pair.last_error = None
    pair.classified_at = datetime.now(UTC)
    pair.a_version, pair.b_version = a.current_version, b.current_version


def _fail(pair: CandidatePair, code: str) -> None:
    pair.classification_status = ClassificationStatus.FAILED
    pair.attempts += 1
    pair.last_error = code


def classify_candidate_pair(
    db: Session, pair_id: uuid.UUID, llm: LLMClient, *, run_id: uuid.UUID | None = None
) -> Finding | None:
    """Classify one pair; returns the new finding, or ``None`` (no issue, already classified,
    or failed — see ``pair.classification_status``)."""
    pair = db.scalar(select(CandidatePair).where(CandidatePair.id == pair_id).with_for_update())
    if pair is None:
        return None
    a = db.get(Requirement, pair.requirement_a_id)
    b = db.get(Requirement, pair.requirement_b_id)
    if a is None or b is None:
        return None
    if _live_pair_finding(db, pair.id) is not None or (
        pair.classification_status is ClassificationStatus.DONE
        and (pair.a_version, pair.b_version) == (a.current_version, b.current_version)
    ):
        if pair.classification_status is not ClassificationStatus.DONE:
            _finish(pair, a, b)  # classified before G1 existed (Sprint 1 findings)
        db.commit()
        return None
    project = db.get(Project, a.project_id)
    if project is None:
        return None
    context_service.ensure_analysis_allowed(db, project)  # 409 project_in_setup in Setup

    pack = ContextPackBuilder(db).build(project, query_text=f"{a.body}\n{b.body}")
    try:
        output = Classifier(llm).classify_pair(
            as_input(a), as_input(b), pack=pack, project_id=project.id
        )
    except LLMOutputError:
        _fail(pair, "invalid_output")
        db.commit()
        logger.warning("Pair %s failed: invalid output after retries", pair.id)
        return None
    except LLMRefusedError:
        _fail(pair, "refused")
        db.commit()
        return None
    except BudgetExceededError:
        pair.last_error = "budget_exhausted"  # stays pending
        db.commit()
        raise

    _finish(pair, a, b)
    finding: Finding | None = None
    if output.is_issue:
        explanation = explain_pair(output, _subject(a), _subject(b))
        finding = Finding(
            project_id=project.id,
            document_id=a.document_id or b.document_id,
            candidate_pair_id=pair.id,
            analysis_run_id=run_id,
            category=FindingCategory(output.category),
            confidence=output.confidence,
            rationale=output.rationale,
            explanation=explanation.text,
            evidence_spans=explanation.evidence_spans,
            original_ai_output=output.model_dump(mode="json"),
            context_version=pack.context_version,
            prompt_version=PROMPT_VERSION,
        )
        try:
            with db.begin_nested():
                db.add(finding)
                db.flush()
        except IntegrityError:  # another delivery of this task stored it first
            finding = None
    db.commit()
    return finding


def classify_requirement(
    db: Session, requirement_id: uuid.UUID, llm: LLMClient, *, run_id: uuid.UUID | None = None
) -> Finding | None:
    """Check one requirement for Ambiguous / Incomplete; returns the new finding or ``None``."""
    requirement = db.scalar(
        select(Requirement).where(Requirement.id == requirement_id).with_for_update()
    )
    if requirement is None or requirement.state in NOT_ANALYSED:
        return None
    if requirement.single_checked_version == requirement.current_version:
        return None
    project = db.get(Project, requirement.project_id)
    if project is None:
        return None
    context_service.ensure_analysis_allowed(db, project)

    pack = ContextPackBuilder(db).build(project, query_text=requirement.body)
    try:
        output = Classifier(llm).classify_single(
            as_input(requirement), pack=pack, project_id=project.id
        )
    except (LLMOutputError, LLMRefusedError) as exc:
        db.rollback()
        logger.warning("Requirement %s not checked: %s", requirement_id, type(exc).__name__)
        return None

    requirement.single_checked_version = requirement.current_version
    finding: Finding | None = None
    if output.is_issue:
        explanation = explain_single(output, _subject(requirement))
        finding = Finding(
            project_id=project.id,
            document_id=requirement.document_id,
            requirement_id=requirement.id,
            analysis_run_id=run_id,
            category=FindingCategory(output.category),
            confidence=output.confidence,
            rationale=output.rationale,
            explanation=explanation.text,
            evidence_spans=explanation.evidence_spans,
            original_ai_output=output.model_dump(mode="json"),
            context_version=pack.context_version,
            prompt_version=PROMPT_VERSION,
        )
        db.add(finding)
    db.commit()
    return finding


@celery_app.task(
    name="classification.classify_pair",
    bind=True,
    autoretry_for=(LLMUnavailableError,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=5,
)
def classify_pair_task(self: object, pair_id: str, run_id: str | None = None) -> str | None:
    """Returns the finding id, or ``None``."""
    llm = get_llm_client()
    if llm is None:
        logger.warning("Pair %s not classified: no LLM is configured", pair_id)
        return None
    with session_scope() as db:
        try:
            finding = classify_candidate_pair(
                db, uuid.UUID(pair_id), llm, run_id=uuid.UUID(run_id) if run_id else None
            )
        except LLMUnavailableError:
            raise
        except (LLMError, BudgetExceededError) as exc:
            logger.warning("Pair %s not classified: %s", pair_id, exc)
            return None
        return str(finding.id) if finding else None


@celery_app.task(
    name="classification.classify_requirement",
    autoretry_for=(LLMUnavailableError,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=5,
)
def classify_requirement_task(requirement_id: str, run_id: str | None = None) -> str | None:
    llm = get_llm_client()
    if llm is None:
        return None
    with session_scope() as db:
        try:
            finding = classify_requirement(
                db, uuid.UUID(requirement_id), llm, run_id=uuid.UUID(run_id) if run_id else None
            )
        except LLMUnavailableError:
            raise
        except (LLMError, BudgetExceededError) as exc:
            logger.warning("Requirement %s not checked: %s", requirement_id, exc)
            return None
        return str(finding.id) if finding else None
