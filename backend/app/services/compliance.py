"""Protection of compliance-critical requirements (Parth — US-18, FR-21, FR-36, NFR-13, DR-05,
DR-12).

* **Tagging.** A holder of ``req.protect`` marks requirements protected — one at a time
  (:func:`set_protection`) or in bulk right after an import (:func:`protect_many`, by id or by
  printed ID). Removing protection needs a reason too. Each change is audited, recorded on the
  requirement (who, when, why) and shown on the map.
* **The guard** came earlier and is unchanged: only compliance reviewers act on findings about a
  protected requirement (US-10), a change request on one merges only with a compliance approval
  of its current revision (US-35, ``409 compliance_missing``), and approving one needs a sign-off
  of its current version (US-37).
* **The queue** (:func:`queue`) lists what waits for a compliance reviewer: findings about
  protected requirements not yet decided, open change requests on them without a compliance
  approval of the current revision, and protected requirements whose current version is not
  signed off. Done items show who signed off and when.
* **The trail.** Every action on a protected requirement is in the audit log, which a database
  trigger keeps immutable; :func:`record_view` adds *viewing* (NFR-13), at most once a minute per
  person and requirement so a drawer that re-renders does not flood it. :func:`trail` reads it
  back for ``audit.export`` holders, as JSON or CSV, ids and action names only (CR-04); the
  export itself is audited.
"""

import csv
import io
import json
import uuid
from collections.abc import Collection
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.errors import BadRequestError, NotFoundError
from app.graph import deltas, narrator
from app.models import (
    AuditAction,
    AuditLog,
    CandidatePair,
    ChangeRequest,
    Finding,
    FindingStatus,
    Project,
    Requirement,
    RequirementState,
    User,
)
from app.models.change_request import APPROVED, OPEN
from app.models.change_review import APPROVE
from app.services import reviews
from app.services.access import AccessContext

MAX_REASON = 1000
MAX_BULK = 500
VIEW_DEDUPE = timedelta(minutes=1)
PENDING_FINDINGS = (FindingStatus.FLAGGED, FindingStatus.RECLASSIFIED)
NOT_SIGNED = (RequirementState.DEPRECATED, RequirementState.REJECTED)


# ── tagging ─────────────────────────────────────────────────────────────────────────────────
def _clean_reason(reason: str | None, *, required: bool) -> str | None:
    why = (reason or "").strip() or None
    if required and why is None:
        raise BadRequestError("Say why protection is removed", code="reason_required")
    if why is not None and len(why) > MAX_REASON:
        raise BadRequestError(f"A reason is at most {MAX_REASON} characters", code="too_long")
    return why


def _apply(
    db: Session, ctx: AccessContext, requirement: Requirement, protected: bool, reason: str | None
) -> bool:
    """Set the flag (no commit). Returns whether anything changed."""
    if requirement.is_protected == protected:
        return False
    requirement.is_protected = protected
    requirement.protected_by = ctx.user.id if protected else None
    requirement.protected_at = datetime.now(UTC) if protected else None
    requirement.protection_reason = reason if protected else None
    db.add(
        AuditLog(
            workspace_id=ctx.workspace_id,
            actor_id=ctx.user.id,
            requirement_id=requirement.id,
            action=AuditAction.PROTECTION_CHANGED,
            details={"protected": protected, "version": requirement.current_version},
        )
    )
    return True


def set_protection(
    db: Session,
    ctx: AccessContext,
    requirement: Requirement,
    *,
    protected: bool,
    reason: str | None,
) -> Requirement:
    why = _clean_reason(reason, required=not protected)
    if _apply(db, ctx, requirement, protected, why):
        db.commit()
        _announce(db, ctx, requirement.project_id, [requirement], protected)
    return requirement


