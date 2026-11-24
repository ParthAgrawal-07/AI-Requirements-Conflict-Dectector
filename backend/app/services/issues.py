"""Issues and automatic conflict issues (Dhavni — US-52, FR-86, FR-87; design update §3.5, §7.4).

**Issues by people.** A member with ``issue.open`` opens ISS-n about one or more requirements of
the project, with labels and assignees (members of the workspace), and comments on it. Who may
change what:

=====================  ===============================================================
Change                 Who
=====================  ===============================================================
title, body            the author, or ``issue.manage``
labels, assignees      ``issue.manage``
close, reopen          the author, an assignee, or ``issue.manage``
comment                ``issue.open``
=====================  ===============================================================

**Auto conflict issues** (:class:`ConflictIssueOpener`). When an analysis run stores a live
Conflicting or Duplicate finding of Medium or High severity whose requirements have **two or more
distinct owners**, ISS-n is opened by itself: labelled ``conflict``, ``auto`` and the severity,
assigned to every owner, linked to both requirements, its finding's clarification question as the
first comment. One per finding (unique index); a re-analysis that flags the same pair again
re-points the existing issue to the new finding and reopens it if its finding had been resolved.
It closes by itself (``finding_resolved``) when its finding is dismissed, merged, superseded by
an edit, or accepted with its question answered — and reopens if that is undone. A manual close
is never undone automatically.

Numbers are unique per project: the next one is taken under a lock on the project row. Every
change is audited (ids only), published as ``issue.*`` and, when it changes a requirement's open
issue count, as a ``graph.delta`` with a sentence for the feed.
"""

import uuid
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import BadRequestError, ForbiddenError
from app.graph import deltas, narrator
from app.models import (
    AnalysisRun,
    AuditAction,
    AuditLog,
    CandidatePair,
    Comment,
    Finding,
    FindingCategory,
    FindingStatus,
    Issue,
    IssueAssignee,
    IssueRequirement,
    Membership,
    Project,
    Requirement,
    Severity,
    User,
)
from app.models.issue import CLOSED, FINDING_RESOLVED, MANUAL, OPEN
from app.realtime import bus
from app.realtime.events import (
    ISSUE_CLOSED,
    ISSUE_COMMENTED,
    ISSUE_OPENED,
    ISSUE_REOPENED,
    ISSUE_UPDATED,
    issue_event,
)
from app.services.access import AccessContext

AUTO_CATEGORIES = (FindingCategory.CONFLICTING, FindingCategory.DUPLICATE)
AUTO_SEVERITIES = (Severity.MEDIUM, Severity.HIGH)
LIVE = (FindingStatus.FLAGGED, FindingStatus.CONFIRMED, FindingStatus.RECLASSIFIED)
MAX_LABELS = 10


def key(issue: Issue) -> str:
    return f"ISS-{issue.number}"


@dataclass
class IssueView:
    issue: Issue
    requirements: list[Requirement]
    assignees: list[User]
    author: User | None
    comment_count: int


# ── reading ─────────────────────────────────────────────────────────────────────────────────
def requirement_ids(db: Session, issue_id: uuid.UUID) -> list[uuid.UUID]:
    return list(
        db.scalars(
            select(IssueRequirement.requirement_id).where(IssueRequirement.issue_id == issue_id)
        )
    )


def assignee_ids(db: Session, issue_id: uuid.UUID) -> list[uuid.UUID]:
    return list(db.scalars(select(IssueAssignee.user_id).where(IssueAssignee.issue_id == issue_id)))


def view(db: Session, issue: Issue) -> IssueView:
    requirements = list(
        db.scalars(
            select(Requirement)
            .join(IssueRequirement, IssueRequirement.requirement_id == Requirement.id)
            .where(IssueRequirement.issue_id == issue.id)
            .order_by(Requirement.source_req_id, Requirement.id)
        )
    )
    assignees = list(
        db.scalars(
            select(User)
            .join(IssueAssignee, IssueAssignee.user_id == User.id)
            .where(IssueAssignee.issue_id == issue.id)
            .order_by(User.full_name, User.id)
        )
    )
    comments = db.scalar(
        select(func.count())
        .select_from(Comment)
        .where(Comment.subject_type == "issue", Comment.subject_id == issue.id)
    )
    author = db.get(User, issue.author_id) if issue.author_id else None
    return IssueView(issue, requirements, assignees, author, comments or 0)


