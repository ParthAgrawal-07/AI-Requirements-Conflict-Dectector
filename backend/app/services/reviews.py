"""Who reviews a change request, and their reviews (Parth — US-35, FR-65, FR-66, FR-98, SX-13).

**ReviewPolicy** is the only place that knows who must review (design update §3.2):

* **required** — the owner of the changed requirement; the owners of requirements in a *direct
  conflict* with it; a **compliance reviewer** (``protected.signoff``) when it is protected;
  and members who may merge (``rcr.merge``), in name order, until ``projects.required_approvals``
  people are asked (``merge_quota``);
* **optional** — the owners of requirements affected further away (``transitive``), and anyone
  added by hand (``requested``).

The proposer is never a reviewer (SX-13), and only current members holding ``rcr.review`` are
asked. Requests are created when a change request opens and kept up to date when its proposal
changes.

**Reviews** — ``approve``, ``request_changes`` (with a reason) or ``comment``, optionally with
inline comments on the proposal, bound to the ``proposal_revision`` and base version they were
given on. Editing the proposal therefore *dismisses* earlier reviews without deleting them
(FR-98). The proposer cannot approve; on a protected requirement only a compliance reviewer's
approval satisfies the compliance requirement (CR-19). After every review the request's status is
recomputed by :func:`app.services.change_requests.refresh_status`.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.consequences.impact import ImpactAnalyzer
from app.core.errors import AppError, BadRequestError, ConflictError, ForbiddenError
from app.models import (
    AuditAction,
    AuditLog,
    ChangeRequest,
    Membership,
    Project,
    Requirement,
    Review,
    ReviewComment,
    ReviewRequest,
    User,
)
from app.models.change_request import ACTIVE, DRAFT
from app.models.change_review import APPROVE, COMMENT, REQUEST_CHANGES
from app.search.relations import RelationKind
from app.services.access import AccessContext, Scope, build_access_context


@dataclass(frozen=True)
class Wanted:
    reviewer_id: uuid.UUID
    required: bool
    reason: str


def holders(db: Session, project: Project, permission: str) -> list[User]:
    """Current members whose effective role in ``project`` grants ``permission`` freely."""
    users = db.scalars(
        select(User)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.workspace_id == project.workspace_id, Membership.ended_at.is_(None))
        .order_by(User.full_name, User.id)
    )
    scope = Scope(project.workspace_id, project.id)
    return [u for u in users if build_access_context(db, u, scope).can(permission)]


class ReviewPolicy:
    def __init__(self, db: Session) -> None:
        self.db = db

    def reviewers(self, change_request: ChangeRequest) -> list[Wanted]:
        db = self.db
        requirement = db.get(Requirement, change_request.requirement_id)
        project = db.get(Project, change_request.project_id)
        if requirement is None or project is None:  # pragma: no cover
            return []
        may_review = {u.id for u in holders(db, project, "rcr.review")}
        wanted: dict[uuid.UUID, Wanted] = {}

        def ask(user_id: uuid.UUID | None, *, required: bool, reason: str) -> None:
            if (
                user_id is None
                or user_id == change_request.proposer_id
                or user_id not in may_review
            ):
                return
            current = wanted.get(user_id)
            if current is None or (required and not current.required):
                wanted[user_id] = Wanted(user_id, required, reason)

        ask(requirement.owner_id, required=True, reason="owner")
        impact = ImpactAnalyzer(db).analyse(requirement, kind=change_request.kind)
        for affected in impact.affected:
            if affected.depth == 1 and affected.relation is RelationKind.CONFLICT:
                ask(affected.owner_id, required=True, reason="direct_conflict")
        if requirement.is_protected:
            for user in holders(db, project, "protected.signoff"):
                ask(user.id, required=True, reason="compliance")
        for user in holders(db, project, "rcr.merge"):
            if sum(1 for w in wanted.values() if w.required) >= project.required_approvals:
                break
            ask(user.id, required=True, reason="merge_quota")
        for affected in impact.affected:
            if affected.depth == 2 or affected.relation is not RelationKind.CONFLICT:
                ask(affected.owner_id, required=False, reason="transitive")
        return list(wanted.values())

    def request(self, change_request: ChangeRequest) -> list[ReviewRequest]:
        """Create the review requests the policy asks for (never removes a hand-added one)."""
        db = self.db
        existing = {
            r.reviewer_id: r
            for r in db.scalars(
                select(ReviewRequest).where(ReviewRequest.change_request_id == change_request.id)
            )
        }
        for want in self.reviewers(change_request):
            row = existing.get(want.reviewer_id)
            if row is None:
                row = ReviewRequest(
                    change_request_id=change_request.id,
                    reviewer_id=want.reviewer_id,
                    required=want.required,
                    reason=want.reason,
                )
                db.add(row)
                existing[want.reviewer_id] = row
            elif want.required and not row.required:
                row.required, row.reason = True, want.reason
        db.commit()
        return list(existing.values())


def requests_of(db: Session, change_request_id: uuid.UUID) -> list[ReviewRequest]:
    return list(
        db.scalars(
            select(ReviewRequest)
            .where(ReviewRequest.change_request_id == change_request_id)
            .order_by(ReviewRequest.required.desc(), ReviewRequest.created_at)
        )
    )


def reviews_of(db: Session, change_request_id: uuid.UUID) -> list[Review]:
    return list(
        db.scalars(
            select(Review)
            .where(Review.change_request_id == change_request_id)
            .order_by(Review.created_at, Review.id)
        )
    )


def comments_of(db: Session, review_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[ReviewComment]]:
    result: dict[uuid.UUID, list[ReviewComment]] = {}
    if review_ids:
        for row in db.scalars(select(ReviewComment).where(ReviewComment.review_id.in_(review_ids))):
            result.setdefault(row.review_id, []).append(row)
    return result


def current_decisions(db: Session, change_request: ChangeRequest) -> dict[uuid.UUID, Review]:
    """Each reviewer's latest approve / request-changes on the current proposal revision and
    base version. Comments decide nothing; older revisions are dismissed."""
    latest: dict[uuid.UUID, Review] = {}
    for review in reviews_of(db, change_request.id):
        if (
            review.decision != COMMENT
            and review.proposal_revision == change_request.proposal_revision
            and review.reviewed_base_version == change_request.base_version
        ):
            latest[review.reviewer_id] = review
    return latest


def add_reviewer(
    db: Session, ctx: AccessContext, change_request: ChangeRequest, reviewer_id: uuid.UUID
) -> ReviewRequest:
    """Ask one more person (optional reviewer, ``requested``): the proposer or a merger may."""
    if ctx.user.id != change_request.proposer_id and not ctx.can("rcr.merge"):
        raise ForbiddenError("Only the proposer or a member who may merge can ask for reviewers")
    if reviewer_id == change_request.proposer_id:
        raise BadRequestError("The proposer cannot review their own change", code="self_review")
    project = db.get(Project, change_request.project_id)
    if project is None or reviewer_id not in {u.id for u in holders(db, project, "rcr.review")}:
        raise BadRequestError("They cannot review change requests here", code="not_a_reviewer")
    row = db.get(ReviewRequest, (change_request.id, reviewer_id))
    if row is None:
        row = ReviewRequest(
            change_request_id=change_request.id,
            reviewer_id=reviewer_id,
            required=False,
            reason="requested",
        )
        db.add(row)
        db.commit()
    return row


def review(
    db: Session,
    ctx: AccessContext,
    change_request: ChangeRequest,
    *,
    decision: str,
    rationale: str | None = None,
    inline: list[dict[str, object]] | None = None,
) -> Review:
    """Record a review (committed). The caller recomputes the status and announces it."""
    if change_request.status not in ACTIVE or change_request.status == DRAFT:
        raise ConflictError("Only an open change request can be reviewed", code="not_open")
    if decision == APPROVE and ctx.user.id == change_request.proposer_id:
        raise AppError(
            "You cannot approve your own change request", status_code=403, code="self_approval"
        )
    if decision == REQUEST_CHANGES and not (rationale and rationale.strip()):
        raise BadRequestError("Say what should change", code="rationale_required")
    proposal = change_request.proposed_body or ""
    record = Review(
        change_request_id=change_request.id,
        reviewer_id=ctx.user.id,
        decision=decision,
        rationale=(rationale or "").strip() or None,
        proposal_revision=change_request.proposal_revision,
        reviewed_base_version=change_request.base_version,
    )
    db.add(record)
    db.flush()
    for item in inline or []:
        start, end = item.get("start_offset"), item.get("end_offset")
        if isinstance(end, int) and item.get("field") == "statement" and end > len(proposal):
            raise BadRequestError(
                "The comment points past the end of the proposal", code="bad_offsets"
            )
        db.add(
            ReviewComment(
                review_id=record.id,
                field=str(item.get("field") or "statement"),
                start_offset=start if isinstance(start, int) else None,
                end_offset=end if isinstance(end, int) else None,
                body=str(item.get("body") or "").strip(),
            )
        )
    db.add(
        AuditLog(
            workspace_id=ctx.workspace_id,
            actor_id=ctx.user.id,
            requirement_id=change_request.requirement_id,
            action=AuditAction.CHANGE_REQUEST_REVIEWED,
            details={
                "change_request_id": str(change_request.id),
                "decision": decision,
                "proposal_revision": change_request.proposal_revision,
            },
        )
    )
    db.commit()
    return record
