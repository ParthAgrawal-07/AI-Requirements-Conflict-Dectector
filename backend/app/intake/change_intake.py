"""Change-request intake (Bansil — US-33, FR-62, FR-89, DR-14; design update §3.2, §7.2).

``POST /requirements/{id}/change-requests`` opens RCR-n against one requirement:

* ``modify`` with the proposed text (it must differ from the current text), or ``deprecate``
  (no text; only an Approved or Implemented requirement can be deprecated);
* ``base_version`` — the version the proposer read. It must still be the current one when the
  request is opened (409 ``base_version_moved`` otherwise: re-read and write again); later moves
  of the requirement are what makes an open request ``needs_update`` (Parth, US-35);
* ``proposal_revision`` = 1, kept with its text in ``change_request_revisions``;
* "Resolves ISS-n": the ``resolves`` numbers plus every "Resolves ISS-n" / "Fixes ISS-n" /
  "Closes ISS-n" in the reason. They must be open issues of the same project; merging the request
  closes them (``resolved_by_merge``).

A rejected or deprecated requirement takes no change requests. ``draft=true`` keeps the request
out of review until its proposer opens it. The consequence checks start when it is opened
(Madhav, US-34). Every request is audited (ids only) and announced as ``change_request.opened``.
"""

import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.consequences import tasks as consequence_tasks
from app.core.errors import BadRequestError, ConflictError
from app.graph import deltas, narrator
from app.models import (
    AuditAction,
    AuditLog,
    ChangeRequest,
    ChangeRequestIssue,
    ChangeRequestRevision,
    Issue,
    Project,
    Requirement,
    RequirementState,
    RequirementVersion,
    User,
)
from app.models.change_request import DEPRECATE, DRAFT, MODIFY, OPEN
from app.realtime import bus
from app.realtime.events import CHANGE_REQUEST_OPENED, change_request_event
from app.services.access import AccessContext

CLOSED_TO_CHANGE = (RequirementState.REJECTED, RequirementState.DEPRECATED)
DEPRECATABLE = (RequirementState.APPROVED, RequirementState.IMPLEMENTED)
RESOLVES = re.compile(r"\b(?:resolves|fixes|closes)\s+ISS-(\d+)\b", re.IGNORECASE)


def key(change_request: ChangeRequest) -> str:
    return f"RCR-{change_request.number}"


def resolved_numbers(reason: str, explicit: Iterable[int] = ()) -> list[int]:
    return sorted({*explicit, *(int(n) for n in RESOLVES.findall(reason))})


@dataclass
class ChangeRequestView:
    change_request: ChangeRequest
    requirement: Requirement
    proposer: User | None
    base_body: str  # the requirement's text at base_version
    issues: list[Issue]


def body_at(db: Session, requirement: Requirement, version: int) -> str:
    """The requirement's text at ``version`` (the current text when no snapshot exists)."""
    snapshot = db.scalar(
        select(RequirementVersion.body_snapshot).where(
            RequirementVersion.requirement_id == requirement.id,
            RequirementVersion.version_no == version,
        )
    )
    return snapshot if snapshot is not None else requirement.body


def resolves(db: Session, change_request_id: uuid.UUID) -> list[Issue]:
    return list(
        db.scalars(
            select(Issue)
            .join(ChangeRequestIssue, ChangeRequestIssue.issue_id == Issue.id)
            .where(ChangeRequestIssue.change_request_id == change_request_id)
            .order_by(Issue.number)
        )
    )


def view(db: Session, change_request: ChangeRequest) -> ChangeRequestView:
    requirement = db.get(Requirement, change_request.requirement_id)
    if requirement is None:  # pragma: no cover — CASCADE removes the request with it
        raise LookupError(change_request.requirement_id)
    return ChangeRequestView(
        change_request,
        requirement,
        db.get(User, change_request.proposer_id),
        body_at(db, requirement, change_request.base_version),
        resolves(db, change_request.id),
    )


def list_change_requests(
    db: Session,
    project_id: uuid.UUID,
    *,
    status: str | None = None,
    requirement_id: uuid.UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[ChangeRequestView], int]:
    query = select(ChangeRequest).where(ChangeRequest.project_id == project_id)
    if status is not None:
        query = query.where(ChangeRequest.status == status)
    if requirement_id is not None:
        query = query.where(ChangeRequest.requirement_id == requirement_id)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(ChangeRequest.number.desc()).limit(limit).offset(offset))
    return [view(db, row) for row in rows], total


