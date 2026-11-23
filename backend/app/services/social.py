"""Discussion, votes, watches and human links (Madhav — US-53, FR-80, FR-90, FR-91, DR-17,
DR-19; design update §4.1).

* **Comments** on a requirement — a thread separate from channel chat, stored in ``comments``
  with ``subject_type='requirement'``. The owner and the watchers hear about each one, and the
  people it @mentions are told so.
* **Votes** — *support* or *oppose* a requirement or a change request, at most one per member and
  subject (a second vote replaces the first). Tallies are shown in the drawer and to reviewers.
  **Votes never decide**: nothing here changes a state, and the agreement rules (US-57) do not
  read this table (DR-17).
* **Watches** — follow a requirement, an issue or a change request; :func:`watcher_ids` is what
  producers add to their notification recipients (US-38, kind ``watching``).
* **Links** — a person asserts *depends on*, *refines* or *related to* between two requirements of
  the same project. The map draws them as human edges, impact analysis follows them
  (``app.search.relations``), and they are removed only by a person (DR-19). Adding and removing
  is audited (ids only) and goes out as a map delta with a written sentence.

Notifications and events carry ids, keys and short titles — never comment or requirement text
(CR-04).
"""

import logging
import uuid
from collections.abc import Collection, Iterable
from dataclasses import dataclass, field

from sqlalchemy import delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import BadRequestError, ConflictError, NotFoundError
from app.graph import deltas, narrator
from app.models import (
    AuditAction,
    AuditLog,
    ChangeRequest,
    Comment,
    Issue,
    Membership,
    Project,
    Requirement,
    RequirementLink,
    User,
    Vote,
    Watch,
)
from app.models.notification import MENTIONED, WATCHING
from app.models.social import LINK_KINDS, STANCES, VOTE_SUBJECTS, WATCH_SUBJECTS
from app.notifications import subjects
from app.notifications.service import NotificationService, Subject
from app.realtime import bus
from app.realtime.events import requirement_activity

logger = logging.getLogger(__name__)

MAX_COMMENT = 5000
MAX_REASON = 1000
LINK_WORDS = {"depends_on": "depends on", "refines": "refines", "related_to": "is related to"}


@dataclass(frozen=True)
class VoteView:
    user_id: uuid.UUID
    user_name: str | None
    stance: str
    reason: str | None


@dataclass
class Tally:
    support: int = 0
    oppose: int = 0
    mine: str | None = None  # the caller's stance, if they voted
    votes: list[VoteView] = field(default_factory=list)


# ── subjects ────────────────────────────────────────────────────────────────────────────────
def project_of(db: Session, subject_type: str, subject_id: uuid.UUID) -> Project:
    """The project a votable or watchable subject belongs to (404 when it does not exist)."""
    row: Requirement | Issue | ChangeRequest | None
    if subject_type == "requirement":
        row = db.get(Requirement, subject_id)
    elif subject_type == "issue":
        row = db.get(Issue, subject_id)
    elif subject_type == "change_request":
        row = db.get(ChangeRequest, subject_id)
    else:
        raise NotFoundError("Not found")
    project = db.get(Project, row.project_id) if row is not None else None
    if project is None:
        raise NotFoundError("Not found")
    return project


# ── comments ────────────────────────────────────────────────────────────────────────────────
def comments(db: Session, requirement_id: uuid.UUID) -> list[Comment]:
    return list(
        db.scalars(
            select(Comment)
            .where(Comment.subject_type == "requirement", Comment.subject_id == requirement_id)
            .order_by(Comment.created_at, Comment.id)
        )
    )


def comment_count(db: Session, requirement_id: uuid.UUID) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(Comment)
            .where(Comment.subject_type == "requirement", Comment.subject_id == requirement_id)
        )
        or 0
    )


def add_comment(
    db: Session,
    requirement: Requirement,
    author: User,
    body: str,
    *,
    mentions: Collection[uuid.UUID] = (),
) -> Comment:
    text = body.strip()
    if not text:
        raise BadRequestError("A comment cannot be empty", code="empty_comment")
    if len(text) > MAX_COMMENT:
        raise BadRequestError(f"A comment is at most {MAX_COMMENT} characters", code="too_long")
    comment = Comment(
        subject_type="requirement", subject_id=requirement.id, author_id=author.id, body=text
    )
    db.add(comment)
    db.commit()
    project = db.get(Project, requirement.project_id)
    if project is None:  # pragma: no cover
        return comment
    label = subjects.requirement_label(requirement)
    _publish(project, requirement.id, "comment", author.id)
    mentioned = _members(db, project.workspace_id, set(mentions)) - {author.id}
    _notify(
        db,
        project,
        mentioned,
        MENTIONED,
        _requirement_subject(project, requirement, f"{author.full_name} mentioned you on {label}"),
        actor_id=author.id,
        requirement_id=requirement.id,
    )
    _notify(
        db,
        project,
        ({requirement.owner_id} | watcher_ids(db, "requirement", requirement.id)) - mentioned,
        WATCHING,
        _requirement_subject(project, requirement, f"{author.full_name} commented on {label}"),
        actor_id=author.id,
        requirement_id=requirement.id,
    )
    return comment


