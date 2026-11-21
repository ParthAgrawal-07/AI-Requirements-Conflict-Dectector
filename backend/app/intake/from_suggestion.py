"""From an accepted AI suggestion to a change (Bansil — US-51 wiring, US-45, US-33; DR-04).

Accepting a suggestion (``POST /suggestions/{s}/feedback``) changes nothing: it answers with a
*pre-fill*. The member then opens what the pre-fill says, through the normal intake:

* a **change request** on the target requirement — ``POST /requirements/{r}/change-requests``
  with ``source_suggestion_id``; the finding's auto conflict issue is added to *Resolves*, so the
  merge closes it;
* or, for their own Proposed requirement, a **new post that supersedes it** —
  ``POST /projects/{p}/requirements`` with ``supersedes`` and ``source_suggestion_id``; the old
  proposal is rejected with "Superseded by REQ-n".

Either way the member's acceptance must be on record (the feedback is the evidence the CP2
study counts), the suggestion must still be the live one, and an option must target that
requirement. Text that still holds a ``[TBD — confirm]`` placeholder is refused everywhere: the
AI marks what a person has to supply.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.classification.suggest import TBD
from app.core.errors import BadRequestError, ConflictError, ForbiddenError
from app.models import (
    AuditAction,
    AuditLog,
    Finding,
    Issue,
    Requirement,
    RequirementState,
    RequirementTransition,
    User,
)
from app.models.suggestion import ACCEPTED, ACCEPTED_EDITED, READY, Suggestion, SuggestionFeedback

SUPERSEDABLE = (RequirementState.PROPOSED, RequirementState.UNDER_REVIEW)


def refuse_placeholders(text: str | None) -> None:
    if text and TBD in text:
        raise BadRequestError(
            f"Replace every {TBD} with the value it stands for first", code="tbd_unfilled"
        )


def accepted_suggestion(
    db: Session, user: User, requirement: Requirement, suggestion_id: uuid.UUID
) -> Suggestion:
    """The suggestion a change to ``requirement`` comes from — after the checks above."""
    suggestion = db.get(Suggestion, suggestion_id)
    if suggestion is None or suggestion.project_id != requirement.project_id:
        raise BadRequestError("That suggestion is not in this project", code="unknown_suggestion")
    if suggestion.status != READY:
        raise ConflictError(
            "That suggestion was replaced or is not ready", code="suggestion_unusable"
        )
    if not any(o.get("target_requirement_id") == str(requirement.id) for o in suggestion.options):
        raise BadRequestError(
            "No option of that suggestion changes this requirement", code="suggestion_mismatch"
        )
    accepted = db.scalar(
        select(SuggestionFeedback.id).where(
            SuggestionFeedback.suggestion_id == suggestion.id,
            SuggestionFeedback.user_id == user.id,
            SuggestionFeedback.action.in_((ACCEPTED, ACCEPTED_EDITED)),
        )
    )
    if accepted is None:
        raise ConflictError("Accept the suggestion first", code="not_accepted")
    return suggestion


def issue_of(db: Session, suggestion: Suggestion) -> Issue | None:
    """The finding's open auto conflict issue, which the change will resolve."""
    from app.services.issues import auto_issue_of

    finding = db.get(Finding, suggestion.finding_id)
    issue = auto_issue_of(db, finding) if finding else None
    return issue if issue is not None and issue.status == "open" else None


def check_supersede(
    db: Session, author: User, project_id: uuid.UUID, requirement_id: uuid.UUID
) -> Requirement:
    """The author's own open proposal that a new post will replace."""
    old = db.scalar(
        select(Requirement).where(
            Requirement.id == requirement_id, Requirement.project_id == project_id
        )
    )
    if old is None:
        raise BadRequestError(
            "The requirement to supersede was not found", code="unknown_requirement"
        )
    if old.state not in SUPERSEDABLE:
        raise ConflictError(
            "Only a Proposed requirement is superseded by a post; change an approved one with "
            "a change request",
            code="not_a_proposal",
        )
    if old.owner_id != author.id:
        raise ForbiddenError("Only its owner can supersede a proposal")
    return old


def supersede(
    db: Session, old: Requirement, new: Requirement, author: User, workspace_id: uuid.UUID
) -> None:
    """Reject ``old`` in favour of ``new`` (no commit: part of the post's transaction)."""
    reason = f"Superseded by {new.source_req_id or 'a new post'}"
    db.add(
        RequirementTransition(
            requirement_id=old.id,
            from_state=old.state,
            to_state=RequirementState.REJECTED,
            version=old.current_version,
            actor_id=author.id,
            reason=reason,
        )
    )
    old.state = RequirementState.REJECTED
    db.add(
        AuditLog(
            workspace_id=workspace_id,
            actor_id=author.id,
            requirement_id=old.id,
            action=AuditAction.STATE_CHANGED,
            details={"to": RequirementState.REJECTED.value, "superseded_by": str(new.id)},
        )
    )