def list_issues(
    db: Session,
    project_id: uuid.UUID,
    *,
    status: str | None = None,
    label: str | None = None,
    assignee: uuid.UUID | None = None,
    requirement: uuid.UUID | None = None,
    auto: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[IssueView], int]:
    """Newest first. ``label`` matches one label exactly."""
    query = select(Issue).where(Issue.project_id == project_id)
    if status is not None:
        query = query.where(Issue.status == status)
    if label is not None:
        query = query.where(Issue.labels.contains([label]))
    if auto is not None:
        query = query.where(Issue.auto.is_(auto))
    if assignee is not None:
        query = query.where(
            Issue.id.in_(select(IssueAssignee.issue_id).where(IssueAssignee.user_id == assignee))
        )
    if requirement is not None:
        query = query.where(
            Issue.id.in_(
                select(IssueRequirement.issue_id).where(
                    IssueRequirement.requirement_id == requirement
                )
            )
        )
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(Issue.number.desc()).limit(limit).offset(offset))
    return [view(db, issue) for issue in rows], total


def open_counts(
    db: Session, project_id: uuid.UUID, requirement_ids: Collection[uuid.UUID] | None = None
) -> dict[uuid.UUID, int]:
    """Open issues per requirement, for the map's badge (``GraphNode.open_issues``)."""
    query = (
        select(IssueRequirement.requirement_id, func.count())
        .join(Issue, Issue.id == IssueRequirement.issue_id)
        .where(Issue.project_id == project_id, Issue.status == OPEN)
        .group_by(IssueRequirement.requirement_id)
    )
    if requirement_ids is not None:
        query = query.where(IssueRequirement.requirement_id.in_(list(requirement_ids)))
    return {row[0]: row[1] for row in db.execute(query)}


def comments(db: Session, issue_id: uuid.UUID) -> list[Comment]:
    return list(
        db.scalars(
            select(Comment)
            .where(Comment.subject_type == "issue", Comment.subject_id == issue_id)
            .order_by(Comment.created_at, Comment.id)
        )
    )


# ── writing ─────────────────────────────────────────────────────────────────────────────────
def _next_number(db: Session, project_id: uuid.UUID) -> int:
    db.execute(select(Project.id).where(Project.id == project_id).with_for_update())
    return (
        db.scalar(select(func.max(Issue.number)).where(Issue.project_id == project_id)) or 0
    ) + 1


def _clean_labels(labels: Iterable[str]) -> list[str]:
    cleaned: list[str] = []
    for label in labels:
        value = label.strip().lower()
        if value and value not in cleaned:
            cleaned.append(value[:40])
    if len(cleaned) > MAX_LABELS:
        raise BadRequestError(f"At most {MAX_LABELS} labels", code="too_many_labels")
    return cleaned


def _project_requirements(
    db: Session, project_id: uuid.UUID, ids: Collection[uuid.UUID]
) -> list[Requirement]:
    rows = list(
        db.scalars(
            select(Requirement).where(
                Requirement.id.in_(list(ids)), Requirement.project_id == project_id
            )
        )
    )
    if len(rows) != len(set(ids)):
        raise BadRequestError(
            "Every requirement must belong to this project", code="unknown_requirement"
        )
    return rows


def _members(
    db: Session, workspace_id: uuid.UUID, ids: Collection[uuid.UUID], *, strict: bool = True
) -> list[uuid.UUID]:
    """The active members among ``ids``; ``strict`` refuses anyone else instead of skipping."""
    found = set(
        db.scalars(
            select(Membership.user_id).where(
                Membership.workspace_id == workspace_id,
                Membership.user_id.in_(list(ids)),
                Membership.ended_at.is_(None),
            )
        )
    )
    if strict and found != set(ids):
        raise BadRequestError(
            "Issues can be assigned to members of the workspace only", code="unknown_assignee"
        )
    return sorted(found)


def _audit(
    db: Session,
    workspace_id: uuid.UUID,
    actor: User | None,
    issue: Issue,
    action: AuditAction,
    **details: object,
) -> None:
    if actor is None:  # the app itself (auto issues): the issue row records it
        return
    db.add(
        AuditLog(
            workspace_id=workspace_id,
            actor_id=actor.id,
            action=action,
            details={"issue_id": str(issue.id), "number": issue.number, **details},
        )
    )