# ── votes (display only, DR-17) ─────────────────────────────────────────────────────────────
def set_vote(
    db: Session,
    project: Project,
    subject_type: str,
    subject_id: uuid.UUID,
    voter: User,
    stance: str,
    reason: str | None = None,
) -> Tally:
    if subject_type not in VOTE_SUBJECTS or stance not in STANCES:
        raise BadRequestError("Unknown vote", code="invalid_vote")
    why = (reason or "").strip() or None
    if why is not None and len(why) > MAX_REASON:
        raise BadRequestError(f"A reason is at most {MAX_REASON} characters", code="too_long")
    statement = insert(Vote).values(
        project_id=project.id,
        subject_type=subject_type,
        subject_id=subject_id,
        user_id=voter.id,
        stance=stance,
        reason=why,
    )
    db.execute(
        statement.on_conflict_do_update(
            constraint="uq_votes_subject_type_subject_id_user_id",
            set_={"stance": stance, "reason": why, "updated_at": func.now()},
        )
    )
    db.commit()
    _publish_vote(db, project, subject_type, subject_id, voter.id)
    return tally(db, subject_type, subject_id, voter.id)


def clear_vote(
    db: Session, project: Project, subject_type: str, subject_id: uuid.UUID, voter: User
) -> Tally:
    db.execute(
        delete(Vote).where(
            Vote.subject_type == subject_type,
            Vote.subject_id == subject_id,
            Vote.user_id == voter.id,
        )
    )
    db.commit()
    _publish_vote(db, project, subject_type, subject_id, voter.id)
    return tally(db, subject_type, subject_id, voter.id)


def tally(
    db: Session, subject_type: str, subject_id: uuid.UUID, viewer_id: uuid.UUID | None = None
) -> Tally:
    result = Tally()
    rows = db.execute(
        select(Vote, User.full_name)
        .outerjoin(User, User.id == Vote.user_id)
        .where(Vote.subject_type == subject_type, Vote.subject_id == subject_id)
        .order_by(Vote.updated_at.desc(), Vote.id)
    )
    for vote, name in rows:
        if vote.stance == "support":
            result.support += 1
        else:
            result.oppose += 1
        if vote.user_id == viewer_id:
            result.mine = vote.stance
        result.votes.append(VoteView(vote.user_id, name, vote.stance, vote.reason))
    return result


# ── watches ─────────────────────────────────────────────────────────────────────────────────
def watch(
    db: Session, project: Project, subject_type: str, subject_id: uuid.UUID, user: User
) -> None:
    if subject_type not in WATCH_SUBJECTS:
        raise BadRequestError("Unknown subject", code="invalid_subject")
    db.execute(
        insert(Watch)
        .values(
            user_id=user.id, subject_type=subject_type, subject_id=subject_id, project_id=project.id
        )
        .on_conflict_do_nothing()
    )
    db.commit()


def unwatch(db: Session, subject_type: str, subject_id: uuid.UUID, user: User) -> None:
    db.execute(
        delete(Watch).where(
            Watch.user_id == user.id,
            Watch.subject_type == subject_type,
            Watch.subject_id == subject_id,
        )
    )
    db.commit()


