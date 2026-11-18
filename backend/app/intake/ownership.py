"""Owners, stakeholder groups and ownership requests (Bansil — US-36, FR-59, DR-11).

Every requirement has an owner and a stakeholder group:

* a **post** defaults both to its author (their membership's group); an **import** defaults the
  owner to the uploader until someone reassigns it (``app.services.processing``);
* members who may **reassign** — ``baseline.manage``: analysts, project managers, admins — change
  the owner or group directly (``PATCH /requirements/{id}``);
* any member who may propose (``req.propose``) can **request ownership**; the current owner, or a
  member who could reassign it anyway, accepts or declines.

Owners are who live analysis @mentions (US-31) and who conflict issues, reviews and notifications
reach later, so every change is audited (ids and group names only) and shown on the map.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.graph import deltas, narrator
from app.models import AuditAction, AuditLog, OwnershipRequest, Requirement, User
from app.models.ownership import ACCEPTED, DECLINED, PENDING
from app.services.access import AccessContext, Scope, active_membership, register_scope_resolver

MAX_GROUP = 120


def may_reassign(ctx: AccessContext) -> bool:
    return ctx.can("baseline.manage")


def reassign(
    db: Session,
    ctx: AccessContext,
    requirement_id: uuid.UUID,
    *,
    owner_id: uuid.UUID | None = None,
    set_owner: bool = False,
    group: str | None = None,
    set_group: bool = False,
    commit: bool = True,
) -> list[str]:
    """Change the owner and/or the stakeholder group. ``set_*`` say which were sent, so a group
    can be cleared with ``null`` while an omitted field stays as it is. Returns the delta sentences.

    ``commit=False`` stages the change in the caller's transaction and announces nothing: a PATCH
    that also moves the lifecycle commits both together, so a refused move leaves the owner as it
    was, then calls :func:`announce` with the sentences."""
    if not may_reassign(ctx):
        raise ForbiddenError("Only analysts and managers reassign owners and groups")
    requirement = _locked(db, requirement_id)
    sentences: list[str] = []
    if set_owner and owner_id != requirement.owner_id:
        new_owner = _member(db, ctx.workspace_id, owner_id) if owner_id else None
        _audit(
            db,
            ctx,
            requirement,
            AuditAction.OWNER_CHANGED,
            before=requirement.owner_id,
            after=owner_id,
        )
        requirement.owner_id = owner_id
        sentences.append(
            narrator.owner_changed(
                ctx.user.full_name,
                deltas.label_of(requirement),
                new_owner.full_name if new_owner else None,
            )
        )
    if set_group:
        cleaned = (group or "").strip()[:MAX_GROUP] or None
        if cleaned != requirement.stakeholder_group:
            _audit(
                db,
                ctx,
                requirement,
                AuditAction.GROUP_CHANGED,
                before=requirement.stakeholder_group,
                after=cleaned,
            )
            requirement.stakeholder_group = cleaned
            sentences.append(
                f"{ctx.user.full_name} moved {deltas.label_of(requirement)} to the "
                f"{cleaned or 'no'} group."
            )
    if not commit:
        db.flush()
        return sentences
    db.commit()
    if sentences:
        _publish(db, ctx, requirement, sentences)
    return sentences


def announce(
    db: Session, ctx: AccessContext, requirement_id: uuid.UUID, sentences: list[str]
) -> None:
    """Publish a staged reassignment's delta once the transaction that carried it committed."""
    requirement = db.get(Requirement, requirement_id)
    if sentences and requirement is not None:
        _publish(db, ctx, requirement, sentences)


def request_ownership(
    db: Session, ctx: AccessContext, requirement_id: uuid.UUID, *, note: str | None
) -> OwnershipRequest:
    requirement = _locked(db, requirement_id)
    if requirement.owner_id == ctx.user.id:
        raise ConflictError("You already own this requirement", code="already_owner")
    request = OwnershipRequest(
        requirement_id=requirement.id,
        requester_id=ctx.user.id,
        note=(note or "").strip() or None,
        created_at=func.clock_timestamp(),  # requests in one transaction keep their order
    )
    try:
        with db.begin_nested():
            db.add(request)
            db.flush()
    except IntegrityError:
        raise ConflictError(
            "You already asked to own this requirement", code="already_requested"
        ) from None
    db.add(
        AuditLog(
            workspace_id=ctx.workspace_id,
            actor_id=ctx.user.id,
            requirement_id=requirement.id,
            action=AuditAction.OWNERSHIP_REQUESTED,
            details={"request_id": str(request.id)},
        )
    )
    db.commit()
    return request


