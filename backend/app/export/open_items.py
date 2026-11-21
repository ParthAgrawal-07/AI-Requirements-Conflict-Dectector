"""The open-items report beside an approved baseline (Bansil — US-59, FR-102, DR-22; design
update §11.6, ``OpenItemsReport``).

The SRS export contains **only** Approved and Implemented requirements; everything unresolved is
listed here instead, for the same baseline revision, so a polished SRS never hides open
disagreements or mixes in unapproved suggestions:

* proposed requirements (Proposed, Under review);
* open findings, by source (AI, rule, person) and severity;
* open issues, with their decision owners (US-57);
* change requests closed or withdrawn without merging, with the reason given;
* accepted risks: approvals and merges made while a High finding was open, with the reason.

:func:`excluded_counts` is the first-page note of the SRS export and the banner on the Baselines
screen ("4 proposed requirements, 3 open findings and 1 open change request are not in this
export").
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AuditAction,
    AuditLog,
    CandidatePair,
    ChangeRequest,
    Finding,
    FindingStatus,
    Issue,
    Project,
    Requirement,
    RequirementState,
    RequirementTransition,
    User,
)
from app.models.change_request import APPROVED, CLOSED, NEEDS_UPDATE, OPEN, WITHDRAWN
from app.services.decision_rules import Decision, DecisionRuleEngine, facts_for_issue

LIVE = (FindingStatus.FLAGGED, FindingStatus.CONFIRMED, FindingStatus.RECLASSIFIED)
PROPOSED = (RequirementState.PROPOSED, RequirementState.UNDER_REVIEW)
OPEN_CHANGES = (OPEN, APPROVED, NEEDS_UPDATE)
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2, None: 3}
SOURCE_NAMES = {"ai": "AI", "rule": "Rule", "person": "Person"}


@dataclass
class OpenItems:
    project_name: str
    baseline_revision: int
    baseline_label: str | None
    generated_at: datetime
    proposed: list[dict[str, Any]] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)
    issues: list[dict[str, Any]] = field(default_factory=list)
    closed_change_requests: list[dict[str, Any]] = field(default_factory=list)
    accepted_risks: list[dict[str, Any]] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    def as_json(self) -> dict[str, Any]:
        return {
            "project_name": self.project_name,
            "baseline_revision": self.baseline_revision,
            "baseline_label": self.baseline_label,
            "generated_at": self.generated_at.isoformat(),
            "proposed": self.proposed,
            "findings": self.findings,
            "issues": self.issues,
            "closed_change_requests": self.closed_change_requests,
            "accepted_risks": self.accepted_risks,
            "counts": self.counts,
        }


def _label(requirement: Requirement | None) -> str:
    if requirement is None:
        return "?"
    return requirement.source_req_id or f"requirement {str(requirement.id)[:8]}"


def excluded_counts(db: Session, project_id: uuid.UUID) -> dict[str, int]:
    """What an SRS export of this project leaves out, as counts (the first-page note)."""

    def count(query: Any) -> int:
        return int(db.scalar(query) or 0)

    return {
        "proposed_requirements": count(
            select(func.count())
            .select_from(Requirement)
            .where(Requirement.project_id == project_id, Requirement.state.in_(PROPOSED))
        ),
        "open_findings": count(
            select(func.count())
            .select_from(Finding)
            .where(Finding.project_id == project_id, ~Finding.is_stale, Finding.status.in_(LIVE))
        ),
        "open_change_requests": count(
            select(func.count())
            .select_from(ChangeRequest)
            .where(ChangeRequest.project_id == project_id, ChangeRequest.status.in_(OPEN_CHANGES))
        ),
        "open_issues": count(
            select(func.count())
            .select_from(Issue)
            .where(Issue.project_id == project_id, Issue.status == "open")
        ),
    }


def exclusion_note(counts: dict[str, int]) -> str:
    parts = []
    for key, one, many in (
        ("proposed_requirements", "proposed requirement", "proposed requirements"),
        ("open_findings", "open finding", "open findings"),
        ("open_change_requests", "open change request", "open change requests"),
        ("open_issues", "open issue", "open issues"),
    ):
        n = counts.get(key, 0)
        if n:
            parts.append(f"{n} {one if n == 1 else many}")
    head = "This document contains only Approved and Implemented requirements."
    if not parts:
        return head + " Nothing was left out."
    listed = ", ".join(parts[:-1]) + (" and " if len(parts) > 1 else "") + parts[-1]
    return f"{head} Not included: {listed} — see the open-items report for the same revision."


def build(
    db: Session, project: Project, *, baseline_revision: int, baseline_label: str | None,
    generated_at: datetime,
) -> OpenItems:  # fmt: skip
    report = OpenItems(
        project_name=project.name,
        baseline_revision=baseline_revision,
        baseline_label=baseline_label,
        generated_at=generated_at,
    )
    users: dict[uuid.UUID, str] = {}

    def name(user_id: uuid.UUID | None) -> str | None:
        if user_id is None:
            return None
        if user_id not in users:
            user = db.get(User, user_id)
            users[user_id] = user.full_name if user else "a former member"
        return users[user_id]

    for r in db.scalars(
        select(Requirement)
        .where(Requirement.project_id == project.id, Requirement.state.in_(PROPOSED))
        .order_by(Requirement.created_at, Requirement.id)
    ):
        report.proposed.append(
            {
                "id": str(r.id),
                "label": _label(r),
                "state": r.state.value.replace("_", " "),
                "owner": name(r.owner_id),
                "body": r.body,
            }  # fmt: skip
        )

    rows = db.execute(
        select(Finding, CandidatePair)
        .outerjoin(CandidatePair, CandidatePair.id == Finding.candidate_pair_id)
        .where(Finding.project_id == project.id, ~Finding.is_stale, Finding.status.in_(LIVE))
    ).all()
    involved_ids = {
        x
        for f, p in rows
        for x in ([p.requirement_a_id, p.requirement_b_id] if p else [f.requirement_id])
        if x
    }
    labels = {
        r.id: _label(r)
        for r in (
            db.scalars(select(Requirement).where(Requirement.id.in_(involved_ids)))
            if involved_ids
            else []
        )
    }
    for finding, pair in rows:
        ids = [pair.requirement_a_id, pair.requirement_b_id] if pair else [finding.requirement_id]
        severity = finding.severity.value if finding.severity else None
        report.findings.append(
            {
                "id": str(finding.id),
                "category": finding.category.value,
                "source": SOURCE_NAMES.get(finding.source, finding.source),
                "severity": severity,
                "status": finding.status.value,
                "requirements": [labels.get(i, "?") for i in ids if i],
            }  # fmt: skip
        )
    report.findings.sort(
        key=lambda f: (f["source"], SEVERITY_ORDER.get(f["severity"], 3), f["category"])
    )

    engine = DecisionRuleEngine(db)
    for issue in db.scalars(
        select(Issue)
        .where(Issue.project_id == project.id, Issue.status == "open")
        .order_by(Issue.number)
    ):
        owner = None
        if issue.decision:  # US-57: who decides, as the project's rules resolved it
            decision = Decision.from_json(issue.decision)
            owners = engine.owners(project, decision, facts_for_issue(db, issue))
            owner = engine.owner_name(decision, owners)
        report.issues.append(
            {
                "id": str(issue.id),
                "key": f"ISS-{issue.number}",
                "title": issue.title,
                "decision_owner": owner,
                "labels": list(issue.labels or []),
            }  # fmt: skip
        )

    for change in db.scalars(
        select(ChangeRequest)
        .where(
            ChangeRequest.project_id == project.id, ChangeRequest.status.in_((CLOSED, WITHDRAWN))
        )  # fmt: skip
        .order_by(ChangeRequest.number)
    ):
        requirement = db.get(Requirement, change.requirement_id)
        report.closed_change_requests.append(
            {
                "id": str(change.id),
                "key": f"RCR-{change.number}",
                "requirement": _label(requirement),
                "status": change.status,
                "reason": change.close_reason,
                "closed_by": name(change.closed_by),
            }  # fmt: skip
        )

    for transition in db.scalars(
        select(RequirementTransition)
        .join(Requirement, Requirement.id == RequirementTransition.requirement_id)
        .where(Requirement.project_id == project.id, RequirementTransition.accepted_risk.is_(True))
        .order_by(RequirementTransition.created_at)
    ):
        report.accepted_risks.append(
            {
                "requirement": _label(db.get(Requirement, transition.requirement_id)),
                "what": f"approved version {transition.version} with a High finding open",
                "reason": transition.reason,
                "by": name(transition.actor_id),
                "at": transition.created_at.isoformat(),
            }  # fmt: skip
        )
    project_requirements = select(Requirement.id).where(Requirement.project_id == project.id)
    for row in db.scalars(
        select(AuditLog)
        .where(
            AuditLog.action == AuditAction.CHANGE_REQUEST_MERGED,
            AuditLog.requirement_id.in_(project_requirements),
            AuditLog.details["accepted_risk"].astext == "true",
        )
        .order_by(AuditLog.at)
    ):
        report.accepted_risks.append(
            {
                "requirement": _label(db.get(Requirement, row.requirement_id)),
                "what": "merged a change request with a High finding open",
                "reason": (row.details or {}).get("accepted_risk_reason"),
                "by": name(row.actor_id),
                "at": row.at.isoformat(),
            }  # fmt: skip
        )
    report.counts = excluded_counts(db, project.id)
    return report


def to_markdown(report: OpenItems) -> str:
    revision = f"baseline revision {report.baseline_revision}"
    if report.baseline_label:
        revision += f" (snapshot {report.baseline_label})"
    lines = [
        f"# Open items — {report.project_name}",
        "",
        f"**For {revision}** · generated {report.generated_at.strftime('%d %b %Y %H:%M UTC')}",
        "",
        "These items are **not** part of the approved specification. Read them with the SRS "
        "export of the same baseline revision.",
        "",
        "## Proposed requirements",
        "",
    ]
    if report.proposed:
        for item in report.proposed:
            lines.append(
                f"**{item['label']}** · {item['state']} · Owner: {item['owner'] or 'unassigned'}"
            )
            lines.append("")
            lines.append("> " + item["body"].replace("\n", "\n> "))
            lines.append("")
    else:
        lines += ["_None._", ""]
    lines += ["## Open findings", ""]
    if report.findings:
        lines += [
            f"- {f['source']} · {f['severity'] or 'no severity'} · {f['category']} on "
            f"{' and '.join(f['requirements'])} ({f['status']})"
            for f in report.findings
        ]
    else:
        lines.append("_None._")
    lines += ["", "## Open issues", ""]
    lines += [
        f"- {i['key']}: {i['title']} — decision owner: {i['decision_owner'] or 'not set'}"
        for i in report.issues
    ] or ["_None._"]
    lines += ["", "## Change requests closed without merging", ""]
    lines += [
        f"- {c['key']} on {c['requirement']} ({c['status']})"
        + (f": {c['reason']}" if c["reason"] else "")
        for c in report.closed_change_requests
    ] or ["_None._"]
    lines += ["", "## Accepted risks", ""]
    lines += [
        f"- {r['requirement']}: {r['what']}"
        + (f" — {r['reason']}" if r["reason"] else "")
        + (f" ({r['by']})" if r["by"] else "")
        for r in report.accepted_risks
    ] or ["_None._"]
    return "\n".join(lines) + "\n"
