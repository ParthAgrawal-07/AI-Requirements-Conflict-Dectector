"""Change requests after intake: edit, review, merge, close (Parth — US-35, US-12, FR-65, FR-66,
FR-89, FR-98, DR-14; design update §3.2, §7.2, §11.3).

Status, recomputed after every review, edit and merge (:func:`refresh_status`)::

    open ⇄ approved        approved when the review policy is satisfied (AgreementGuard)
    open / approved → needs_update   the requirement moved past base_version (a competing merge)
    needs_update → open    the proposer updates the proposal against the current version
    open / approved → merged | closed (rejected, with a reason) | withdrawn (by the proposer)

**Editing** (``PATCH``) is for the proposer: new text or reason, optionally rebased onto the
current version. It bumps ``proposal_revision``, stores the revision, dismisses earlier reviews
(they are bound to the old revision) and runs the checks again.

**Merging** (``rcr.merge``) is one transaction: the requirement and the request are locked, the
agreement rules are evaluated (``app.services.agreement``) and, if any is unmet, nothing is
written and the answer is **409** ``merge_blocked`` listing them (``details``). Otherwise:
version *n+1* with the proposed text (or the requirement becomes Deprecated), the baseline
revision goes up, the requirement's findings become stale and a fresh analysis is queued, the
issues it resolves close (``resolved_by_merge``), competing requests turn ``needs_update`` and
every other open report goes stale. Audited, announced, and on the map.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from app.consequences import tasks as consequence_tasks
from app.core.errors import AppError, BadRequestError, ConflictError, ForbiddenError
from app.graph import deltas, narrator
from app.intake.change_intake import resolves
from app.models import (
    AuditAction,
    AuditLog,
    CandidatePair,
    ChangeRequest,
    ChangeRequestRevision,
    Embedding,
    Finding,
    Project,
    Requirement,
    RequirementState,
    RequirementTransition,
    RequirementVersion,
    User,
)
from app.models.change_request import (
    ACTIVE,
    APPROVED,
    CLOSED,
    DRAFT,
    MERGED,
    NEEDS_UPDATE,
    OPEN,
    WITHDRAWN,
)
from app.models.issue import RESOLVED_BY_MERGE
from app.realtime import bus
from app.realtime.events import (
    CHANGE_REQUEST_CLOSED,
    CHANGE_REQUEST_MERGED,
    CHANGE_REQUEST_REVIEWED,
    CHANGE_REQUEST_UPDATED,
    change_request_event,
)
from app.services import analysis_orchestrator, issues
from app.services.access import AccessContext
from app.services.agreement import AgreementGuard
from app.services.reviews import ReviewPolicy

BASELINE = (RequirementState.APPROVED, RequirementState.IMPLEMENTED)


def announce(
    db: Session, change_request: ChangeRequest, event_type: str, actor: User | None, **data: object
) -> None:
    project = db.get(Project, change_request.project_id)
    if project is None:  # pragma: no cover
        return
    bus.publish(
        change_request_event(
            event_type,
            workspace_id=project.workspace_id,
            project_id=project.id,
            change_request_id=change_request.id,
            requirement_id=change_request.requirement_id,
            number=change_request.number,
            status=change_request.status,
            proposal_revision=change_request.proposal_revision,
            actor_id=actor.id if actor else None,
            **data,
        )
    )


def refresh_status(db: Session, change_request: ChangeRequest) -> str:
    """Recompute open / approved / needs_update (decided and draft requests keep theirs)."""
    if change_request.status not in (OPEN, APPROVED, NEEDS_UPDATE):
        return change_request.status
    requirement = db.get(Requirement, change_request.requirement_id)
    if requirement is not None and change_request.base_version != requirement.current_version:
        status = NEEDS_UPDATE
    elif AgreementGuard(db).approved_by_policy(change_request):
        status = APPROVED
    else:
        status = OPEN
    if status != change_request.status:
        change_request.status = status
        db.commit()
    return status


def on_opened(db: Session, change_request: ChangeRequest) -> None:
    """After intake opened it (or a draft was opened): ask the reviewers the policy wants."""
    if change_request.status == OPEN:
        ReviewPolicy(db).request(change_request)


def after_review(db: Session, change_request: ChangeRequest, actor: User, decision: str) -> None:
    refresh_status(db, change_request)
    announce(db, change_request, CHANGE_REQUEST_REVIEWED, actor, decision=decision)
    project = db.get(Project, change_request.project_id)
    if project is not None:  # Madhav (US-53): watchers of the request hear about each review
        from app.notifications import hooks, subjects

        hooks.watchers(
            db,
            project,
            "change_request",
            change_request.id,
            subjects.change_request(db, change_request, f"{actor.full_name} reviewed {{key}}"),
            actor_id=actor.id,
            exclude=[change_request.proposer_id],
            change_request_id=change_request.id,
        )


def _proposer_only(ctx: AccessContext, change_request: ChangeRequest) -> None:
    if ctx.user.id != change_request.proposer_id:
        raise ForbiddenError("Only the proposer can change or withdraw this change request")


def update_proposal(
    db: Session,
    ctx: AccessContext,
    change_request: ChangeRequest,
    *,
    proposed_body: str | None = None,
    reason: str | None = None,
    rebase: bool = False,
    open_draft: bool = False,
) -> ChangeRequest:
    _proposer_only(ctx, change_request)
    if change_request.status not in ACTIVE:
        raise ConflictError("This change request is already decided", code="decided")
    requirement = db.get(Requirement, change_request.requirement_id)
    if requirement is None:  # pragma: no cover
        raise ConflictError("The requirement is gone", code="decided")
    text = proposed_body.strip() if proposed_body is not None else None
    if text is not None:
        if change_request.kind != "modify":
            raise BadRequestError("A deprecation proposes no text", code="unexpected_body")
        if not text:
            raise BadRequestError("Write the proposed text", code="proposed_body_required")
        if text == requirement.body.strip():
            raise BadRequestError("The proposed text is the current text", code="no_change")
    changed = (
        (text is not None and text != change_request.proposed_body)
        or (reason is not None and reason.strip() != change_request.reason)
        or (rebase and change_request.base_version != requirement.current_version)
    )
    if not changed and not (open_draft and change_request.status == DRAFT):
        return change_request
    if changed:
        if text is not None:
            change_request.proposed_body = text
        if reason is not None:
            change_request.reason = reason.strip()
        if rebase:
            change_request.base_version = requirement.current_version
        change_request.proposal_revision += 1
        db.add(
            ChangeRequestRevision(
                change_request_id=change_request.id,
                revision=change_request.proposal_revision,
                proposed_body=change_request.proposed_body,
                reason=change_request.reason,
                author_id=ctx.user.id,
            )
        )
    if change_request.status == DRAFT and open_draft:
        change_request.status = OPEN
    elif change_request.status != DRAFT:
        change_request.status = OPEN  # earlier approvals were for the old revision
    db.add(
        AuditLog(
            workspace_id=ctx.workspace_id,
            actor_id=ctx.user.id,
            requirement_id=change_request.requirement_id,
            action=AuditAction.CHANGE_REQUEST_UPDATED,
            details={
                "change_request_id": str(change_request.id),
                "proposal_revision": change_request.proposal_revision,
                "base_version": change_request.base_version,
            },
        )
    )
    db.commit()
    if change_request.status != DRAFT:
        on_opened(db, change_request)
        consequence_tasks.queue_checks(change_request.id)
        refresh_status(db, change_request)
    announce(db, change_request, CHANGE_REQUEST_UPDATED, ctx.user)
    return change_request


def _decide(
    db: Session, ctx: AccessContext, change_request: ChangeRequest, status: str, reason: str | None
) -> ChangeRequest:
    if change_request.status not in ACTIVE:
        raise ConflictError("This change request is already decided", code="decided")
    change_request.status = status
    change_request.closed_by, change_request.closed_at = ctx.user.id, datetime.now(UTC)
    change_request.close_reason = (reason or "").strip() or None
    db.add(
        AuditLog(
            workspace_id=ctx.workspace_id,
            actor_id=ctx.user.id,
            requirement_id=change_request.requirement_id,
            action=AuditAction.CHANGE_REQUEST_CLOSED,
            details={"change_request_id": str(change_request.id), "status": status},
        )
    )
    db.commit()
    announce(db, change_request, CHANGE_REQUEST_CLOSED, ctx.user)
    return change_request


def withdraw(db: Session, ctx: AccessContext, change_request: ChangeRequest) -> ChangeRequest:
    _proposer_only(ctx, change_request)
    return _decide(db, ctx, change_request, WITHDRAWN, None)


def close(
    db: Session, ctx: AccessContext, change_request: ChangeRequest, reason: str
) -> ChangeRequest:
    """Close without merging (rejected): ``rcr.merge``, with a reason that is kept (§3.2)."""
    if not reason.strip():
        raise BadRequestError("Say why it is closed without merging", code="reason_required")
    return _decide(db, ctx, change_request, CLOSED, reason)


@dataclass
class Merged:
    change_request: ChangeRequest
    version: int
    stale_findings: list[uuid.UUID]


def _findings_of(db: Session, requirement_id: uuid.UUID) -> list[uuid.UUID]:
    pairs = select(CandidatePair.id).where(
        or_(
            CandidatePair.requirement_a_id == requirement_id,
            CandidatePair.requirement_b_id == requirement_id,
        )
    )
    return list(
        db.scalars(
            select(Finding.id).where(
                or_(Finding.requirement_id == requirement_id, Finding.candidate_pair_id.in_(pairs)),
                ~Finding.is_stale,
            )
        )
    )


def merge(
    db: Session,
    ctx: AccessContext,
    change_request: ChangeRequest,
    *,
    accepted_risk_reason: str | None = None,
) -> Merged:
    requirement = db.scalar(
        select(Requirement).where(Requirement.id == change_request.requirement_id).with_for_update()
    )
    db.refresh(change_request, with_for_update=True)
    if requirement is None:  # pragma: no cover
        raise ConflictError("The requirement is gone", code="decided")
    accepted = bool(accepted_risk_reason and accepted_risk_reason.strip())
    unmet = AgreementGuard(db).unmet(change_request, accepted_risk=accepted)
    if unmet:
        db.rollback()
        raise AppError(
            "This change request cannot be merged yet",
            status_code=409,
            code="merge_blocked",
            details=[u.as_json() for u in unmet],
        )
    project = db.get(Project, requirement.project_id)
    if project is None:  # pragma: no cover
        raise ConflictError("The project is gone", code="decided")
    now = datetime.now(UTC)
    stale = _findings_of(db, requirement.id)
    in_baseline = requirement.state in BASELINE
    before_state = requirement.state
    if change_request.kind == "modify":
        requirement.body = change_request.proposed_body or requirement.body
        requirement.current_version += 1
        # The vector is of the old text; the queued run embeds the new one (US-31 path).
        db.execute(delete(Embedding).where(Embedding.requirement_id == requirement.id))
        db.add(
            RequirementVersion(
                requirement_id=requirement.id,
                version_no=requirement.current_version,
                body_snapshot=requirement.body,
                changed_by=change_request.proposer_id,
                change_request_id=change_request.id,
            )
        )
    else:
        requirement.state = RequirementState.DEPRECATED
        db.add(
            RequirementTransition(
                requirement_id=requirement.id,
                from_state=before_state,
                to_state=RequirementState.DEPRECATED,
                version=requirement.current_version,
                actor_id=ctx.user.id,
                reason=change_request.reason,
            )
        )
    if stale:
        db.execute(update(Finding).where(Finding.id.in_(stale)).values(is_stale=True))
    if in_baseline:
        project.baseline_revision += 1
    change_request.status = MERGED
    change_request.merged_version = requirement.current_version
    change_request.merged_by, change_request.merged_at = ctx.user.id, now
    competing = list(
        db.scalars(
            select(ChangeRequest).where(
                ChangeRequest.requirement_id == requirement.id,
                ChangeRequest.id != change_request.id,
                ChangeRequest.status.in_((OPEN, APPROVED)),
            )
        )
    )
    for other in competing:
        other.status = NEEDS_UPDATE
    run = (
        analysis_orchestrator.queue_requirement_run(db, requirement)
        if change_request.kind == "modify"
        else None
    )
    db.add(
        AuditLog(
            workspace_id=project.workspace_id,
            actor_id=ctx.user.id,
            requirement_id=requirement.id,
            action=AuditAction.CHANGE_REQUEST_MERGED,
            details={
                "change_request_id": str(change_request.id),
                "version": requirement.current_version,
                "kind": change_request.kind,
                "accepted_risk": accepted,
                "accepted_risk_reason": (accepted_risk_reason or "").strip() or None,
                "stale_findings": [str(f) for f in stale],
                "needs_update": [str(o.id) for o in competing],
            },
        )
    )
    db.commit()  # the merge itself: everything above, or nothing

    if run is not None:
        analysis_orchestrator.dispatch_requirement_run(run.id, analysis_orchestrator.send)
    for issue in resolves(db, change_request.id):
        issues.close(db, issue, RESOLVED_BY_MERGE, actor=ctx.user)
    for finding_id in stale:  # Dhavni (US-52): their auto issues close, and reopen if re-found
        finding = db.get(Finding, finding_id)
        if finding is not None:
            issues.on_finding_changed(db, finding, actor=ctx.user)
    consequence_tasks.mark_stale(db, project.id)
    label = requirement.source_req_id or "the requirement"
    sentence = (
        narrator.merged(
            ctx.user.full_name, change_request.number, label, requirement.current_version
        )
        if change_request.kind == "modify"
        else narrator.moved(ctx.user.full_name, label, RequirementState.DEPRECATED.value)
    )
    deltas.publish(
        db,
        project.id,
        deltas.Change(requirements={requirement.id}, findings=set(stale), sentences=[sentence]),
        actor=ctx.user,
    )
    announce(
        db, change_request, CHANGE_REQUEST_MERGED, ctx.user, version=requirement.current_version
    )
    for other in competing:
        announce(db, other, CHANGE_REQUEST_UPDATED, ctx.user, needs_update=True)
    _notify_merged(db, change_request, requirement, ctx.user)
    return Merged(change_request, requirement.current_version, stale)


def _notify_merged(
    db: Session, change_request: ChangeRequest, requirement: Requirement, actor: User
) -> None:
    """US-38: the proposer, the owner, the owners of affected requirements and the people
    assigned to the issues it resolved hear that it merged (best effort)."""
    from app.consequences.impact import ImpactAnalyzer
    from app.models.notification import MERGED as MERGED_KIND
    from app.notifications import subjects
    from app.notifications.service import NotificationService

    project = db.get(Project, change_request.project_id)
    if project is None:  # pragma: no cover
        return
    try:
        from app.services.social import watcher_ids

        people = {change_request.proposer_id, requirement.owner_id}
        people |= {a.owner_id for a in ImpactAnalyzer(db).analyse(requirement).affected}
        # Madhav (US-53): whoever watches the change request or the requirement.
        people |= watcher_ids(db, "change_request", change_request.id)
        people |= watcher_ids(db, "requirement", requirement.id)
        for issue in resolves(db, change_request.id):
            people |= set(issues.assignee_ids(db, issue.id))
        NotificationService(db).notify(
            people,
            MERGED_KIND,
            workspace_id=project.workspace_id,
            project_id=project.id,
            actor_id=actor.id,
            subject=subjects.change_request(
                db,
                change_request,
                "{key} merged: {requirement} v" + str(requirement.current_version),
            ),
            change_request_id=change_request.id,
            requirement_id=requirement.id,
        )
    except Exception:
        db.rollback()


def versions(db: Session, requirement_id: uuid.UUID) -> list[RequirementVersion]:
    """Newest first (US-12)."""
    return list(
        db.scalars(
            select(RequirementVersion)
            .where(RequirementVersion.requirement_id == requirement_id)
            .order_by(RequirementVersion.version_no.desc())
        )
    )
