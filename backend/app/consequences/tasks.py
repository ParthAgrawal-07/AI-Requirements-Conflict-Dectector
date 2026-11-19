"""Building and storing consequence reports (Madhav — US-11, US-34, FR-64, FR-98, FR-99).

``consequence.build`` runs whenever a change request opens, its proposal is edited, or someone
asks for a re-run: impact (``impact``), probe and checks (``checks``), findings delta (``delta``)
and risk (``risk``), stored as a new ``consequence_reports`` row. The change request records the
proposal revision and base version the checks ran on (``checks_proposal_revision`` /
``checks_base_version``), which the merge compares with the current ones (Parth, FR-98).

**Staleness (FR-64).** A report is stale when the requirement moved past its base version, the
proposal was edited since, or the project's baseline revision moved on (another merge).
:func:`refresh_staleness` checks and records it; approving and merging are blocked until the
checks run again.

Nothing here changes a requirement or a finding: the report only describes what merging would do.
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import CursorResult, select, update
from sqlalchemy.orm import Session

from app.classification import narrative
from app.classification.llm_client import LLMClient, get_llm_client
from app.consequences import checks as consequence_checks
from app.consequences.delta import build_delta, open_partners
from app.consequences.impact import ImpactAnalyzer
from app.consequences.risk import assess
from app.core.celery_app import celery_app
from app.core.database import session_scope
from app.embeddings.model import Embedder, get_embedder
from app.models import ChangeRequest, ConsequenceReport, Project, Requirement
from app.models.change_request import ACTIVE
from app.realtime import bus
from app.realtime.events import CHANGE_REQUEST_CHECKED, change_request_event
from app.services import analysis_orchestrator

logger = logging.getLogger(__name__)

BUILD = "consequence.build"


def latest_report(db: Session, change_request_id: uuid.UUID) -> ConsequenceReport | None:
    return db.scalar(
        select(ConsequenceReport)
        .where(ConsequenceReport.change_request_id == change_request_id)
        # The report for the newest proposal and baseline wins, whatever order the workers
        # finished in (``created_at`` is each transaction's start time).
        .order_by(
            ConsequenceReport.proposal_revision.desc(),
            ConsequenceReport.baseline_revision.desc(),
            ConsequenceReport.created_at.desc(),
            ConsequenceReport.id.desc(),
        )
        .limit(1)
    )


def stale_reasons(
    report: ConsequenceReport,
    change_request: ChangeRequest,
    requirement: Requirement,
    project: Project,
) -> list[str]:
    reasons = []
    if report.base_version != requirement.current_version:
        reasons.append("the requirement changed since the checks ran")
    if report.proposal_revision != change_request.proposal_revision:
        reasons.append("the proposal was edited since the checks ran")
    if report.baseline_revision != project.baseline_revision:
        reasons.append("the baseline changed since the checks ran")
    return reasons


def refresh_staleness(
    db: Session, report: ConsequenceReport, change_request: ChangeRequest
) -> bool:
    """Mark the report stale if it is (once stale, always stale). Returns ``is_stale``."""
    if report.is_stale:
        return True
    requirement = db.get(Requirement, change_request.requirement_id)
    project = db.get(Project, change_request.project_id)
    if requirement is None or project is None:  # pragma: no cover
        return False
    if stale_reasons(report, change_request, requirement, project):
        report.is_stale = True
        db.commit()
    return report.is_stale


def mark_stale(db: Session, project_id: uuid.UUID) -> int:
    """After a merge: every report of the project's undecided requests computed against an older
    baseline becomes stale. Returns how many."""
    project = db.get(Project, project_id)
    if project is None:
        return 0
    active = select(ChangeRequest.id).where(
        ChangeRequest.project_id == project_id, ChangeRequest.status.in_(ACTIVE)
    )
    # The baseline is read inside the UPDATE: a merge committed after this function started must
    # not leave a report computed against the newest baseline marked stale.
    current = select(Project.baseline_revision).where(Project.id == project_id).scalar_subquery()
    result = db.execute(
        update(ConsequenceReport)
        .where(
            ConsequenceReport.change_request_id.in_(active),
            ConsequenceReport.baseline_revision != current,
            ConsequenceReport.is_stale.is_(False),
        )
        .values(is_stale=True)
        .execution_options(synchronize_session=False)
    )
    db.commit()
    return cast(CursorResult[Any], result).rowcount


def build_report(
    db: Session,
    change_request_id: uuid.UUID,
    llm: LLMClient | None,
    embedder: Embedder | None,
) -> ConsequenceReport | None:
    """Run every check and store the report. ``None`` when the request is decided or gone."""
    change_request = db.get(ChangeRequest, change_request_id)
    if change_request is None or change_request.status not in ACTIVE:
        return None
    requirement = db.get(Requirement, change_request.requirement_id)
    project = db.get(Project, change_request.project_id)
    if requirement is None or project is None:  # pragma: no cover
        return None

    # What this run checks; the request may move on (a new revision) while it probes.
    revision, base_version = change_request.proposal_revision, change_request.base_version
    impact = ImpactAnalyzer(db).analyse(requirement, kind=change_request.kind)
    probe = consequence_checks.probe(db, change_request, requirement, impact, llm, embedder)
    checks = consequence_checks.run_checks(
        change_request, requirement, impact, probe, open_partners=open_partners(db, requirement)
    )
    delta = build_delta(db, requirement, change_request.kind, impact, probe)
    level, reasons = assess(checks, impact, delta)
    report = ConsequenceReport(
        change_request_id=change_request.id,
        proposal_revision=revision,
        base_version=base_version,
        baseline_revision=project.baseline_revision,
        status="done",
        risk_level=level,
        risk_reasons=reasons,
        affected=[a.as_json() for a in impact.affected],
        checks=[c.as_json() for c in checks],
        findings_delta=delta,
        llm_calls=probe.llm_calls,
    )
    db.add(report)
    current = db.scalar(
        select(ChangeRequest)
        .where(ChangeRequest.id == change_request.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    # A slower worker for an older revision must not move the markers back (FR-98).
    if current is not None and (current.checks_proposal_revision or 0) <= revision:
        current.checks_proposal_revision = revision
        current.checks_base_version = base_version
        current.updated_at = datetime.now(UTC)
    db.commit()
    if llm is not None:  # Keval (US-34): the AI summary, kept only if it agrees with the checks
        try:
            narrative.attach(db, report, change_request, llm)
        except Exception:
            # Optional: the report and markers are committed, so the checked event still goes out.
            db.rollback()
            logger.exception("Narrative for report %s failed", report.id)
    bus.publish(
        change_request_event(
            CHANGE_REQUEST_CHECKED,
            workspace_id=project.workspace_id,
            project_id=project.id,
            change_request_id=change_request.id,
            requirement_id=requirement.id,
            number=change_request.number,
            status=change_request.status,
            proposal_revision=change_request.proposal_revision,
            actor_id=None,
            report_id=str(report.id),
            risk_level=level,
        )
    )
    return report


def queue_checks(change_request_id: uuid.UUID) -> None:
    """Best effort: a broker outage is logged and the checks can be re-run from the page."""
    analysis_orchestrator.send(BUILD, [str(change_request_id)])


@celery_app.task(name=BUILD)
def build_report_task(change_request_id: str) -> str | None:
    with session_scope() as db:
        report = build_report(db, uuid.UUID(change_request_id), get_llm_client(), get_embedder())
        return str(report.id) if report else None
