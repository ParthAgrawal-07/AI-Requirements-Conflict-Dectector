"""Human review of findings (Parth — US-10, FR-18–FR-21, CR-19; ADR-06 human in the loop).

A finding is reviewed with one of six actions; the review states are those of US-10 (``flagged``
is *open*, ``confirmed`` is *accepted*):

==============  =======================================  ====================================
Action          From                                      To
==============  =======================================  ====================================
``confirm``     flagged, reclassified                     confirmed
``dismiss``     flagged, confirmed, reclassified          dismissed — a reason is required
``merge``       flagged, confirmed, reclassified          merged — into another live finding
                                                          of the same project and category
``reclassify``  flagged, confirmed, reclassified          reclassified — new category, of the
                                                          same kind (pair or single requirement)
``reopen``      confirmed, dismissed, merged,             flagged
                reclassified
``escalate``    flagged, confirmed, reclassified          unchanged — audited, for attention
==============  =======================================  ====================================

* **The original AI finding is kept** (FR-20): ``original_ai_output`` is never touched, and every
  decision is a ``finding_reviews`` row with the status and category before and after.
* **Protected requirements** (FR-21, CR-19): a finding about one can only be acted on by someone
  who holds ``finding.review`` *for protected requirements* **and** ``protected.signoff`` — the
  Compliance Reviewer by default. Nobody else, not even the Owner, may dismiss or merge it.
  Holders of a protected-only ``finding.review`` may act on nothing else.
* Stale findings (superseded by an edit) are history and cannot be reviewed.
* Every decision is audited (ids only) and published to the map as a ``graph.delta``.
"""

import uuid
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.graph import deltas, narrator
from app.graph.service import KIND
from app.models import (
    AuditAction,
    AuditLog,
    CandidatePair,
    Finding,
    FindingCategory,
    FindingReview,
    FindingStatus,
    Requirement,
)
from app.services.access import AccessContext

ReviewAction = Literal["confirm", "dismiss", "merge", "reclassify", "reopen", "escalate"]

F = FindingStatus
LIVE = (F.FLAGGED, F.CONFIRMED, F.RECLASSIFIED)
_FROM: dict[str, tuple[FindingStatus, ...]] = {
    "confirm": (F.FLAGGED, F.RECLASSIFIED),
    "dismiss": LIVE,
    "merge": LIVE,
    "reclassify": LIVE,
    "reopen": (F.CONFIRMED, F.DISMISSED, F.MERGED, F.RECLASSIFIED),
    "escalate": LIVE,
}
_AUDIT = {
    "confirm": AuditAction.CONFIRMED,
    "dismiss": AuditAction.DISMISSED,
    "merge": AuditAction.MERGED,
    "reclassify": AuditAction.RECLASSIFIED,
    "reopen": AuditAction.FINDING_REOPENED,
    "escalate": AuditAction.ESCALATED,
}
PAIR_CATEGORIES = frozenset(
    {FindingCategory.CONFLICTING, FindingCategory.DUPLICATE, FindingCategory.DEPENDENT}
)
SINGLE_CATEGORIES = frozenset({FindingCategory.AMBIGUOUS, FindingCategory.INCOMPLETE})
MIN_REASON = 3


def involved_requirements(db: Session, finding: Finding) -> list[Requirement]:
    if finding.candidate_pair_id is not None:
        pair = db.get(CandidatePair, finding.candidate_pair_id)
        ids = [pair.requirement_a_id, pair.requirement_b_id] if pair else []
    else:
        ids = [finding.requirement_id] if finding.requirement_id else []
    return [r for r in (db.get(Requirement, i) for i in ids) if r is not None]


def may_review(ctx: AccessContext, *, protected: bool) -> bool:
    """The US-10 guard. Read from permissions, never role names."""
    if protected:
        return ctx.can("finding.review", protected_requirement=True) and ctx.can(
            "protected.signoff"
        )
    return ctx.can("finding.review")