def is_watching(db: Session, subject_type: str, subject_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    return db.get(Watch, (user_id, subject_type, subject_id)) is not None


def watcher_ids(db: Session, subject_type: str, subject_id: uuid.UUID) -> set[uuid.UUID]:
    """Who watches the subject. Producers add these to their recipients (best effort)."""
    return set(
        db.scalars(
            select(Watch.user_id).where(
                Watch.subject_type == subject_type, Watch.subject_id == subject_id
            )
        )
    )


def watchers_of_requirements(db: Session, requirement_ids: Iterable[uuid.UUID]) -> set[uuid.UUID]:
    ids = list(requirement_ids)
    if not ids:
        return set()
    return set(
        db.scalars(
            select(Watch.user_id).where(
                Watch.subject_type == "requirement", Watch.subject_id.in_(ids)
            )
        )
    )


# ── links (DR-19) ───────────────────────────────────────────────────────────────────────────
def links(db: Session, requirement_id: uuid.UUID) -> list[RequirementLink]:
    """Every link from or to the requirement, oldest first."""
    return list(
        db.scalars(
            select(RequirementLink)
            .where(
                or_(
                    RequirementLink.source_id == requirement_id,
                    RequirementLink.target_id == requirement_id,
                )
            )
            .order_by(RequirementLink.created_at, RequirementLink.id)
        )
    )


def add_link(
    db: Session,
    source: Requirement,
    target_id: uuid.UUID,
    kind: str,
    actor: User,
    *,
    note: str | None = None,
) -> RequirementLink:
    if kind not in LINK_KINDS:
        raise BadRequestError("Unknown link kind", code="invalid_link")
    target = db.get(Requirement, target_id)
    if target is None or target.project_id != source.project_id:
        # Another project's requirement does not exist for this request (NFR-27).
        raise NotFoundError("Requirement not found")
    if target.id == source.id:
        raise BadRequestError("A requirement cannot be linked to itself", code="self_link")
    link = RequirementLink(
        project_id=source.project_id,
        source_id=source.id,
        target_id=target.id,
        kind=kind,
        note=(note or "").strip() or None,
        created_by=actor.id,
    )
    try:
        with db.begin_nested():
            db.add(link)
            db.flush()
    except IntegrityError:
        raise ConflictError("This link already exists", code="link_exists") from None
    project = db.get(Project, source.project_id)
    if project is None:  # pragma: no cover — the requirement's project exists
        raise NotFoundError("Project not found")
    _audit_link(db, project, actor, link, AuditAction.LINK_ADDED)
    db.commit()
    a, b = deltas.label_of(source), deltas.label_of(target)
    deltas.publish(
        db,
        project.id,
        deltas.Change(
            requirements={source.id, target.id},
            new_links={link.id},
            sentences=[narrator.linked(actor.full_name, a, LINK_WORDS[kind], b)],
            kind="link",
        ),
        actor=actor,
    )
    _publish(project, source.id, "link", actor.id)
    _notify(
        db,
        project,
        watchers_of_requirements(db, [source.id, target.id]) | {source.owner_id, target.owner_id},
        WATCHING,
        _requirement_subject(project, source, f"{actor.full_name} linked {a} to {b}"),
        actor_id=actor.id,
        requirement_ids=[str(source.id), str(target.id)],
    )
    return link


def remove_link(db: Session, link: RequirementLink, actor: User) -> None:
    source, target = db.get(Requirement, link.source_id), db.get(Requirement, link.target_id)
    project = db.get(Project, link.project_id)
    if project is None or source is None or target is None:  # pragma: no cover — cascades
        raise NotFoundError("Link not found")
    _audit_link(db, project, actor, link, AuditAction.LINK_REMOVED)
    link_id, kind = link.id, link.kind
    db.delete(link)
    db.commit()
    deltas.publish(
        db,
        project.id,
        deltas.Change(
            requirements={source.id, target.id},
            removed_links={link_id},
            sentences=[
                narrator.unlinked(
                    actor.full_name,
                    deltas.label_of(source),
                    LINK_WORDS[kind],
                    deltas.label_of(target),
                )
            ],
            kind="link",
        ),
        actor=actor,
    )
    _publish(project, source.id, "link", actor.id)


def _audit_link(
    db: Session, project: Project, actor: User, link: RequirementLink, action: AuditAction
) -> None:
    db.add(
        AuditLog(
            workspace_id=project.workspace_id,
            actor_id=actor.id,
            requirement_id=link.source_id,
            action=action,
            details={
                "project_id": str(project.id),
                "link_id": str(link.id),
                "target_id": str(link.target_id),
                "kind": link.kind,
            },
        )
    )


# ── helpers ─────────────────────────────────────────────────────────────────────────────────
def _members(db: Session, workspace_id: uuid.UUID, users: set[uuid.UUID]) -> set[uuid.UUID]:
    if not users:
        return set()
    return set(
        db.scalars(
            select(Membership.user_id).where(
                Membership.workspace_id == workspace_id,
                Membership.user_id.in_(users),
                Membership.ended_at.is_(None),
            )
        )
    )


def _requirement_subject(project: Project, requirement: Requirement, title: str) -> Subject:
    return Subject(
        type="requirement",
        id=requirement.id,
        key=subjects.requirement_label(requirement),
        title=title,
        url=f"/w/{project.workspace_id}/p/{project.id}/requirements?requirement={requirement.id}",
    )


def _notify(
    db: Session,
    project: Project,
    users: Collection[uuid.UUID | None],
    kind: str,
    subject: Subject,
    *,
    actor_id: uuid.UUID,
    **ids: object,
) -> None:
    """Best effort: a failed notification never fails the comment or link it announces."""
    if not any(users):
        return
    try:
        NotificationService(db).notify(
            users,
            kind,
            workspace_id=project.workspace_id,
            project_id=project.id,
            actor_id=actor_id,
            subject=subject,
            **ids,
        )
    except Exception:
        db.rollback()
        logger.exception("Notifications about %s %s failed", subject.type, subject.id)


def _publish(project: Project, requirement_id: uuid.UUID, what: str, actor_id: uuid.UUID) -> None:
    bus.publish(
        requirement_activity(
            workspace_id=project.workspace_id,
            project_id=project.id,
            requirement_id=requirement_id,
            what=what,
            actor_id=actor_id,
        )
    )


def _publish_vote(
    db: Session, project: Project, subject_type: str, subject_id: uuid.UUID, actor_id: uuid.UUID
) -> None:
    requirement_id = subject_id
    if subject_type == "change_request":
        change_request = db.get(ChangeRequest, subject_id)
        if change_request is None:  # pragma: no cover
            return
        requirement_id = change_request.requirement_id
    _publish(project, requirement_id, "vote", actor_id)
