"""Analysis orchestration (Parth — US-05 enabler, US-03; design update §3.1; gap G1).

After extraction (``documents.process``) a document goes through:

    embed  →  candidate pairs  →  classify each pending pair  ┐
                               →  check each requirement      ┴→  run done

1. ``analysis.run_document`` embeds the document (Heet) — allowed in Setup, it costs nothing — and
   stops there while the project is in **Setup** (ContextGate, FR-103). When the project becomes
   active, ``analyse_project`` runs every done document.
2. It opens an :class:`~app.models.AnalysisRun`, generates candidate pairs (Heet) and fans out one
   task per pending pair and per requirement still to check, each carrying the run id.
3. Each task classifies its item (Keval) and then *counts* it on the run in one atomic UPDATE:
   ``pairs_done`` / ``pairs_failed`` and ``checks_done`` / ``checks_failed``. The task that brings
   the counts to their totals closes the run and announces ``analysis.completed`` with the numbers.
   A failed pair stays visible as failed (G1); a run "done with 2 failed pairs" says so.
4. An exhausted LLM budget parks the run as ``waiting_budget`` (the item stays pending; re-running
   the analysis picks it up). No LLM configured: the run ends after candidates, saying so.

Every step is idempotent: re-running a document skips unchanged pairs and requirements (G1), so a
task delivered twice, or a re-run after a crash, never pays twice or duplicates findings.
Tasks are sent by name so this module never imports the model or parsing stacks at import time.
"""

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Literal, cast

from sqlalchemy import CursorResult, select, update
from sqlalchemy.orm import Session

from app.core.celery_app import celery_app
from app.models import (
    AnalysisRun,
    AnalysisRunStatus,
    AnalysisScope,
    CandidatePair,
    ClassificationStatus,
    Document,
    DocumentStatus,
    Project,
    ProjectStatus,
    Requirement,
    RequirementState,
)
from app.realtime import bus
from app.realtime.events import analysis_completed

logger = logging.getLogger(__name__)

Dispatch = Callable[[str, list[str]], None]
Outcome = Literal["done", "failed", "budget"]

RUN_DOCUMENT = "analysis.run_document"
CLASSIFY_PAIR = "analysis.classify_pair"
CHECK_REQUIREMENT = "analysis.check_requirement"
NOT_ANALYSED = (RequirementState.REJECTED, RequirementState.DEPRECATED)
NO_LLM = "No LLM is configured: candidate pairs were found but not classified."


def send(name: str, args: list[str]) -> None:
    """Queue a task by name (best effort: a broker outage is logged, the run can be re-started)."""
    try:
        celery_app.send_task(name, args=args, retry=False)
    except Exception:
        logger.warning("Could not queue %s %s", name, args, exc_info=True)


def dispatch_document(document_id: uuid.UUID, dispatch: Dispatch = send) -> None:
    dispatch(RUN_DOCUMENT, [str(document_id)])


def analyse_project(db: Session, project_id: uuid.UUID, dispatch: Dispatch = send) -> int:
    """Queue the analysis of every processed document of a project (e.g. when it becomes active).
    Returns how many were queued."""
    documents = list(
        db.scalars(
            select(Document.id)
            .where(Document.project_id == project_id, Document.status == DocumentStatus.DONE)
            .order_by(Document.created_at)
        )
    )
    for document_id in documents:
        dispatch_document(document_id, dispatch)
    return len(documents)