def _issues(db: Session, project_id: uuid.UUID, numbers: list[int]) -> list[Issue]:
    if not numbers:
        return []
    found = {
        i.number: i
        for i in db.scalars(
            select(Issue).where(Issue.project_id == project_id, Issue.number.in_(numbers))
        )
    }
    missing = [n for n in numbers if n not in found]
    if missing:
        raise BadRequestError(
            f"No issue {', '.join(f'ISS-{n}' for n in missing)} in this project",
            code="unknown_issue",
        )
    closed = [n for n in numbers if found[n].status != "open"]
    if closed:
        raise BadRequestError(
            f"{', '.join(f'ISS-{n}' for n in closed)} is already closed", code="issue_not_open"
        )
    return [found[n] for n in numbers]


def open_change_request(
    db: Session,
    ctx: AccessContext,
    requirement: Requirement,
    *,
    kind: str,
    reason: str,
    proposed_body: str | None = None,
    proposed_fields: dict[str, Any] | None = None,
    base_version: int | None = None,
    resolves_numbers: Iterable[int] = (),
    draft: bool = False,
) -> ChangeRequest:
    """Open (or draft) RCR-n — committed, then announced."""
    db.refresh(requirement, with_for_update=True)
    if requirement.state in CLOSED_TO_CHANGE:
        raise ConflictError(
            f"A {requirement.state.value.lower()} requirement takes no change requests",
            code="requirement_closed",
        )
    if base_version is not None and base_version != requirement.current_version:
        raise ConflictError(
            f"The requirement is at version {requirement.current_version} now, not "
            f"{base_version}: read it again before proposing a change",
            code="base_version_moved",
        )
    text = (proposed_body or "").strip()
    if kind == MODIFY:
        if not text:
            raise BadRequestError("Write the proposed text", code="proposed_body_required")
        if text == requirement.body.strip():
            raise BadRequestError("The proposed text is the current text", code="no_change")
    elif kind == DEPRECATE:
        if proposed_body is not None:
            raise BadRequestError("A deprecation proposes no text", code="unexpected_body")
        if requirement.state not in DEPRECATABLE:
            raise ConflictError(
                "Only an approved or implemented requirement can be deprecated",
                code="not_in_baseline",
            )
    else:  # pragma: no cover — the schema allows only the two kinds
        raise BadRequestError("Unknown kind", code="unknown_kind")

    project = db.get(Project, requirement.project_id)
    if project is None:  # pragma: no cover
        raise LookupError(requirement.project_id)
    linked = _issues(db, project.id, resolved_numbers(reason, resolves_numbers))
    db.execute(select(Project.id).where(Project.id == project.id).with_for_update())
    number = (
        db.scalar(
            select(func.max(ChangeRequest.number)).where(ChangeRequest.project_id == project.id)
        )
        or 0
    ) + 1
    change_request = ChangeRequest(
        project_id=project.id,
        requirement_id=requirement.id,
        number=number,
        proposer_id=ctx.user.id,
        kind=kind,
        status=DRAFT if draft else OPEN,
        base_version=requirement.current_version,
        proposal_revision=1,
        proposed_body=text if kind == MODIFY else None,
        proposed_fields=proposed_fields,
        reason=reason.strip(),
    )
    db.add(change_request)
    db.flush()
    db.add(
        ChangeRequestRevision(
            change_request_id=change_request.id,
            revision=1,
            proposed_body=change_request.proposed_body,
            reason=change_request.reason,
            author_id=ctx.user.id,
        )
    )
    db.add_all(
        ChangeRequestIssue(change_request_id=change_request.id, issue_id=i.id) for i in linked
    )
    db.add(
        AuditLog(
            workspace_id=project.workspace_id,
            actor_id=ctx.user.id,
            requirement_id=requirement.id,
            action=AuditAction.CHANGE_REQUEST_OPENED,
            details={
                "change_request_id": str(change_request.id),
                "number": number,
                "kind": kind,
                "base_version": change_request.base_version,
                "resolves": [str(i.id) for i in linked],
                "draft": draft,
            },
        )
    )
    db.commit()
    announce_opened(db, change_request, project, requirement, ctx.user)
    if change_request.status == OPEN:
        consequence_tasks.queue_checks(change_request.id)  # Madhav (US-34)
    return change_request


def announce_opened(
    db: Session,
    change_request: ChangeRequest,
    project: Project,
    requirement: Requirement,
    actor: User,
) -> None:
    bus.publish(
        change_request_event(
            CHANGE_REQUEST_OPENED,
            workspace_id=project.workspace_id,
            project_id=project.id,
            change_request_id=change_request.id,
            requirement_id=requirement.id,
            number=change_request.number,
            status=change_request.status,
            proposal_revision=change_request.proposal_revision,
            actor_id=actor.id,
            kind=change_request.kind,
        )
    )
    if change_request.status == DRAFT:
        return
    sentence = narrator.change_requested(
        actor.full_name, change_request.number, deltas.label_of(requirement), change_request.kind
    )
    deltas.publish(
        db,
        project.id,
        deltas.Change(requirements={requirement.id}, sentences=[sentence]),
        actor=actor,
    )