def review(
    db: Session,
    ctx: AccessContext,
    finding_id: uuid.UUID,
    action: ReviewAction,
    *,
    reason: str | None = None,
    category: FindingCategory | None = None,
    merge_into: uuid.UUID | None = None,
) -> FindingReview:
    finding = db.scalar(select(Finding).where(Finding.id == finding_id).with_for_update())
    if finding is None:
        raise NotFoundError("Finding not found")
    requirements = involved_requirements(db, finding)
    protected = any(r.is_protected for r in requirements)
    if not may_review(ctx, protected=protected):
        raise ForbiddenError(
            "Only a compliance reviewer can act on a finding about a protected requirement"
            if protected
            else "You do not have permission to review findings"
        )
    if finding.is_stale:
        raise ConflictError(
            "This finding is out of date: its requirement changed since", code="finding_stale"
        )
    if finding.status not in _FROM[action]:
        raise ConflictError(
            f"'{action}' is not possible on a {finding.status.value} finding",
            code="illegal_review",
        )
    reason = (reason or "").strip() or None
    if action == "dismiss" and (reason is None or len(reason) < MIN_REASON):
        raise BadRequestError("Say why the finding is dismissed", code="reason_required")

    before_status, before_category = finding.status, finding.category
    target: Finding | None = None
    if action == "confirm":
        finding.status = F.CONFIRMED
    elif action == "dismiss":
        finding.status = F.DISMISSED
    elif action == "merge":
        target = _merge_target(db, finding, merge_into)
        finding.status = F.MERGED
        finding.merged_into_id = target.id
    elif action == "reclassify":
        finding.category = _new_category(finding, category)
        finding.status = F.RECLASSIFIED
    elif action == "reopen":
        finding.status = F.FLAGGED
        finding.merged_into_id = None
    finding.reviewed_by = ctx.user.id
    finding.reviewed_at = datetime.now(UTC)

    record = FindingReview(
        finding_id=finding.id,
        actor_id=ctx.user.id,
        action=action,
        from_status=before_status,
        to_status=finding.status,
        from_category=before_category,
        to_category=finding.category,
        reason=reason,
        merged_into_id=target.id if target else None,
        created_at=func.clock_timestamp(),  # decisions in one transaction keep their order
    )
    db.add(record)
    db.add(
        AuditLog(
            workspace_id=ctx.workspace_id,
            actor_id=ctx.user.id,
            finding_id=finding.id,
            action=_AUDIT[action],
            details={
                "from_status": before_status.value,
                "to_status": finding.status.value,
                "from_category": before_category.value,
                "to_category": finding.category.value,
                "merged_into": str(target.id) if target else None,
                "protected": protected,
            },
        )
    )
    db.commit()

    sentence = narrator.reviewed(
        ctx.user.full_name,
        action,
        KIND[before_category],
        sorted(deltas.label_of(r) for r in requirements),
        new_kind=KIND[finding.category] if action == "reclassify" else None,
    )
    deltas.publish(
        db,
        finding.project_id,
        deltas.Change(findings={finding.id}, sentences=[sentence]),
        actor=ctx.user,
    )
    return record


def _merge_target(db: Session, finding: Finding, merge_into: uuid.UUID | None) -> Finding:
    if merge_into is None:
        raise BadRequestError("Name the finding to merge into", code="merge_target_required")
    if merge_into == finding.id:
        raise BadRequestError("A finding cannot be merged into itself", code="merge_into_self")
    target = db.get(Finding, merge_into)
    # Another project's finding does not exist for this request (tenant isolation).
    if target is None or target.project_id != finding.project_id:
        raise NotFoundError("The finding to merge into was not found")
    if target.is_stale or target.status not in LIVE:
        raise ConflictError(
            "Merge into a finding that is still open or accepted", code="merge_target_closed"
        )
    if target.category is not finding.category:
        raise ConflictError(
            "Only findings of the same category describe the same issue",
            code="merge_category_mismatch",
        )
    return target


def _new_category(finding: Finding, category: FindingCategory | None) -> FindingCategory:
    if category is None:
        raise BadRequestError("Choose the new category", code="category_required")
    if category is finding.category:
        raise ConflictError("The finding already has this category", code="no_change")
    allowed = PAIR_CATEGORIES if finding.candidate_pair_id is not None else SINGLE_CATEGORIES
    if category not in allowed:
        raise BadRequestError(
            "A finding about two requirements is Conflicting, Duplicate or Dependent; one about a "
            "single requirement is Ambiguous or Incomplete",
            code="category_kind_mismatch",
        )
    return category


def reviews_of(db: Session, finding_id: uuid.UUID) -> list[FindingReview]:
    return list(
        db.scalars(
            select(FindingReview)
            .where(FindingReview.finding_id == finding_id)
            .order_by(FindingReview.created_at, FindingReview.id)
        )
    )
