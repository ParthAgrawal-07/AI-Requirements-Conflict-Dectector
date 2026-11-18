"""Requirement lifecycle (Parth — US-37, FR-61, FR-98, FR-21, DR-13; design update §7.1).

::

    Proposed ──start review──▶ Under review ──approve──▶ Approved ──mark implemented──▶ Implemented
       │                          │
       └──withdraw (author)──▶ Rejected ◀──reject (reason)──┘
    Approved / Implemented ──▶ Deprecated     only through an approved deprecation request (S4)

Who may do what is decided by **permissions**, never role names:

=================================  ==================  ========================================
Move                               Permission          Extra condition
=================================  ==================  ========================================
Proposed → Under review            ``baseline.manage``
Under review → Approved            ``baseline.manage`` the agreement rules below
Under review → Rejected            ``baseline.manage`` a reason
Proposed → Rejected (withdraw)     ``req.propose``     only the requirement's author
Approved → Implemented             ``req.implement``
=================================  ==================  ========================================

**Agreement rules for approval** (FR-98, the parts that exist before change requests):

1. an analysis has completed on the **current** text — its single checks ran on this version and
   no comparison with a neighbour is pending, failed or for an older version;
2. no High-severity finding about it is open, unless the approver records an accepted risk with a
   reason;
3. the approver decided on this exact text — the request names the ``version`` it read, and a
   different current version is a 409 (someone edited it meanwhile);
4. a **protected** requirement needs a compliance reviewer's sign-off on that version (FR-21).

Required reviewers (``projects.required_approvals``) arrive with change requests (US-35, S4).
Every move writes a ``requirement_transitions`` row and an audit row, then a ``graph.delta``.
Only Approved and Implemented requirements form the baseline (DR-13); Rejected and Deprecated
ones are never analysed again.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import BadRequestError, ConflictError, ForbiddenError
from app.graph import deltas, narrator
from app.models import (
    AuditAction,
    AuditLog,
    CandidatePair,
    ClassificationStatus,
    Finding,
    FindingStatus,
    Requirement,
    RequirementState,
    RequirementTransition,
    Severity,
)
from app.services.access import AccessContext

S = RequirementState
MIN_REASON = 3


@dataclass(frozen=True)
class Move:
    permission: str
    needs_reason: bool = False
    author_only: bool = False


MOVES: dict[tuple[RequirementState, RequirementState], Move] = {
    (S.PROPOSED, S.UNDER_REVIEW): Move("baseline.manage"),
    (S.UNDER_REVIEW, S.APPROVED): Move("baseline.manage"),
    (S.UNDER_REVIEW, S.REJECTED): Move("baseline.manage", needs_reason=True),
    (S.PROPOSED, S.REJECTED): Move("req.propose", author_only=True),
    (S.APPROVED, S.IMPLEMENTED): Move("req.implement"),
}
# In the state machine, but only an approved change request may make them (US-35, Sprint 4).
VIA_CHANGE_REQUEST = frozenset({(S.APPROVED, S.DEPRECATED), (S.IMPLEMENTED, S.DEPRECATED)})
OPEN = (FindingStatus.FLAGGED, FindingStatus.CONFIRMED, FindingStatus.RECLASSIFIED)


@dataclass(frozen=True)
class Readiness:
    """How far a requirement is from being approvable (FR-98), for the API and the drawer."""

    analysis_current: bool
    open_high_findings: list[uuid.UUID] = field(default_factory=list)
    needs_signoff: bool = False  # protected and not signed off on the current version


def readiness(db: Session, requirement: Requirement) -> Readiness:
    version = requirement.current_version
    behind = db.scalar(
        select(CandidatePair.id)
        .where(
            or_(
                (CandidatePair.requirement_a_id == requirement.id)
                & (
                    (CandidatePair.classification_status != ClassificationStatus.DONE)
                    | CandidatePair.a_version.is_distinct_from(version)
                ),
                (CandidatePair.requirement_b_id == requirement.id)
                & (
                    (CandidatePair.classification_status != ClassificationStatus.DONE)
                    | CandidatePair.b_version.is_distinct_from(version)
                ),
            )
        )
        .limit(1)
    )
    analysed = requirement.single_checked_version == version and behind is None
    return Readiness(
        analysis_current=analysed,
        open_high_findings=_open_high_findings(db, requirement),
        needs_signoff=requirement.is_protected and requirement.signed_off_version != version,
    )


def _open_high_findings(db: Session, requirement: Requirement) -> list[uuid.UUID]:
    pairs = select(CandidatePair.id).where(
        or_(
            CandidatePair.requirement_a_id == requirement.id,
            CandidatePair.requirement_b_id == requirement.id,
        )
    )
    return list(
        db.scalars(
            select(Finding.id)
            .where(
                or_(Finding.requirement_id == requirement.id, Finding.candidate_pair_id.in_(pairs)),
                Finding.is_stale.is_(False),
                Finding.status.in_(OPEN),
                Finding.severity == Severity.HIGH,
            )
            .order_by(Finding.created_at)
        )
    )


def author_id_of(db: Session, requirement: Requirement) -> uuid.UUID | None:
    author = deltas.author_of(db, requirement)
    return author.id if author else None


def allowed_moves(
    db: Session, ctx: AccessContext, requirement: Requirement
) -> list[RequirementState]:
    """The states the caller may try to move this requirement to (the drawer's buttons). The
    agreement rules are checked on the move itself and explained by :func:`readiness`."""
    allowed: list[RequirementState] = []
    for (source, target), move in MOVES.items():
        if source is not requirement.state or not ctx.can(move.permission):
            continue
        if move.author_only and author_id_of(db, requirement) != ctx.user.id:
            continue
        allowed.append(target)
    return allowed


def transition(
    db: Session,
    ctx: AccessContext,
    requirement_id: uuid.UUID,
    target: RequirementState,
    *,
    version: int,
    reason: str | None = None,
    accepted_risk: bool = False,
) -> RequirementTransition:
    """Move a requirement to ``target``, or raise (403 not allowed, 409 not now, 400 bad input)."""
    requirement = db.scalar(
        select(Requirement).where(Requirement.id == requirement_id).with_for_update()
    )
    if requirement is None:  # the access layer resolved it a moment ago; defensive
        raise ConflictError("The requirement no longer exists", code="gone")
    source = requirement.state
    if source is target:
        raise ConflictError(f"The requirement is already {target.value}", code="no_change")
    if (source, target) in VIA_CHANGE_REQUEST:
        raise ConflictError(
            "Deprecating an agreed requirement needs an approved deprecation request",
            code="needs_change_request",
        )
    move = MOVES.get((source, target))
    if move is None:
        raise ConflictError(
            f"A requirement cannot go from {source.value} to {target.value}",
            code="illegal_transition",
        )
    if not ctx.can(move.permission):
        raise ForbiddenError()
    if move.author_only and author_id_of(db, requirement) != ctx.user.id:
        raise ForbiddenError("Only its author can withdraw a proposed requirement")
    if version != requirement.current_version:
        raise ConflictError(
            "The requirement changed since you read it; review the current text",
            code="version_changed",
        )
    reason = (reason or "").strip() or None
    if (move.needs_reason or accepted_risk) and (reason is None or len(reason) < MIN_REASON):
        raise BadRequestError("Give a reason for this decision", code="reason_required")

    risk_taken = False
    if target is S.APPROVED:
        state = readiness(db, requirement)
        if not state.analysis_current:
            raise ConflictError(
                "Analysis has not finished on the current text", code="analysis_not_current"
            )
        if state.needs_signoff:
            raise ConflictError(
                "A compliance reviewer must sign off this version first", code="signoff_required"
            )
        if state.open_high_findings:
            if not accepted_risk:
                raise ConflictError(
                    "A High-severity finding is open; resolve it or accept the risk with a reason",
                    code="open_high_severity",
                )
            risk_taken = True

    record = RequirementTransition(
        requirement_id=requirement.id,
        from_state=source,
        to_state=target,
        version=requirement.current_version,
        actor_id=ctx.user.id,
        reason=reason,
        accepted_risk=risk_taken,
        # Wall-clock time, not the transaction's: moves made in one transaction keep their order.
        created_at=func.clock_timestamp(),
    )
    requirement.state = target
    db.add(record)
    db.add(
        AuditLog(
            workspace_id=ctx.workspace_id,
            actor_id=ctx.user.id,
            requirement_id=requirement.id,
            action=AuditAction.STATE_CHANGED,
            details={
                "from": source.value,
                "to": target.value,
                "version": requirement.current_version,
                "accepted_risk": risk_taken,
            },
        )
    )
    db.commit()
    deltas.publish(
        db,
        requirement.project_id,
        deltas.Change(
            requirements={requirement.id},
            sentences=[
                narrator.moved(ctx.user.full_name, deltas.label_of(requirement), target.value)
            ],
        ),
        actor=ctx.user,
    )
    return record


def sign_off(
    db: Session, ctx: AccessContext, requirement_id: uuid.UUID, *, version: int
) -> Requirement:
    """A compliance reviewer signs off the current text of a protected requirement (FR-21)."""
    requirement = db.scalar(
        select(Requirement).where(Requirement.id == requirement_id).with_for_update()
    )
    if requirement is None:
        raise ConflictError("The requirement no longer exists", code="gone")
    if not requirement.is_protected:
        raise ConflictError("Only protected requirements need a sign-off", code="not_protected")
    if version != requirement.current_version:
        raise ConflictError(
            "The requirement changed since you read it; review the current text",
            code="version_changed",
        )
    if requirement.signed_off_version == version:
        return requirement
    requirement.signed_off_version = version
    requirement.signed_off_by = ctx.user.id
    requirement.signed_off_at = datetime.now(UTC)
    db.add(
        AuditLog(
            workspace_id=ctx.workspace_id,
            actor_id=ctx.user.id,
            requirement_id=requirement.id,
            action=AuditAction.SIGNED_OFF,
            details={"version": version},
        )
    )
    db.commit()
    return requirement


def history(db: Session, requirement_id: uuid.UUID) -> list[RequirementTransition]:
    return list(
        db.scalars(
            select(RequirementTransition)
            .where(RequirementTransition.requirement_id == requirement_id)
            .order_by(RequirementTransition.created_at, RequirementTransition.id)
        )
    )
