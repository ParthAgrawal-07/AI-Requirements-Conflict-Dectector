"""The readiness checklist shown before an updated SRS is generated (Bansil — US-61, FR-106).

Four checks on the requirements the SRS will include (the chosen baseline's Approved and
Implemented requirements):

=========================  ========================================================================
``open_questions``         clarification questions not yet answered on their live findings
``high_findings``          open High-severity findings, unless the approval of the requirement's
                           current version recorded an accepted risk (US-37)
``open_change_requests``   change requests on them still open, approved or needing an update
``open_issues``            open issues about them
=========================  ========================================================================

Each blocking item links to where it is fixed. Generation is allowed when nothing blocks, or after
a Project Manager's override with a reason — the open-items report is then attached (US-59).
"""

import uuid
from collections.abc import Collection
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import (
    CandidatePair,
    ChangeRequest,
    Clarification,
    Finding,
    FindingStatus,
    Issue,
    IssueRequirement,
    Requirement,
    RequirementTransition,
    Severity,
)
from app.models.change_request import APPROVED, NEEDS_UPDATE, OPEN

LIVE = (FindingStatus.FLAGGED, FindingStatus.CONFIRMED, FindingStatus.RECLASSIFIED)
MAX_LINKS = 20


@dataclass
class Check:
    key: str
    label: str
    count: int = 0
    links: list[dict[str, Any]] = field(default_factory=list)  # {type, id, key}

    @property
    def ok(self) -> bool:
        return self.count == 0

    def as_json(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "ok": self.ok,
            "count": self.count,
            "links": self.links,
        }


def _live_findings(db: Session, ids: list[uuid.UUID]) -> list[tuple[Finding, list[uuid.UUID]]]:
    rows = db.execute(
        select(Finding, CandidatePair)
        .outerjoin(CandidatePair, CandidatePair.id == Finding.candidate_pair_id)
        .where(
            ~Finding.is_stale,
            Finding.status.in_(LIVE),
            or_(
                Finding.requirement_id.in_(ids),
                CandidatePair.requirement_a_id.in_(ids),
                CandidatePair.requirement_b_id.in_(ids),
            ),
        )
        .order_by(Finding.created_at, Finding.id)
    ).all()
    result = []
    for finding, pair in rows:
        involved = (
            [pair.requirement_a_id, pair.requirement_b_id]
            if pair is not None
            else [finding.requirement_id]
            if finding.requirement_id
            else []
        )
        result.append((finding, involved))
    return result


def _accepted_risk(db: Session, requirements: dict[uuid.UUID, Requirement]) -> set[uuid.UUID]:
    """Requirements whose current version was approved with an accepted risk."""
    if not requirements:
        return set()
    rows = db.execute(
        select(RequirementTransition.requirement_id, RequirementTransition.version).where(
            RequirementTransition.requirement_id.in_(list(requirements)),
            RequirementTransition.accepted_risk.is_(True),
        )
    )
    return {
        requirement_id
        for requirement_id, version in rows
        if requirements[requirement_id].current_version == version
    }


def check(db: Session, requirement_ids: Collection[uuid.UUID]) -> list[Check]:
    ids = list(requirement_ids)
    checks = [
        Check("open_questions", "Open clarification questions"),
        Check("high_findings", "Open High findings without an accepted risk"),
        Check("open_change_requests", "Open change requests on included requirements"),
        Check("open_issues", "Open issues on included requirements"),
    ]
    if not ids:
        return checks
    questions, high, changes, issues = checks
    requirements = {r.id: r for r in db.scalars(select(Requirement).where(Requirement.id.in_(ids)))}
    labels = {rid: (r.source_req_id or str(rid)[:8]) for rid, r in requirements.items()}
    risked = _accepted_risk(db, requirements)
    findings = _live_findings(db, ids)
    open_questions = {
        c.finding_id
        for c in db.scalars(
            select(Clarification).where(
                Clarification.finding_id.in_([f.id for f, _ in findings]),
                Clarification.resolved_at.is_(None),
            )
        )
    }
    for finding, involved in findings:
        key = " & ".join(labels.get(i, "?") for i in involved if i in labels) or "a finding"
        link = {"type": "finding", "id": str(finding.id), "key": key}
        if finding.id in open_questions:
            questions.count += 1
            questions.links.append(link)
        if finding.severity is Severity.HIGH and not any(i in risked for i in involved):
            high.count += 1
            high.links.append(link)
    for change in db.scalars(
        select(ChangeRequest)
        .where(
            ChangeRequest.requirement_id.in_(ids),
            ChangeRequest.status.in_((OPEN, APPROVED, NEEDS_UPDATE)),
        )
        .order_by(ChangeRequest.number)
    ):
        changes.count += 1
        changes.links.append(
            {"type": "change_request", "id": str(change.id), "key": f"RCR-{change.number}"}
        )
    for issue in db.scalars(
        select(Issue)
        .join(IssueRequirement, IssueRequirement.issue_id == Issue.id)
        .where(IssueRequirement.requirement_id.in_(ids), Issue.status == "open")
        .distinct()
        .order_by(Issue.number)
    ):
        issues.count += 1
        issues.links.append({"type": "issue", "id": str(issue.id), "key": f"ISS-{issue.number}"})
    for item in checks:
        item.links = item.links[:MAX_LINKS]
    return checks


def blocking(checks: list[Check]) -> list[Check]:
    return [c for c in checks if not c.ok]
