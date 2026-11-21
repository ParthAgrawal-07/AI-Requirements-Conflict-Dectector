"""Who is told what (Madhav — US-38, FR-69): one function per moment, called by its producer
after the commit. Each is best effort — a failed notification never fails the action it reports.

============================  ==============================================================
:func:`mentioned`             @mentioned in a message or a result card → ``mentioned``
:func:`assigned`              assigned to an issue (by a person or automatically) → ``assigned``
:func:`join_requested`        someone asks to join with an approval code → managers,
                              ``join_request``
:func:`results_for_run`       an analysis run found something on your requirements → owners,
                              ``results``
============================  ==============================================================

Review requests, decisions and merges are Parth's (``app.services.reviews``,
``app.services.change_requests``).
"""

import logging
import uuid
from collections.abc import Collection

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AnalysisRun,
    Channel,
    Finding,
    Issue,
    JoinRequest,
    Membership,
    Message,
    Project,
    User,
)
from app.models.notification import ASSIGNED, JOIN_REQUEST, MENTIONED, RESULTS
from app.notifications import subjects
from app.notifications.service import NotificationService
from app.services.access import Scope, build_access_context
from app.services.review_state import involved_requirements

logger = logging.getLogger(__name__)


def mentioned(db: Session, project: Project, channel: Channel, message: Message) -> None:
    if not message.mentions:
        return
    try:
        author = db.get(User, message.author_id) if message.author_id else None
        who = author.full_name if author else "The analysis"
        NotificationService(db).notify(
            [uuid.UUID(u) for u in message.mentions],
            MENTIONED,
            workspace_id=project.workspace_id,
            project_id=project.id,
            actor_id=message.author_id,
            subject=subjects.message(
                project, channel.id, message.id, f"{who} mentioned you in #{channel.name}"
            ),
            channel_id=channel.id,
            message_id=message.id,
        )
    except Exception:
        db.rollback()
        logger.exception("Mention notifications for message %s failed", message.id)


def assigned(
    db: Session, issue: Issue, user_ids: Collection[uuid.UUID], *, actor_id: uuid.UUID | None
) -> None:
    if not user_ids:
        return
    try:
        project = db.get(Project, issue.project_id)
        if project is None:  # pragma: no cover
            return
        NotificationService(db).notify(
            user_ids,
            ASSIGNED,
            workspace_id=project.workspace_id,
            project_id=project.id,
            actor_id=actor_id,
            subject=subjects.issue(db, issue, "{key} was assigned to you"),
            issue_id=issue.id,
        )
    except Exception:
        db.rollback()
        logger.exception("Assignment notifications for issue %s failed", issue.id)


def _managers(db: Session, workspace_id: uuid.UUID, project_id: uuid.UUID | None) -> set[uuid.UUID]:
    """Current members who may decide join requests here (``members.manage``)."""
    members = db.scalars(
        select(User)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.workspace_id == workspace_id, Membership.ended_at.is_(None))
    )
    scope = Scope(workspace_id, project_id)
    return {u.id for u in members if build_access_context(db, u, scope).can("members.manage")}


def join_requested(db: Session, request: JoinRequest) -> None:
    try:
        newcomer = db.get(User, request.user_id)
        NotificationService(db).notify(
            _managers(db, request.workspace_id, request.project_id),
            JOIN_REQUEST,
            workspace_id=request.workspace_id,
            project_id=request.project_id,
            actor_id=request.user_id,
            subject=subjects.join_request(
                request.workspace_id,
                request.id,
                f"{newcomer.full_name if newcomer else 'Someone'} asks to join",
            ),
            join_request_id=request.id,
        )
    except Exception:
        db.rollback()
        logger.exception("Join request notifications for %s failed", request.id)


def results_for_run(db: Session, run: AnalysisRun) -> None:
    """Tell each owner what the run found on their requirements (one per finding)."""
    try:
        project = db.get(Project, run.project_id)
        if project is None:  # pragma: no cover
            return
        service = NotificationService(db)
        findings = db.scalars(
            select(Finding)
            .where(Finding.analysis_run_id == run.id, ~Finding.is_stale)
            .order_by(Finding.created_at, Finding.id)
        ).all()
        for finding in findings:
            requirements = involved_requirements(db, finding)
            owners = {r.owner_id for r in requirements if r.owner_id is not None}
            labels = [subjects.requirement_label(r) for r in requirements]
            service.notify(
                owners,
                RESULTS,
                workspace_id=project.workspace_id,
                project_id=project.id,
                subject=subjects.finding(db, finding, labels, "{category} found on {key}"),
                finding_id=finding.id,
                requirement_ids=[str(r.id) for r in requirements],
            )
    except Exception:
        db.rollback()
        logger.exception("Result notifications for run %s failed", run.id)
