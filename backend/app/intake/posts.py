"""Requirement posts (Bansil — US-30, US-36, FR-55, FR-59, FR-60; design update §3.1).

A member posts a requirement from the composer, into a channel. In **one transaction** this creates

* a channel message of kind ``requirement_post`` whose body is the rendered statement (the card
  people see in the channel; it can never be edited — changes go through a change request);
* a **Proposed** requirement (``origin = post``, version 1, no document) linked to that message,
  with the composer's type, priority and submitted fields, and a printed ID (below);
* its owner (default: the author) and stakeholder group (default: the author's group, US-36);
* a **queued analysis run** for it (US-31) and an audit row with ids only (CR-04);

and, after the commit: ``message.created``, the run is dispatched (live analysis against the
baseline, ``analysis.run_requirement``) and the map hears about the new node (``graph.delta``).
The statement is :func:`app.intake.ears.render_statement` of the template and slots — the preview
the member saw — and is never rewritten (FR-04). The draft it came from is deleted with it.

**Printed IDs.** A post gets the next ``REQ-n`` of its project (one more than the highest
``REQ-<number>`` there, documents included, at least three digits), so a post is named like every
other requirement in cards, the map and the feed. The project row is locked while the number is
chosen, so two posts at the same moment never share one. Extracted requirements keep exactly the
ID printed in their document (FR-04); only posts are numbered by the system.

``POST /projects/{p}/requirements`` posts where the composer says: the chosen channel, else the
channel named after the stakeholder group (``Security`` → ``#security``), else ``#general``.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import BigInteger, cast, func, select
from sqlalchemy.orm import Session

from app.core.errors import BadRequestError, ConflictError, NotFoundError
from app.graph import deltas, narrator
from app.intake import drafts as draft_service
from app.intake import from_suggestion
from app.intake.schemas import ComposerFields
from app.models import (
    AnalysisRun,
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
from app.schemas.channels import normalize_channel_name
from app.services import analysis_orchestrator as orchestrator
from app.services import channels as channel_service
from app.services import messages as message_service
from app.services.access import active_membership

LABEL_PATTERN = r"^REQ-([0-9]{1,9})$"


@dataclass(frozen=True)
class PostResult:
    message: Message
    requirement: Requirement
    run: AnalysisRun


def post_requirement(
    db: Session,
    *,
    channel: Channel,
    author: User,
    fields: ComposerFields,
    draft_id: uuid.UUID | None = None,
    supersedes: uuid.UUID | None = None,
    source_suggestion_id: uuid.UUID | None = None,
) -> PostResult:
    project = db.scalar(select(Project).where(Project.id == channel.project_id).with_for_update())
    if project is None:  # impossible through the FK; defensive
        raise NotFoundError("Channel not found")
    author_membership = active_membership(db, author.id, project.workspace_id)
    owner_id = fields.owner_id or author.id
    if active_membership(db, owner_id, project.workspace_id) is None:
        raise NotFoundError("The chosen owner is not a member of this workspace")
    group = fields.stakeholder_group or (
        author_membership.stakeholder_group if author_membership else None
    )
    draft = draft_service.get_draft(db, author, draft_id) if draft_id else None
    from_suggestion.refuse_placeholders(fields.statement)
    old = from_suggestion.check_supersede(db, author, supersedes) if supersedes else None
    if old is not None and old.project_id != project.id:
        raise NotFoundError("The requirement to supersede was not found")
    if source_suggestion_id is not None:
        if old is None:
            raise BadRequestError(
                "A post from a suggestion supersedes your own proposal: name it",
                code="supersedes_required",
            )
        from_suggestion.accepted_suggestion(db, author, old, source_suggestion_id)

    label = next_label(db, project.id)
    message = message_service.post_message(
        db,
        channel=channel,
        author=author,
        body=fields.statement,
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
        stakeholder_group=group,
        source_req_id=label,
        body=message.body,  # the statement as stored on the card, verbatim
        req_type=fields.type.value,
        priority=fields.priority.value,
        composer_fields=fields.model_dump(mode="json"),
    )
    db.add(requirement)
    db.flush()
    message.payload = {"requirement_id": str(requirement.id), "label": label}
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
    if old is not None:  # Bansil (US-45): the new post replaces the member's own proposal
        from_suggestion.supersede(db, old, requirement, author, project.workspace_id)
    run = orchestrator.queue_requirement_run(db, requirement)
    if draft is not None:
        draft_service.delete_draft(db, draft, commit=False)
    db.commit()
    db.refresh(requirement)

    message_service.announce(MESSAGE_CREATED, project, channel, message)
    # Looked up on the module at call time so tests can replace the broker hand-off.
    orchestrator.dispatch_requirement_run(run.id, orchestrator.send)
    deltas.publish(
        db,
        project.id,
        deltas.Change(
            new_requirements={requirement.id},
            sentences=[narrator.added(author.full_name, label)],
            kind="added",
        ),
        actor=author,
    )
    return PostResult(message=message, requirement=requirement, run=run)


def post_to_project(
    db: Session,
    *,
    project: Project,
    author: User,
    fields: ComposerFields,
    draft_id: uuid.UUID | None = None,
    supersedes: uuid.UUID | None = None,
    source_suggestion_id: uuid.UUID | None = None,
) -> PostResult:
    """The composer's *Propose*: post where the fields say (see the module docstring)."""
    channel = target_channel(db, project, author, fields)
    return post_requirement(
        db,
        channel=channel,
        author=author,
        fields=fields,
        draft_id=draft_id,
        supersedes=supersedes,
        source_suggestion_id=source_suggestion_id,
    )


def target_channel(db: Session, project: Project, author: User, fields: ComposerFields) -> Channel:
    if fields.channel_id is not None:
        channel = channel_service.get_visible_channel(db, fields.channel_id, author)
        if channel.project_id != project.id:
            raise NotFoundError("Channel not found")
        return channel
    membership = active_membership(db, author.id, project.workspace_id)
    group = fields.stakeholder_group or (membership.stakeholder_group if membership else None)
    if group:
        try:
            name = normalize_channel_name(group)
        except ValueError:
            name = None
        if name is not None:
            group_channel = db.scalar(
                select(Channel).where(
                    Channel.project_id == project.id,
                    Channel.name == name,
                    Channel.archived_at.is_(None),
                )
            )
            if group_channel is not None and channel_service.can_see(db, group_channel, author.id):
                return group_channel
    general = db.scalar(
        select(Channel).where(
            Channel.project_id == project.id,
            Channel.is_default.is_(True),
            Channel.archived_at.is_(None),
        )
    )
    if general is None:
        raise ConflictError("This project has no channel to post in; choose one", code="no_channel")
    return general


def next_label(db: Session, project_id: uuid.UUID) -> str:
    """The next ``REQ-n`` of the project. Call with the project row locked."""
    number = func.substring(Requirement.source_req_id, LABEL_PATTERN)
    highest = db.scalar(
        select(func.max(cast(number, BigInteger))).where(
            Requirement.project_id == project_id,
            Requirement.source_req_id.regexp_match(LABEL_PATTERN),
        )
    )
    return f"REQ-{(highest or 0) + 1:03d}"