def protect_many(
    db: Session,
    ctx: AccessContext,
    project: Project,
    *,
    requirement_ids: Collection[uuid.UUID] = (),
    labels: Collection[str] = (),
    reason: str | None = None,
) -> tuple[list[Requirement], list[str]]:
    """Protect requirements of ``project`` by id and/or printed ID, e.g. right after an import.
    Returns the requirements now protected and the printed IDs that matched nothing."""
    if len(requirement_ids) + len(labels) > MAX_BULK:
        raise BadRequestError(f"At most {MAX_BULK} requirements at once", code="too_many")
    why = _clean_reason(reason, required=False)
    conditions = []
    if requirement_ids:
        conditions.append(Requirement.id.in_(list(requirement_ids)))
    wanted = {label.strip() for label in labels if label.strip()}
    if wanted:
        conditions.append(Requirement.source_req_id.in_(wanted))
    if not conditions:
        raise BadRequestError("Name at least one requirement", code="nothing_selected")
    rows = list(
        db.scalars(
            select(Requirement).where(Requirement.project_id == project.id, or_(*conditions))
        )
    )
    found_ids = {r.id for r in rows}
    if set(requirement_ids) - found_ids:
        raise NotFoundError("Requirement not found")  # another project's: does not exist here
    changed = [r for r in rows if _apply(db, ctx, r, True, why)]
    db.commit()
    if changed:
        _announce(db, ctx, project.id, changed, True)
    missing = sorted(wanted - {r.source_req_id for r in rows if r.source_req_id})
    return rows, missing


def _announce(
    db: Session,
    ctx: AccessContext,
    project_id: uuid.UUID,
    requirements: list[Requirement],
    protected: bool,
) -> None:
    labels = sorted(deltas.label_of(r) for r in requirements)
    deltas.publish(
        db,
        project_id,
        deltas.Change(
            requirements={r.id for r in requirements},
            sentences=[narrator.protection_changed(ctx.user.full_name, labels, protected)],
            kind="state",
        ),
        actor=ctx.user,
    )


# ── the queue ───────────────────────────────────────────────────────────────────────────────
@dataclass
class QueueItem:
    kind: str  # "finding", "change_request", "signoff"
    id: uuid.UUID  # the finding, change request or requirement
    requirement_ids: list[uuid.UUID]
    labels: list[str]
    title: str
    status: str  # "awaiting_decision", "awaiting_approval", "approved", "awaiting_signoff"
    since: datetime
    done_by: uuid.UUID | None = None


@dataclass
class Queue:
    pending: list[QueueItem] = field(default_factory=list)
    protected: list[dict[str, Any]] = field(default_factory=list)  # every protected requirement


def _label(requirement: Requirement) -> str:
    return requirement.source_req_id or f"requirement {str(requirement.id)[:8]}"