def _announce(
    db: Session,
    issue: Issue,
    event_type: str,
    *,
    actor: User | None,
    sentence: str | None = None,
    **data: object,
) -> None:
    project = db.get(Project, issue.project_id)
    if project is None:  # pragma: no cover — the FK makes this impossible
        return
    bus.publish(
        issue_event(
            event_type,
            workspace_id=project.workspace_id,
            project_id=project.id,
            issue_id=issue.id,
            number=issue.number,
            status=issue.status,
            actor_id=actor.id if actor else None,
            assignee_ids=assignee_ids(db, issue.id),
            **data,
        )
    )
    if sentence is not None:
        deltas.publish(
            db,
            project.id,
            deltas.Change(
                requirements=set(requirement_ids(db, issue.id)), sentences=[sentence], kind="issue"
            ),
            actor=actor,
        )


def _labels_of(requirements: Sequence[Requirement]) -> list[str]:
    return sorted(deltas.label_of(r) for r in requirements)


def open_issue(
    db: Session,
    *,
    project: Project,
    author: User | None,
    title: str,
    body: str = "",
    labels: Iterable[str] = (),
    assignees: Collection[uuid.UUID] = (),
    requirements: Collection[uuid.UUID] = (),
    finding: Finding | None = None,
    auto: bool = False,
    members_only: bool = False,
) -> Issue:
    """Open ISS-n (committed), then announce it. ``members_only`` assigns those of
    ``assignees`` still in the workspace (owners can leave) instead of refusing the rest."""
    linked = _project_requirements(db, project.id, requirements)
    people = _members(db, project.workspace_id, assignees, strict=not members_only)
    issue = Issue(
        project_id=project.id,
        number=_next_number(db, project.id),
        title=title.strip(),
        body=body.strip(),
        labels=_clean_labels(labels),
        auto=auto,
        finding_id=finding.id if finding else None,
        author_id=author.id if author else None,
    )
    db.add(issue)
    db.flush()
    db.add_all(IssueRequirement(issue_id=issue.id, requirement_id=r.id) for r in linked)
    db.add_all(IssueAssignee(issue_id=issue.id, user_id=u) for u in people)
    _audit(
        db,
        project.workspace_id,
        author,
        issue,
        AuditAction.ISSUE_OPENED,
        requirement_ids=[str(r.id) for r in linked],
        assignee_ids=[str(u) for u in people],
    )
    db.commit()
    if auto:
        names = [u.full_name for u in db.scalars(select(User).where(User.id.in_(people)))]
        sentence = narrator.auto_issue_opened(issue.number, _labels_of(linked), sorted(names))
    else:
        sentence = narrator.issue_opened(
            author.full_name if author else None, issue.number, _labels_of(linked)
        )
    _announce(db, issue, ISSUE_OPENED, actor=author, sentence=sentence, auto=auto)
    _notify_assigned(db, issue, people, actor=author)
    return issue


def _notify_assigned(
    db: Session, issue: Issue, user_ids: Collection[uuid.UUID], *, actor: User | None
) -> None:
    from app.notifications import hooks  # Madhav (US-38); late import: hooks reads services

    hooks.assigned(db, issue, user_ids, actor_id=actor.id if actor else None)


def _may_edit(ctx: AccessContext, issue: Issue) -> bool:
    return ctx.can("issue.manage") or issue.author_id == ctx.user.id


def _may_close(db: Session, ctx: AccessContext, issue: Issue) -> bool:
    return _may_edit(ctx, issue) or ctx.user.id in assignee_ids(db, issue.id)