def decide(
    db: Session, ctx: AccessContext, request_id: uuid.UUID, *, accept: bool
) -> OwnershipRequest:
    request = db.scalar(
        select(OwnershipRequest).where(OwnershipRequest.id == request_id).with_for_update()
    )
    if request is None:
        raise NotFoundError("Ownership request not found")
    requirement = _locked(db, request.requirement_id)
    if requirement.owner_id != ctx.user.id and not may_reassign(ctx):
        raise ForbiddenError("Only the current owner or a manager decides ownership requests")
    if request.status != PENDING:
        raise ConflictError("This request was already decided", code="already_decided")
    request.status = ACCEPTED if accept else DECLINED
    request.decided_by = ctx.user.id
    request.decided_at = datetime.now(UTC)
    db.add(
        AuditLog(
            workspace_id=ctx.workspace_id,
            actor_id=ctx.user.id,
            requirement_id=requirement.id,
            action=AuditAction.OWNERSHIP_DECIDED,
            details={"request_id": str(request.id), "accepted": accept},
        )
    )
    sentences: list[str] = []
    if accept:
        requester = _member(db, ctx.workspace_id, request.requester_id)
        _audit(
            db,
            ctx,
            requirement,
            AuditAction.OWNER_CHANGED,
            before=requirement.owner_id,
            after=requester.id,
        )
        requirement.owner_id = requester.id
        sentences.append(
            narrator.owner_changed(
                ctx.user.full_name, deltas.label_of(requirement), requester.full_name
            )
        )
    db.commit()
    if sentences:
        _publish(db, ctx, requirement, sentences)
    return request


def list_requests(db: Session, requirement_id: uuid.UUID) -> list[OwnershipRequest]:
    return list(
        db.scalars(
            select(OwnershipRequest)
            .where(OwnershipRequest.requirement_id == requirement_id)
            .order_by(OwnershipRequest.created_at, OwnershipRequest.id)
        )
    )


def _locked(db: Session, requirement_id: uuid.UUID) -> Requirement:
    requirement = db.scalar(
        select(Requirement).where(Requirement.id == requirement_id).with_for_update()
    )
    if requirement is None:
        raise NotFoundError("Requirement not found")
    return requirement


def _member(db: Session, workspace_id: uuid.UUID, user_id: uuid.UUID) -> User:
    """An active member of the workspace — an owner must be able to see what they own."""
    membership = active_membership(db, user_id, workspace_id)
    if membership is None:
        raise BadRequestError("The owner must be a member of this workspace", code="unknown_owner")
    return membership.user


def _audit(
    db: Session,
    ctx: AccessContext,
    requirement: Requirement,
    action: AuditAction,
    *,
    before: object,
    after: object,
) -> None:
    db.add(
        AuditLog(
            workspace_id=ctx.workspace_id,
            actor_id=ctx.user.id,
            requirement_id=requirement.id,
            action=action,
            details={
                "from": str(before) if before is not None else None,
                "to": str(after) if after is not None else None,
            },
        )
    )


def _publish(
    db: Session, ctx: AccessContext, requirement: Requirement, sentences: list[str]
) -> None:
    deltas.publish(
        db,
        requirement.project_id,
        deltas.Change(requirements={requirement.id}, sentences=sentences),
        actor=ctx.user,
    )


def _request_scope(db: Session, request_id: uuid.UUID) -> Scope | None:
    from app.models import Project

    row = db.execute(
        select(Project.workspace_id, Project.id)
        .join(Requirement, Requirement.project_id == Project.id)
        .join(OwnershipRequest, OwnershipRequest.requirement_id == Requirement.id)
        .where(OwnershipRequest.id == request_id)
    ).first()
    return None if row is None else Scope(row[0], row[1])


register_scope_resolver("ownership_request_id", _request_scope)