def queue(db: Session, project: Project) -> Queue:
    protected = {
        r.id: r
        for r in db.scalars(
            select(Requirement)
            .where(Requirement.project_id == project.id, Requirement.is_protected)
            .order_by(Requirement.order_index, Requirement.source_req_id, Requirement.id)
        )
    }
    result = Queue()
    if not protected:
        return result
    ids = list(protected)
    rows = db.execute(
        select(Finding, CandidatePair)
        .outerjoin(CandidatePair, CandidatePair.id == Finding.candidate_pair_id)
        .where(
            Finding.project_id == project.id,
            ~Finding.is_stale,
            Finding.status.in_(PENDING_FINDINGS),
            or_(
                Finding.requirement_id.in_(ids),
                CandidatePair.requirement_a_id.in_(ids),
                CandidatePair.requirement_b_id.in_(ids),
            ),
        )
        .order_by(Finding.created_at, Finding.id)
    ).all()
    others = {
        x
        for _, pair in rows
        if pair is not None
        for x in (pair.requirement_a_id, pair.requirement_b_id)
        if x not in protected
    }
    labels = {r.id: _label(r) for r in protected.values()}
    if others:
        labels.update(
            {
                r.id: _label(r)
                for r in db.scalars(select(Requirement).where(Requirement.id.in_(others)))
            }
        )
    for finding, pair in rows:
        involved = (
            [pair.requirement_a_id, pair.requirement_b_id]
            if pair is not None
            else [finding.requirement_id]
            if finding.requirement_id
            else []
        )
        names = [labels.get(i, "?") for i in involved]
        result.pending.append(
            QueueItem(
                kind="finding",
                id=finding.id,
                requirement_ids=involved,
                labels=names,
                title=f"{finding.category.value} finding on {' and '.join(names)}",
                status="awaiting_decision",
                since=finding.created_at,
            )
        )

    compliance = {u.id for u in reviews.holders(db, project, "protected.signoff")}
    for change in db.scalars(
        select(ChangeRequest)
        .where(ChangeRequest.requirement_id.in_(ids), ChangeRequest.status.in_((OPEN, APPROVED)))
        .order_by(ChangeRequest.created_at)
    ):
        approvals = [
            r
            for reviewer, r in reviews.current_decisions(db, change).items()
            if r.decision == APPROVE and reviewer in compliance
        ]
        label = labels[change.requirement_id]
        result.pending.append(
            QueueItem(
                kind="change_request",
                id=change.id,
                requirement_ids=[change.requirement_id],
                labels=[label],
                title=f"RCR-{change.number} on {label} (revision {change.proposal_revision})",
                status="approved" if approvals else "awaiting_approval",
                since=change.updated_at,
                done_by=approvals[0].reviewer_id if approvals else None,
            )
        )

    for requirement in protected.values():
        signed = requirement.signed_off_version == requirement.current_version
        if not signed and requirement.state not in NOT_SIGNED:
            result.pending.append(
                QueueItem(
                    kind="signoff",
                    id=requirement.id,
                    requirement_ids=[requirement.id],
                    labels=[labels[requirement.id]],
                    title=f"{labels[requirement.id]} v{requirement.current_version} needs a sign-off",
                    status="awaiting_signoff",
                    since=requirement.protected_at or requirement.updated_at,
                )
            )
        result.protected.append(
            {
                "requirement_id": requirement.id,
                "label": labels[requirement.id],
                "state": requirement.state.value,
                "current_version": requirement.current_version,
                "signed_off_version": requirement.signed_off_version,
                "signed_off_by": requirement.signed_off_by,
                "signed_off_at": requirement.signed_off_at,
                "protected_by": requirement.protected_by,
                "protected_at": requirement.protected_at,
                "protection_reason": requirement.protection_reason,
            }
        )
    result.pending.sort(key=lambda item: item.since)
    return result


# ── the trail (NFR-13) ──────────────────────────────────────────────────────────────────────
def record_view(db: Session, ctx: AccessContext, requirement: Requirement, what: str) -> None:
    """Audit that ``ctx.user`` looked at a protected requirement (``what``: detail, versions…)."""
    if not requirement.is_protected:
        return
    recent = db.scalar(
        select(AuditLog.id)
        .where(
            AuditLog.actor_id == ctx.user.id,
            AuditLog.requirement_id == requirement.id,
            AuditLog.action == AuditAction.VIEWED_PROTECTED,
            AuditLog.at > datetime.now(UTC) - VIEW_DEDUPE,
        )
        .limit(1)
    )
    if recent is not None:
        return
    db.add(
        AuditLog(
            workspace_id=ctx.workspace_id,
            actor_id=ctx.user.id,
            requirement_id=requirement.id,
            action=AuditAction.VIEWED_PROTECTED,
            details={"view": what},
        )
    )
    db.commit()


@dataclass(frozen=True)
class TrailRow:
    at: datetime
    actor_id: uuid.UUID
    actor_name: str | None
    action: str
    requirement_id: uuid.UUID | None
    requirement_label: str | None
    finding_id: uuid.UUID | None
    details: dict[str, Any]