def update_issue(
    db: Session,
    ctx: AccessContext,
    issue: Issue,
    *,
    title: str | None = None,
    body: str | None = None,
    labels: Iterable[str] | None = None,
    assignees: Collection[uuid.UUID] | None = None,
    status: str | None = None,
) -> Issue:
    """Edit, relabel, reassign, close (manual) or reopen — each part checked on its own."""
    changed: list[str] = []
    added: set[uuid.UUID] = set()
    if title is not None or body is not None:
        if not _may_edit(ctx, issue):
            raise ForbiddenError("Only the author or an issue manager can edit an issue")
        if title is not None and title.strip() != issue.title:
            issue.title = title.strip()
            changed.append("title")
        if body is not None and body.strip() != issue.body:
            issue.body = body.strip()
            changed.append("body")
    if labels is not None or assignees is not None:
        if not ctx.can("issue.manage"):
            raise ForbiddenError("Labels and assignees are for issue managers")
        if labels is not None:
            cleaned = _clean_labels(labels)
            if cleaned != issue.labels:
                issue.labels = cleaned
                changed.append("labels")
        if assignees is not None:
            wanted = set(_members(db, ctx.workspace_id, assignees))
            current = set(assignee_ids(db, issue.id))
            for user_id in current - wanted:
                db.delete(db.get(IssueAssignee, (issue.id, user_id)))
            db.add_all(IssueAssignee(issue_id=issue.id, user_id=u) for u in wanted - current)
            added = wanted - current
            if wanted != current:
                changed.append("assignees")
    if changed:
        _audit(db, ctx.workspace_id, ctx.user, issue, AuditAction.ISSUE_UPDATED, fields=changed)
        db.commit()
        _announce(db, issue, ISSUE_UPDATED, actor=ctx.user, fields=changed)
        _notify_assigned(db, issue, added, actor=ctx.user)
    if status is not None and status != issue.status:
        if not _may_close(db, ctx, issue):
            raise ForbiddenError("Only the author, an assignee or an issue manager can do this")
        if status == CLOSED:
            close(db, issue, MANUAL, actor=ctx.user)
        else:
            reopen(db, issue, actor=ctx.user)
    return issue


def close(db: Session, issue: Issue, reason: str, *, actor: User | None) -> None:
    if issue.status == CLOSED:
        return
    issue.status, issue.close_reason = CLOSED, reason
    issue.closed_at, issue.closed_by = datetime.now(UTC), actor.id if actor else None
    workspace_id = db.scalar(select(Project.workspace_id).where(Project.id == issue.project_id))
    if workspace_id is not None:
        _audit(db, workspace_id, actor, issue, AuditAction.ISSUE_CLOSED, reason=reason)
    db.commit()
    sentence = narrator.issue_closed(actor.full_name if actor else None, issue.number, reason)
    _announce(db, issue, ISSUE_CLOSED, actor=actor, sentence=sentence, close_reason=reason)


def reopen(db: Session, issue: Issue, *, actor: User | None, reflagged: bool = False) -> None:
    if issue.status == OPEN:
        return
    issue.status, issue.close_reason, issue.closed_at, issue.closed_by = OPEN, None, None, None
    workspace_id = db.scalar(select(Project.workspace_id).where(Project.id == issue.project_id))
    if workspace_id is not None:
        _audit(db, workspace_id, actor, issue, AuditAction.ISSUE_REOPENED)
    db.commit()
    sentence = narrator.issue_reopened(
        actor.full_name if actor else None, issue.number, reflagged=reflagged
    )
    _announce(db, issue, ISSUE_REOPENED, actor=actor, sentence=sentence)


def add_comment(db: Session, issue: Issue, author: User | None, body: str) -> Comment:
    text = body.strip()
    if not text:
        raise BadRequestError("A comment cannot be empty", code="empty_comment")
    comment = Comment(
        subject_type="issue",
        subject_id=issue.id,
        author_id=author.id if author else None,
        body=text,
    )
    db.add(comment)
    issue.updated_at = datetime.now(UTC)
    db.commit()
    _announce(db, issue, ISSUE_COMMENTED, actor=author, comment_id=str(comment.id))
    project = db.get(Project, issue.project_id)
    if project is not None:  # Madhav (US-53): watchers of the issue
        from app.notifications import hooks, subjects

        who = author.full_name if author else "Someone"
        hooks.watchers(
            db,
            project,
            "issue",
            issue.id,
            subjects.issue(db, issue, f"{who} commented on {{key}}"),
            actor_id=author.id if author else None,
            issue_id=issue.id,
        )
    return comment


# ── auto conflict issues (FR-87) ────────────────────────────────────────────────────────────
def _involved(db: Session, finding: Finding) -> list[Requirement]:
    if finding.candidate_pair_id is not None:
        pair = db.get(CandidatePair, finding.candidate_pair_id)
        ids = [pair.requirement_a_id, pair.requirement_b_id] if pair else []
    else:
        ids = [finding.requirement_id] if finding.requirement_id else []
    return [r for r in (db.get(Requirement, i) for i in ids) if r is not None]


