"""What each narrative section of the updated SRS is written from (Bansil — US-61, FR-106;
design update §12.4 "Narrative section inputs").

* the **confirmed** project brief (never AI-drafted fields, FR-105);
* the stakeholder groups of the included requirements;
* the written change log (US-55) between the previous published SRS and this baseline;
* the decisions on closed issues: chosen option, decision owner and reason.

Requirements reach the LLM as IDs only — never the text it might restate (DR-25).
"""

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.context import service as context_service
from app.context.brief import BriefValues
from app.graph.changelog import keys_in
from app.models import (
    GraphEvent,
    Issue,
    IssueRequirement,
    Project,
    SuggestionFeedback,
    User,
)
from app.models.srs import SrsDocument
from app.models.suggestion import ACCEPTED, ACCEPTED_EDITED, Suggestion

MAX_CHANGE_SENTENCES = 60
MAX_DECISIONS = 40


@dataclass
class SectionInputs:
    brief: BriefValues
    values: dict[str, Any]
    known_ids: set[str]  # every ID a section may cite
    baseline_ids: set[str]  # the IDs of the included requirements


def previous_published(db: Session, project_id: uuid.UUID) -> SrsDocument | None:
    return db.scalar(
        select(SrsDocument)
        .where(SrsDocument.project_id == project_id, SrsDocument.status == "published")
        .order_by(SrsDocument.published_at.desc())
        .limit(1)
    )


def _change_log(db: Session, project: Project, since_revision: int | None) -> list[str]:
    query = select(GraphEvent.sentence).where(
        GraphEvent.project_id == project.id,
        GraphEvent.kind.in_(
            ("added", "merged", "state", "conflict_found", "conflict_resolved", "concern", "link")
        ),
    )
    if since_revision is not None:
        query = query.where(GraphEvent.baseline_revision > since_revision)
    query = query.order_by(GraphEvent.created_at.desc()).limit(MAX_CHANGE_SENTENCES)
    return list(reversed(list(db.scalars(query))))


def _decisions(
    db: Session, project: Project, requirement_ids: set[uuid.UUID]
) -> list[dict[str, Any]]:
    issues = list(
        db.scalars(
            select(Issue)
            .join(IssueRequirement, IssueRequirement.issue_id == Issue.id)
            .where(
                Issue.project_id == project.id,
                Issue.status == "closed",
                IssueRequirement.requirement_id.in_(list(requirement_ids)),
            )
            .distinct()
            .order_by(Issue.number)
            .limit(MAX_DECISIONS)
        )
    )
    closers = {
        u.id: u.full_name
        for u in db.scalars(
            select(User).where(User.id.in_({i.closed_by for i in issues if i.closed_by}))
        )
    }
    accepted: dict[uuid.UUID, str] = {}
    finding_ids = [i.finding_id for i in issues if i.finding_id]
    if finding_ids:
        for suggestion, action in db.execute(
            select(Suggestion, SuggestionFeedback.action)
            .join(SuggestionFeedback, SuggestionFeedback.suggestion_id == Suggestion.id)
            .where(
                Suggestion.finding_id.in_(finding_ids),
                SuggestionFeedback.action.in_((ACCEPTED, ACCEPTED_EDITED)),
            )
        ):
            accepted[suggestion.finding_id] = (
                "an AI suggestion accepted after editing"
                if action == ACCEPTED_EDITED
                else "an AI suggestion accepted as offered"
            )
    result = []
    for issue in issues:
        decision = issue.decision or {}
        result.append(
            {
                "key": f"ISS-{issue.number}",
                "title": issue.title,
                "decided_by": closers.get(issue.closed_by) if issue.closed_by else None,
                "rule": decision.get("rule_name"),
                "reason": (issue.close_reason or "").replace("_", " ") or None,
                "chosen_option": accepted.get(issue.finding_id) if issue.finding_id else None,
            }
        )
    return result


def build(db: Session, project: Project, document: SrsDocument) -> SectionInputs:
    context = context_service.confirmed_context(db, project)
    brief = context_service.confirmed_values(context) if context else BriefValues()
    items = document.requirements or []
    requirement_ids = {uuid.UUID(i["requirement_id"]) for i in items}
    baseline_ids = {i["label"] for i in items if i.get("label")}
    previous = previous_published(db, project.id)
    since_revision = previous.baseline_revision if previous else None
    change_log = _change_log(db, project, since_revision)
    decisions = _decisions(db, project, requirement_ids)
    values: dict[str, Any] = {
        **brief.model_dump(mode="json"),
        "stakeholder_groups": sorted({i["group"] for i in items if i.get("group")}),
        "requirement_ids": sorted(baseline_ids),  # IDs only, for cross-references
        "change_log": change_log,
        "previous_version": previous.version_label if previous else None,
        "decisions": decisions,
    }
    known = set(baseline_ids) | {d["key"] for d in decisions}
    for sentence in change_log:
        known |= keys_in(sentence)
    return SectionInputs(brief=brief, values=values, known_ids=known, baseline_ids=baseline_ids)
