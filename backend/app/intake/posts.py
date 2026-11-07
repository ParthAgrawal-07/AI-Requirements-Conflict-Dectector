"""Requirement posts (Bansil — US-30 backend, FR-55; design update §3.1).

A member posts a requirement into a channel from the composer. In **one transaction** this creates

* a channel message of kind ``requirement_post`` whose body is the rendered statement (the card
  people see in the channel; it can never be edited — changes go through a change request);
* a **Proposed** requirement (``origin = post``, version 1, no document) linked to that message,
  with the composer's type, priority, owner, group and the submitted fields;
* an audit row with ids only (CR-04);

and, after the commit, the ``message.created`` event. The statement is
:func:`app.intake.ears.render_statement` of the template and slots — the preview the member saw —
and is never rewritten (FR-04). The draft the member was writing is deleted with it.

Live analysis of the new requirement against the baseline is US-31 (Sprint 3): it will be queued
here, after the commit.
"""

import uuid

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.intake import drafts as draft_service
from app.intake.schemas import ComposerFields
from app.models import (
    AuditAction,
    AuditLog,
    Channel,
    Message,
    MessageKind,
    Project,
    Requirement,
    RequirementOrigin,
    RequirementState,
    RequirementVersion,
    User,
)
from app.realtime.events import MESSAGE_CREATED
from app.services import messages as message_service
from app.services.access import active_membership


def post_requirement(
    db: Session,
    *,
    channel: Channel,
    author: User,
    fields: ComposerFields,
    draft_id: uuid.UUID | None = None,
) -> tuple[Message, Requirement]:
    project = db.get(Project, channel.project_id)
    if project is None:  # impossible through the FK; defensive
        raise NotFoundError("Channel not found")
    owner_id = fields.owner_id or author.id
    if active_membership(db, owner_id, project.workspace_id) is None:
        raise NotFoundError("The chosen owner is not a member of this workspace")
    draft = draft_service.get_draft(db, author, draft_id) if draft_id else None

    statement = fields.statement
    message = message_service.post_message(
        db,
        channel=channel,
        author=author,
        body=statement,
        kind=MessageKind.REQUIREMENT_POST,
        commit=False,
    )
    requirement = Requirement(
        project_id=project.id,
        document_id=None,
        state=RequirementState.PROPOSED,
        origin=RequirementOrigin.POST,
        origin_message_id=message.id,
        owner_id=owner_id,
        stakeholder_group=fields.stakeholder_group,
        body=message.body,  # the statement as stored on the card, verbatim
        req_type=fields.type.value,
        priority=fields.priority.value,
        composer_fields=fields.model_dump(mode="json"),
    )
    db.add(requirement)
    db.flush()
    db.add(
        RequirementVersion(
            requirement_id=requirement.id,
            version_no=1,
            body_snapshot=requirement.body,
            changed_by=author.id,
        )
    )
    db.add(
        AuditLog(
            workspace_id=project.workspace_id,
            actor_id=author.id,
            requirement_id=requirement.id,
            action=AuditAction.REQUIREMENT_POSTED,
            details={"channel_id": str(channel.id), "message_id": str(message.id)},
        )
    )
    if draft is not None:
        draft_service.delete_draft(db, draft, commit=False)
    db.commit()
    db.refresh(requirement)
    message_service.announce(MESSAGE_CREATED, project, channel, message)
    return message, requirement
