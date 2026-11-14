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
4. An exhausted LLM budget parks the run as ``waiting_budget`` (the item stays pending). Celery
   beat runs :func:`resume_waiting` every few minutes: once the project has budget again (a new
   month, or a manager raised the cap) the run resumes with only what is still pending.
   No LLM configured: the run ends after candidates, saying so.
5. When a run closes (or parks for budget) ``analysis.after_run`` does the follow-ups outside the
   classification tasks: the live-map delta (Dhavni, US-14) and — added by later stages — the
   result card and clarification questions.

**Posted requirements** (US-31, Sprint 3) take the same path with ``scope = requirement``: the post
creates a *queued* run in its own transaction (:func:`queue_requirement_run`), and
``analysis.run_requirement`` embeds the requirement, pairs it with its neighbours in the baseline
and open proposals (Heet, ``app.embeddings.incremental``) and fans out exactly as above.

Every step is idempotent: re-running a document skips unchanged pairs and requirements (G1), so a
task delivered twice, or a re-run after a crash, never pays twice or duplicates findings.
Tasks are sent by name so this module never imports the model or parsing stacks at import time.
"""

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal, cast

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

if TYPE_CHECKING:
    from app.classification.budget import BudgetGuard
    from app.embeddings.model import Embedder

logger = logging.getLogger(__name__)

Dispatch = Callable[[str, list[str]], None]
Outcome = Literal["done", "failed", "budget"]

RUN_DOCUMENT = "analysis.run_document"
RUN_REQUIREMENT = "analysis.run_requirement"
CLASSIFY_PAIR = "analysis.classify_pair"
CHECK_REQUIREMENT = "analysis.check_requirement"
AFTER_RUN = "analysis.after_run"
CLARIFY_RUN = "clarifications.generate_for_run"
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
    """Queue the analysis of every processed document of a project, and of every requirement
    posted while it was in Setup (e.g. when it becomes active). Returns how many were queued."""
    documents = list(
        db.scalars(
            select(Document.id)
            .where(Document.project_id == project_id, Document.status == DocumentStatus.DONE)
            .order_by(Document.created_at)
        )
    )
    for document_id in documents:
        dispatch_document(document_id, dispatch)
    queued = list(
        db.scalars(
            select(AnalysisRun.id)
            .where(
                AnalysisRun.project_id == project_id,
                AnalysisRun.scope == AnalysisScope.REQUIREMENT,
                AnalysisRun.status == AnalysisRunStatus.QUEUED,
            )
            .order_by(AnalysisRun.created_at)
        )
    )
    for run_id in queued:
        dispatch_requirement_run(run_id, dispatch)
    return len(documents) + len(queued)


def queue_requirement_run(db: Session, requirement: Requirement) -> AnalysisRun:
    """A queued run for a posted (or changed) requirement, **in the caller's transaction** — the
    post, its message and its run commit together (US-31). Dispatch it after the commit with
    :func:`dispatch_requirement_run`."""
    run = AnalysisRun(
        project_id=requirement.project_id,
        scope=AnalysisScope.REQUIREMENT,
        subject_id=requirement.id,
        status=AnalysisRunStatus.QUEUED,
    )
    db.add(run)
    db.flush()
    return run


def dispatch_requirement_run(run_id: uuid.UUID, dispatch: Dispatch = send) -> None:
    dispatch(RUN_REQUIREMENT, [str(run_id)])


def start_requirement_run(
    db: Session,
    run_id: uuid.UUID,
    *,
    llm_configured: bool,
    embedder: "Embedder",
    dispatch: Dispatch = send,
) -> AnalysisRun | None:
    """Embed the run's requirement, pair it with its neighbours and fan out. ``None`` when the run
    is gone or not queued (a duplicate delivery); the run stays queued while the project is in
    Setup and starts when it is activated (:func:`analyse_project`)."""
    from app.embeddings.incremental import candidates_for_requirement

    run = db.scalar(select(AnalysisRun).where(AnalysisRun.id == run_id).with_for_update())
    if run is None or run.status is not AnalysisRunStatus.QUEUED:
        db.rollback()
        return None
    project = db.get(Project, run.project_id)
    requirement = db.get(Requirement, run.subject_id)
    if project is None or requirement is None:
        db.rollback()
        return None
    if project.status is not ProjectStatus.ACTIVE:
        db.rollback()
        logger.info("Analysis of requirement %s waits: the project is not active", requirement.id)
        return None
    run.status = AnalysisRunStatus.RUNNING  # claims the run before the slow part
    run.started_at = datetime.now(UTC)
    db.commit()

    candidates = candidates_for_requirement(db, requirement, embedder)
    needs_check = (
        requirement.state not in NOT_ANALYSED
        and requirement.single_checked_version != requirement.current_version
    )
    run.pairs_total = len(candidates.pending)
    run.checks_total = 1 if needs_check else 0
    db.commit()
    _fan_out(
        db,
        run,
        candidates.pending,
        [requirement.id] if needs_check else [],
        llm_configured=llm_configured,
        dispatch=dispatch,
    )
    return run


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
    _fan_out(
        db, run, candidates.pending, to_check, llm_configured=llm_configured, dispatch=dispatch
    )
    return run


def _fan_out(
    db: Session,
    run: AnalysisRun,
    pair_ids: list[uuid.UUID],
    requirement_ids: list[uuid.UUID],
    *,
    llm_configured: bool,
    dispatch: Dispatch,
) -> None:
    """One task per pair and per requirement to check — or close the run at once when there is
    nothing to do (or no model to do it with)."""
    if not llm_configured or not (pair_ids or requirement_ids):
        work = bool(pair_ids or requirement_ids)
        _close(db, run, error=NO_LLM if not llm_configured and work else None)
        return
    for pair_id in pair_ids:
        dispatch(CLASSIFY_PAIR, [str(run.id), str(pair_id)])
    for requirement_id in requirement_ids:
        dispatch(CHECK_REQUIREMENT, [str(run.id), str(requirement_id)])


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
        parked = db.execute(
            update(AnalysisRun)
            .where(AnalysisRun.id == run_id, AnalysisRun.status == AnalysisRunStatus.RUNNING)
            .values(status=AnalysisRunStatus.WAITING_BUDGET)
        )
        db.commit()
        if cast(CursorResult[Any], parked).rowcount:  # announced once, by the task that parked it
            _announce(db, run_id)
            send(AFTER_RUN, [str(run_id)])
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
        # Looked up at call time (not bound as a default) so tests can replace ``send``.
        send(AFTER_RUN, [str(run.id)])


def after_run(db: Session, run_id: uuid.UUID) -> None:
    """Follow-ups of a run that closed or parked for budget (``analysis.after_run``): the live-map
    delta once it is done, the result card in a posted requirement's thread (Keval, US-31) —
    "waiting for budget" first, rewritten with the results when the run finishes — and the
    clarification questions, queued as their own task because each is an LLM call (Madhav, US-09).
    Each step is best effort: a failed follow-up never reopens the run."""
    from app.classification.result_card import publish_card
    from app.graph import deltas

    run = db.get(AnalysisRun, run_id)
    if run is None:
        return
    if run.status is AnalysisRunStatus.DONE:
        try:
            deltas.run_finished(db, run)
        except Exception:
            db.rollback()
            logger.exception("Map delta for run %s failed", run_id)
        if run.error_message is None:  # Madhav (US-09): questions for its findings, queued
            send(CLARIFY_RUN, [str(run.id)])
    if run.status in (AnalysisRunStatus.DONE, AnalysisRunStatus.WAITING_BUDGET):
        try:
            publish_card(db, run)
        except Exception:
            db.rollback()
            logger.exception("Result card for run %s failed", run_id)


def resume_waiting(
    db: Session, *, budget: "BudgetGuard", dispatch: Dispatch = send
) -> list[uuid.UUID]:
    """Resume every run parked for budget whose project has calls left again (Celery beat).
    Oldest first, so posts are answered in the order they were made. Returns the runs resumed."""
    resumed: list[uuid.UUID] = []
    runs = list(
        db.scalars(
            select(AnalysisRun)
            .where(AnalysisRun.status == AnalysisRunStatus.WAITING_BUDGET)
            .order_by(AnalysisRun.created_at)
        )
    )
    for run in runs:
        left = budget.remaining(run.project_id)
        if left is not None and left <= 0:
            continue
        if resume_run(db, run.id, dispatch=dispatch):
            resumed.append(run.id)
    return resumed


def resume_run(db: Session, run_id: uuid.UUID, *, dispatch: Dispatch = send) -> bool:
    """Put a parked run back to work on what is still pending; done and failed items keep their
    counts. ``False`` when it was not waiting (someone else resumed it)."""
    run = db.scalar(select(AnalysisRun).where(AnalysisRun.id == run_id).with_for_update())
    if run is None or run.status is not AnalysisRunStatus.WAITING_BUDGET:
        db.rollback()
        return False
    requirement_ids = _subject_requirements(db, run)
    pair_ids = list(
        db.scalars(
            select(CandidatePair.id).where(
                CandidatePair.classification_status == ClassificationStatus.PENDING,
                CandidatePair.requirement_a_id.in_(requirement_ids)
                | CandidatePair.requirement_b_id.in_(requirement_ids),
            )
        )
    )
    to_check = list(
        db.scalars(
            select(Requirement.id).where(
                Requirement.id.in_(requirement_ids),
                Requirement.state.not_in(NOT_ANALYSED),
                Requirement.single_checked_version.is_distinct_from(Requirement.current_version),
            )
        )
    )
    run.status = AnalysisRunStatus.RUNNING
    run.pairs_total = run.pairs_done + run.pairs_failed + len(pair_ids)
    run.checks_total = run.checks_done + run.checks_failed + len(to_check)
    db.commit()
    _fan_out(db, run, pair_ids, to_check, llm_configured=True, dispatch=dispatch)
    return True


def _subject_requirements(db: Session, run: AnalysisRun) -> list[uuid.UUID]:
    if run.scope is AnalysisScope.REQUIREMENT:
        return [run.subject_id]
    return list(db.scalars(select(Requirement.id).where(Requirement.document_id == run.subject_id)))


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
            scope=run.scope.value,
            pairs_total=run.pairs_total,
            pairs_failed=run.pairs_failed,
            checks_total=run.checks_total,
            checks_failed=run.checks_failed,
        )
    )