def _ever_protected(db: Session, project: Project) -> dict[uuid.UUID, Requirement]:
    """Requirements protected now, or at any time (a protection change was audited)."""
    once = select(AuditLog.requirement_id).where(
        AuditLog.workspace_id == project.workspace_id,
        AuditLog.action == AuditAction.PROTECTION_CHANGED,
        AuditLog.requirement_id.is_not(None),
    )
    return {
        r.id: r
        for r in db.scalars(
            select(Requirement).where(
                Requirement.project_id == project.id,
                or_(Requirement.is_protected, Requirement.id.in_(once)),
            )
        )
    }


def trail(
    db: Session,
    project: Project,
    *,
    requirement_id: uuid.UUID | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 5000,
) -> list[TrailRow]:
    """Every audited action on the project's protected requirements, oldest first."""
    requirements = _ever_protected(db, project)
    if requirement_id is not None:
        requirements = {k: v for k, v in requirements.items() if k == requirement_id}
    if not requirements:
        return []
    ids = list(requirements)
    findings = (
        select(Finding.id)
        .outerjoin(CandidatePair, CandidatePair.id == Finding.candidate_pair_id)
        .where(
            or_(
                Finding.requirement_id.in_(ids),
                CandidatePair.requirement_a_id.in_(ids),
                CandidatePair.requirement_b_id.in_(ids),
            )
        )
    )
    changes = [
        str(c)
        for c in db.scalars(select(ChangeRequest.id).where(ChangeRequest.requirement_id.in_(ids)))
    ]
    about = [AuditLog.requirement_id.in_(ids), AuditLog.finding_id.in_(findings)]
    if changes:
        about.append(AuditLog.details["change_request_id"].astext.in_(changes))
    query = (
        select(AuditLog, User.full_name)
        .outerjoin(User, User.id == AuditLog.actor_id)
        .where(AuditLog.workspace_id == project.workspace_id, or_(*about))
        .order_by(AuditLog.at, AuditLog.id)
        .limit(limit)
    )
    if since is not None:
        query = query.where(AuditLog.at >= since)
    if until is not None:
        query = query.where(AuditLog.at <= until)
    return [
        TrailRow(
            at=row.at,
            actor_id=row.actor_id,
            actor_name=name,
            action=row.action,
            requirement_id=row.requirement_id,
            requirement_label=_label(requirements[row.requirement_id])
            if row.requirement_id in requirements
            else None,
            finding_id=row.finding_id,
            details=dict(row.details or {}),
        )
        for row, name in db.execute(query)
    ]


def record_export(
    db: Session, ctx: AccessContext, project: Project, *, fmt: str, rows: int, **filters: object
) -> None:
    db.add(
        AuditLog(
            workspace_id=project.workspace_id,
            actor_id=ctx.user.id,
            action=AuditAction.AUDIT_EXPORTED,
            details={
                "project_id": str(project.id),
                "format": fmt,
                "rows": rows,
                **{k: str(v) for k, v in filters.items() if v is not None},
            },
        )
    )
    db.commit()


CSV_COLUMNS = (
    "at",
    "actor",
    "actor_id",
    "action",
    "requirement",
    "requirement_id",
    "finding_id",
    "details",
)


# A cell starting with one of these is a formula in Excel and LibreOffice. Names and printed IDs
# are chosen by users (a display name, an ID in an uploaded document), so a reviewer opening the
# trail must never run one: prefix it with an apostrophe (CWE-1236, "CSV injection").
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def _cell(value: str) -> str:
    return f"'{value}" if value.startswith(_FORMULA_START) else value


def as_csv(rows: list[TrailRow]) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for row in rows:
        writer.writerow(
            [
                row.at.astimezone(UTC).isoformat(),
                _cell(row.actor_name or ""),
                str(row.actor_id),
                row.action,
                _cell(row.requirement_label or ""),
                str(row.requirement_id or ""),
                str(row.finding_id or ""),
                json.dumps(row.details, sort_keys=True),
            ]
        )
    return out.getvalue()
