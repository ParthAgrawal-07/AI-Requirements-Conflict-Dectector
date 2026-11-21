"""One requirement's activity timeline (Dhavni — US-42, FR-72, DR-06, DR-08).

Everything that happened to a requirement, gathered from the tables that record it — nothing is
copied into a separate history, so the timeline cannot drift from the facts:

==================  ===========================================================================
``post``            it was posted (or extracted from a document): version 1
``version``         a later version written outside a change request
``state``           a lifecycle move, with the reason given
``analysis``        an analysis run of it (or of its document)
``finding``         a finding about it, from any source (AI, rule, person)
``review``          a finding review, or a review of one of its change requests
``clarification``   a clarification question asked, and answered
``issue``           an issue about it opened or closed
``change_request``  a change request on it opened or closed
``merge``           a change request merged into it (a new version)
``comment``         a comment in its discussion
``owner``           its owner changed
``baseline``        it was frozen into a labelled baseline
``vote``            a member supports or opposes it (Madhav, US-53; display only, DR-17)
``link``            a person linked it to another requirement (Madhav, US-53)
==================  ===========================================================================

Each entry links to its detail (``link_type`` / ``link_id``). Titles are template sentences that
name people and requirements by ID; free text (a reason, a decision rationale) is in ``detail``
— the timeline is shown only to members who may see the requirement itself.
"""

import uuid
from collections.abc import Collection
from dataclasses import dataclass, replace
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import (
    AnalysisRun,
    AnalysisScope,
    AuditAction,
    AuditLog,
    Baseline,
    BaselineItem,
    CandidatePair,
    ChangeRequest,
    Clarification,
    Comment,
    Document,
    Finding,
    FindingReview,
    Issue,
    IssueRequirement,
    Requirement,
    RequirementLink,
    RequirementOrigin,
    RequirementTransition,
    RequirementVersion,
    Review,
    User,
    Vote,
)

KINDS = (
    "post",
    "version",
    "state",
    "analysis",
    "finding",
    "review",
    "clarification",
    "issue",
    "change_request",
    "merge",
    "comment",
    "owner",
    "baseline",
    "vote",
    "link",
)
_REVIEW_WORDS = {
    "confirm": "confirmed",
    "dismiss": "dismissed",
    "merge": "merged",
    "reclassify": "reclassified",
    "reopen": "reopened",
    "escalate": "escalated",
}
_RUN_WORDS = {
    "queued": "queued",
    "running": "running",
    "waiting_budget": "waiting for the LLM budget",
    "done": "finished",
    "failed": "failed",
}
_DECISION_WORDS = {
    "approve": "approved",
    "request_changes": "requested changes on",
    "comment": "commented on",
}


@dataclass(frozen=True)
class Entry:
    at: datetime
    kind: str
    title: str
    actor_id: uuid.UUID | None = None
    actor_name: str | None = None
    link_type: str | None = None  # requirement, finding, issue, change_request, baseline, run
    link_id: uuid.UUID | None = None
    detail: str | None = None


def _label(requirement: Requirement | None) -> str:
    if requirement is None:
        return "a requirement"
    return requirement.source_req_id or f"requirement {str(requirement.id)[:8]}"


def timeline(
    db: Session,
    requirement: Requirement,
    *,
    kinds: Collection[str] = (),
    newest_first: bool = True,
) -> list[Entry]:
    wanted = set(kinds) or set(KINDS)
    entries: list[Entry] = []
    for kind, build in _SOURCES:
        if kind & wanted:
            entries.extend(e for e in build(db, requirement) if e.kind in wanted)
    names = _names(db, {e.actor_id for e in entries if e.actor_id})
    entries = [replace(e, actor_name=names.get(e.actor_id)) if e.actor_id else e for e in entries]
    entries.sort(key=lambda e: (e.at, e.kind, e.title), reverse=newest_first)
    return entries