def _resolved(finding: Finding) -> bool:
    if finding.is_stale or finding.status not in LIVE:
        return True
    question = finding.clarification
    return (
        finding.status is FindingStatus.CONFIRMED
        and question is not None
        and question.resolved_at is not None
    )


def auto_issue_of(db: Session, finding: Finding) -> Issue | None:
    """The auto issue of this finding — or of an earlier finding about the same pair."""
    issue = db.scalar(select(Issue).where(Issue.auto.is_(True), Issue.finding_id == finding.id))
    if issue is not None or finding.candidate_pair_id is None:
        return issue
    return db.scalar(
        select(Issue)
        .join(Finding, Finding.id == Issue.finding_id)
        .where(Issue.auto.is_(True), Finding.candidate_pair_id == finding.candidate_pair_id)
        .order_by(Issue.number.desc())
        .limit(1)
    )


class ConflictIssueOpener:
    """Opens, re-points, closes and reopens auto conflict issues (design update §3.5)."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def qualifies(self, finding: Finding, owners: set[uuid.UUID]) -> bool:
        return (
            finding.category in AUTO_CATEGORIES
            and finding.severity in AUTO_SEVERITIES
            and not _resolved(finding)
            and len(owners) >= 2
        )

    def on_finding(self, finding: Finding) -> Issue | None:
        """After a run stored ``finding``: open its issue, or bring the pair's issue back."""
        db = self.db
        requirements = _involved(db, finding)
        owners = {r.owner_id for r in requirements if r.owner_id is not None}
        existing = auto_issue_of(db, finding)
        if existing is not None:
            if existing.finding_id != finding.id and not _resolved(finding):
                existing.finding_id = finding.id
                db.commit()
                if existing.close_reason == FINDING_RESOLVED:
                    reopen(db, existing, actor=None, reflagged=True)
            return existing
        if not self.qualifies(finding, owners):
            return None
        project = db.get(Project, finding.project_id)
        if project is None:  # pragma: no cover
            return None
        labels = _labels_of(requirements)
        severity = finding.severity.value if finding.severity else "medium"
        word = (
            "Conflict" if finding.category is FindingCategory.CONFLICTING else "Possible duplicate"
        )
        issue = open_issue(
            db,
            project=project,
            author=None,
            title=f"{word} between {' and '.join(labels)}",
            body=finding.explanation or finding.rationale,
            labels=[finding.category.value.lower(), f"severity:{severity}", "auto"],
            assignees=sorted(owners),
            members_only=True,
            requirements=[r.id for r in requirements],
            finding=finding,
            auto=True,
        )
        if finding.clarification is not None:
            add_question(db, finding)
        return issue

    def on_run(self, run: AnalysisRun) -> list[Issue]:
        findings = self.db.scalars(
            select(Finding)
            .where(
                Finding.analysis_run_id == run.id,
                Finding.category.in_(AUTO_CATEGORIES),
                ~Finding.is_stale,
            )
            .order_by(Finding.created_at, Finding.id)
        ).all()
        return [issue for f in findings if (issue := self.on_finding(f)) is not None]


def on_finding_changed(db: Session, finding: Finding, *, actor: User | None) -> None:
    """A finding was reviewed, answered or superseded: close or reopen its auto issue."""
    issue = db.scalar(select(Issue).where(Issue.auto.is_(True), Issue.finding_id == finding.id))
    if issue is None:
        return
    if _resolved(finding):
        close(db, issue, FINDING_RESOLVED, actor=actor)
    elif issue.close_reason == FINDING_RESOLVED:
        reopen(db, issue, actor=actor)


def add_question(db: Session, finding: Finding) -> None:
    """The finding's clarification question as the first comment of its auto issue (FR-87)."""
    issue = db.scalar(select(Issue).where(Issue.auto.is_(True), Issue.finding_id == finding.id))
    question = finding.clarification
    if issue is None or question is None:
        return
    already = db.scalar(
        select(func.count())
        .select_from(Comment)
        .where(
            Comment.subject_type == "issue",
            Comment.subject_id == issue.id,
            Comment.author_id.is_(None),
        )
    )
    if not already:
        add_comment(db, issue, None, f"Clarification question: {question.question}")