def start_document_run(
    db: Session, document_id: uuid.UUID, *, llm_configured: bool, dispatch: Dispatch = send
) -> AnalysisRun | None:
    """Candidates for a processed (and embedded) document, then fan out. ``None`` while the
    project is in Setup or the document is gone."""
    from app.embeddings.candidates import generate_candidates

    document = db.get(Document, document_id)
    if document is None or document.status is not DocumentStatus.DONE:
        return None
    project = db.get(Project, document.project_id)
    if project is None or project.status is not ProjectStatus.ACTIVE:
        logger.info("Analysis of %s waits: the project is not active", document_id)
        return None

    requirement_ids = list(
        db.scalars(
            select(Requirement.id)
            .where(Requirement.document_id == document.id, Requirement.state.not_in(NOT_ANALYSED))
            .order_by(Requirement.order_index)
        )
    )
    candidates = generate_candidates(db, project.id, requirement_ids=requirement_ids)
    to_check = list(
        db.scalars(
            select(Requirement.id).where(
                Requirement.id.in_(requirement_ids),
                Requirement.single_checked_version.is_distinct_from(Requirement.current_version),
            )
        )
    )
    run = AnalysisRun(
        project_id=project.id,
        scope=AnalysisScope.DOCUMENT,
        subject_id=document.id,
        status=AnalysisRunStatus.RUNNING,
        pairs_total=len(candidates.pending),
        checks_total=len(to_check),
        started_at=datetime.now(UTC),
    )
    db.add(run)
    db.commit()

    if not llm_configured or not (candidates.pending or to_check):
        _close(
            db,
            run,
            error=NO_LLM if not llm_configured and run.pairs_total + run.checks_total else None,
        )
        return run
    for pair_id in candidates.pending:
        dispatch(CLASSIFY_PAIR, [str(run.id), str(pair_id)])
    for requirement_id in to_check:
        dispatch(CHECK_REQUIREMENT, [str(run.id), str(requirement_id)])
    return run


def pair_outcome(db: Session, pair_id: uuid.UUID) -> Outcome:
    pair = db.get(CandidatePair, pair_id)
    if pair is None or pair.classification_status is ClassificationStatus.DONE:
        return "done"  # a pair whose requirement disappeared has nothing left to do
    if pair.classification_status is ClassificationStatus.FAILED:
        return "failed"
    return "budget" if pair.last_error == "budget_exhausted" else "failed"


def check_outcome(db: Session, requirement_id: uuid.UUID) -> Outcome:
    requirement = db.get(Requirement, requirement_id)
    if requirement is None or requirement.single_checked_version == requirement.current_version:
        return "done"
    return "failed"


def record(
    db: Session, run_id: uuid.UUID, kind: Literal["pair", "check"], outcome: Outcome
) -> None:
    """Count one finished item on the run, atomically; close the run when everything is counted."""
    if outcome == "budget":
        db.execute(
            update(AnalysisRun)
            .where(AnalysisRun.id == run_id, AnalysisRun.status == AnalysisRunStatus.RUNNING)
            .values(status=AnalysisRunStatus.WAITING_BUDGET)
        )
        db.commit()
        _announce(db, run_id)
        return
    column = {
        ("pair", "done"): AnalysisRun.pairs_done,
        ("pair", "failed"): AnalysisRun.pairs_failed,
        ("check", "done"): AnalysisRun.checks_done,
        ("check", "failed"): AnalysisRun.checks_failed,
    }[(kind, outcome)]
    row = db.execute(
        update(AnalysisRun)
        .where(AnalysisRun.id == run_id)
        .values({column.key: column + 1})
        .returning(
            AnalysisRun.pairs_total,
            AnalysisRun.pairs_done + AnalysisRun.pairs_failed,
            AnalysisRun.checks_total,
            AnalysisRun.checks_done + AnalysisRun.checks_failed,
            AnalysisRun.status,
        )
    ).first()
    db.commit()
    if row is None:
        return
    pairs_total, pairs_counted, checks_total, checks_counted, status = row
    if pairs_counted >= pairs_total and checks_counted >= checks_total:
        run = db.get(AnalysisRun, run_id)
        if run is not None and status is AnalysisRunStatus.RUNNING:
            _close(db, run)


def _close(db: Session, run: AnalysisRun, *, error: str | None = None) -> None:
    claimed = db.execute(
        update(AnalysisRun)
        .where(AnalysisRun.id == run.id, AnalysisRun.finished_at.is_(None))
        .values(status=AnalysisRunStatus.DONE, finished_at=datetime.now(UTC), error_message=error)
    )
    db.commit()
    if cast(CursorResult[Any], claimed).rowcount:  # only the task that closed it announces it
        _announce(db, run.id)


def _announce(db: Session, run_id: uuid.UUID) -> None:
    run = db.get(AnalysisRun, run_id)
    if run is None:
        return
    db.refresh(run)
    project = db.get(Project, run.project_id)
    if project is None:
        return
    bus.publish(
        analysis_completed(
            workspace_id=project.workspace_id,
            project_id=project.id,
            run_id=run.id,
            subject_id=run.subject_id,
            status=run.status.value,
            pairs_total=run.pairs_total,
            pairs_failed=run.pairs_failed,
            checks_total=run.checks_total,
            checks_failed=run.checks_failed,
        )
    )