def _names(db: Session, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    return {u.id: u.full_name for u in db.scalars(select(User).where(User.id.in_(ids)))}


def _versions(db: Session, requirement: Requirement) -> list[Entry]:
    rows = db.scalars(
        select(RequirementVersion)
        .where(RequirementVersion.requirement_id == requirement.id)
        .order_by(RequirementVersion.version_no)
    )
    entries = []
    for v in rows:
        if v.change_request_id is not None:
            continue  # shown as its merge
        if v.version_no == 1:
            if requirement.origin is RequirementOrigin.DOCUMENT and requirement.document_id:
                document = db.get(Document, requirement.document_id)
                title = f"Extracted from {document.filename if document else 'a document'}"
            else:
                title = f"{_label(requirement)} was posted"
            entries.append(Entry(v.changed_at, "post", title, actor_id=v.changed_by))
        else:
            entries.append(
                Entry(v.changed_at, "version", f"Version {v.version_no} saved", v.changed_by)
            )
    return entries


def _transitions(db: Session, requirement: Requirement) -> list[Entry]:
    rows = db.scalars(
        select(RequirementTransition).where(RequirementTransition.requirement_id == requirement.id)
    )
    return [
        Entry(
            t.created_at,
            "state",
            f"Moved from {t.from_state.value.replace('_', ' ')} to "
            f"{t.to_state.value.replace('_', ' ')}"
            + (" with an accepted risk" if t.accepted_risk else ""),
            actor_id=t.actor_id,
            detail=t.reason,
        )
        for t in rows
    ]


def _runs(db: Session, requirement: Requirement) -> list[Entry]:
    subjects = [requirement.id]
    if requirement.document_id is not None:
        subjects.append(requirement.document_id)
    rows = db.scalars(select(AnalysisRun).where(AnalysisRun.subject_id.in_(subjects)))
    entries = []
    for run in rows:
        what = "Analysis" if run.scope is AnalysisScope.REQUIREMENT else "Document analysis"
        status = _RUN_WORDS.get(run.status.value, run.status.value)
        entries.append(
            Entry(
                run.finished_at or run.created_at,
                "analysis",
                f"{what} {status}",
                link_type="run",
                link_id=run.id,
                detail=run.error_message,
            )
        )
    return entries


def _findings(db: Session, requirement: Requirement) -> list[tuple[Finding, str | None]]:
    rows = db.execute(
        select(Finding, CandidatePair)
        .outerjoin(CandidatePair, CandidatePair.id == Finding.candidate_pair_id)
        .where(
            or_(
                Finding.requirement_id == requirement.id,
                CandidatePair.requirement_a_id == requirement.id,
                CandidatePair.requirement_b_id == requirement.id,
            )
        )
    ).all()
    others = {
        (p.requirement_b_id if p.requirement_a_id == requirement.id else p.requirement_a_id)
        for _, p in rows
        if p is not None
    }
    labels = {
        r.id: _label(r)
        for r in (
            db.scalars(select(Requirement).where(Requirement.id.in_(others))) if others else []
        )
    }
    result = []
    for finding, pair in rows:
        other = None
        if pair is not None:
            other_id = (
                pair.requirement_b_id
                if pair.requirement_a_id == requirement.id
                else pair.requirement_a_id
            )
            other = labels.get(other_id)
        result.append((finding, other))
    return result


def _finding_entries(db: Session, requirement: Requirement) -> list[Entry]:
    found = _findings(db, requirement)
    entries = []
    for finding, other in found:
        with_other = f" with {other}" if other else ""
        by = {"ai": "the AI", "rule": "a rule check", "person": "a person"}.get(
            finding.source, finding.source
        )
        entries.append(
            Entry(
                finding.created_at,
                "finding",
                f"{finding.category.value} found{with_other} by {by}",
                link_type="finding",
                link_id=finding.id,
            )
        )
    ids = [f.id for f, _ in found]
    kinds = {f.id: (f.category.value.lower(), other) for f, other in found}
    if ids:
        for review in db.scalars(select(FindingReview).where(FindingReview.finding_id.in_(ids))):
            noun, other = kinds[review.finding_id]
            with_other = f" with {other}" if other else ""
            verb = _REVIEW_WORDS.get(review.action, review.action)
            entries.append(
                Entry(
                    review.created_at,
                    "review",
                    f"The {noun} finding{with_other} was {verb}",
                    actor_id=review.actor_id,
                    link_type="finding",
                    link_id=review.finding_id,
                    detail=review.reason,
                )
            )
        for question in db.scalars(select(Clarification).where(Clarification.finding_id.in_(ids))):
            entries.append(
                Entry(
                    question.created_at,
                    "clarification",
                    "A clarification question was asked",
                    link_type="finding",
                    link_id=question.finding_id,
                )
            )
            if question.resolved_at is not None:
                entries.append(
                    Entry(
                        question.resolved_at,
                        "clarification",
                        "The clarification question was answered",
                        actor_id=question.resolved_by,
                        link_type="finding",
                        link_id=question.finding_id,
                    )
                )
    return entries


def _issues(db: Session, requirement: Requirement) -> list[Entry]:
    rows = db.scalars(
        select(Issue)
        .join(IssueRequirement, IssueRequirement.issue_id == Issue.id)
        .where(IssueRequirement.requirement_id == requirement.id)
    )
    entries = []
    for issue in rows:
        how = " automatically" if issue.auto else ""
        entries.append(
            Entry(
                issue.created_at,
                "issue",
                f"ISS-{issue.number} opened{how}",
                actor_id=issue.author_id,
                link_type="issue",
                link_id=issue.id,
            )
        )
        if issue.closed_at is not None:
            entries.append(
                Entry(
                    issue.closed_at,
                    "issue",
                    f"ISS-{issue.number} closed",
                    actor_id=issue.closed_by,
                    link_type="issue",
                    link_id=issue.id,
                    detail=(issue.close_reason or "").replace("_", " ") or None,
                )
            )
    return entries


def _change_requests(db: Session, requirement: Requirement) -> list[Entry]:
    rows = list(
        db.scalars(select(ChangeRequest).where(ChangeRequest.requirement_id == requirement.id))
    )
    entries = []
    for cr in rows:
        key = f"RCR-{cr.number}"
        what = "deprecating it" if cr.kind == "deprecate" else "a change"
        entries.append(
            Entry(
                cr.created_at,
                "change_request",
                f"{key} opened, proposing {what}",
                actor_id=cr.proposer_id,
                link_type="change_request",
                link_id=cr.id,
                detail=cr.reason,
            )
        )
        if cr.merged_at is not None:
            tail = f" (version {cr.merged_version})" if cr.kind == "modify" else ""
            entries.append(
                Entry(
                    cr.merged_at,
                    "merge",
                    f"{key} merged{tail}",
                    actor_id=cr.merged_by,
                    link_type="change_request",
                    link_id=cr.id,
                )
            )
        elif cr.closed_at is not None:
            entries.append(
                Entry(
                    cr.closed_at,
                    "change_request",
                    f"{key} closed without merging",
                    actor_id=cr.closed_by,
                    link_type="change_request",
                    link_id=cr.id,
                    detail=cr.close_reason,
                )
            )
    numbers = {cr.id: cr.number for cr in rows}
    if numbers:
        for review in db.scalars(select(Review).where(Review.change_request_id.in_(numbers))):
            verb = _DECISION_WORDS.get(review.decision, review.decision)
            entries.append(
                Entry(
                    review.created_at,
                    "review",
                    f"Reviewer {verb} RCR-{numbers[review.change_request_id]}",
                    actor_id=review.reviewer_id,
                    link_type="change_request",
                    link_id=review.change_request_id,
                    detail=review.rationale,
                )
            )
    return entries


def _comments(db: Session, requirement: Requirement) -> list[Entry]:
    rows = db.scalars(
        select(Comment).where(
            Comment.subject_type == "requirement", Comment.subject_id == requirement.id
        )
    )
    return [
        Entry(
            c.created_at,
            "comment",
            "Commented in the discussion",
            actor_id=c.author_id,
            link_type="requirement",
            link_id=requirement.id,
        )
        for c in rows
    ]


def _owners(db: Session, requirement: Requirement) -> list[Entry]:
    rows = list(
        db.scalars(
            select(AuditLog).where(
                AuditLog.requirement_id == requirement.id,
                AuditLog.action == AuditAction.OWNER_CHANGED,
            )
        )
    )
    after = {(r.details or {}).get("after") for r in rows} - {None}
    names = _names(db, {uuid.UUID(a) for a in after if isinstance(a, str)})
    entries = []
    for row in rows:
        new = (row.details or {}).get("after")
        name = names.get(uuid.UUID(new)) if isinstance(new, str) else None
        title = f"{name} became the owner" if name else "The owner was removed"
        entries.append(Entry(row.at, "owner", title, actor_id=row.actor_id))
    return entries


def _baselines(db: Session, requirement: Requirement) -> list[Entry]:
    rows = db.execute(
        select(Baseline, BaselineItem.version_no)
        .join(BaselineItem, BaselineItem.baseline_id == Baseline.id)
        .where(BaselineItem.requirement_id == requirement.id)
    )
    return [
        Entry(
            baseline.created_at,
            "baseline",
            f"Frozen in baseline {baseline.label} at version {version}",
            actor_id=baseline.created_by,
            link_type="baseline",
            link_id=baseline.id,
        )
        for baseline, version in rows
    ]


def _votes(db: Session, requirement: Requirement) -> list[Entry]:
    rows = db.scalars(
        select(Vote).where(Vote.subject_type == "requirement", Vote.subject_id == requirement.id)
    )
    return [
        Entry(
            v.updated_at,
            "vote",
            "Supports it" if v.stance == "support" else "Opposes it",
            actor_id=v.user_id,
            detail=v.reason,
        )
        for v in rows
    ]


_LINK_WORDS = {"depends_on": "depends on", "refines": "refines", "related_to": "is related to"}


def _links(db: Session, requirement: Requirement) -> list[Entry]:
    rows = list(
        db.scalars(
            select(RequirementLink).where(
                or_(
                    RequirementLink.source_id == requirement.id,
                    RequirementLink.target_id == requirement.id,
                )
            )
        )
    )
    ids = {x for link in rows for x in (link.source_id, link.target_id)}
    labels = {
        r.id: _label(r)
        for r in (db.scalars(select(Requirement).where(Requirement.id.in_(ids))) if ids else [])
    }
    return [
        Entry(
            link.created_at,
            "link",
            f"Linked: {labels.get(link.source_id, '?')} {_LINK_WORDS.get(link.kind, link.kind)} "
            f"{labels.get(link.target_id, '?')}",
            actor_id=link.created_by,
            link_type="requirement",
            link_id=link.target_id if link.source_id == requirement.id else link.source_id,
            detail=link.note,
        )
        for link in rows
    ]


# Which builders produce which kinds (a builder is skipped when none of its kinds is wanted).
_SOURCES = (
    ({"post", "version"}, _versions),
    ({"state"}, _transitions),
    ({"analysis"}, _runs),
    ({"finding", "review", "clarification"}, _finding_entries),
    ({"issue"}, _issues),
    ({"change_request", "merge", "review"}, _change_requests),
    ({"comment"}, _comments),
    ({"owner"}, _owners),
    ({"baseline"}, _baselines),
    ({"vote"}, _votes),
    ({"link"}, _links),
)
