"""Quality dashboard counts (Parth — US-13 aggregation, FR-27, FR-28, FR-42, NFR-16).

One function per dashboard: :func:`project_dashboard` and :func:`workspace_dashboard`. Every
number is a ``COUNT`` over the same rows the lists show, so a card's number equals the list it
drills into (and a direct database count on demo data — the US-13 acceptance test):

=====================  ========================================================================
findings               live (not stale) findings by category, severity, status and source
requirements           by lifecycle state
change requests        open ones (open, needs update, approved) by the risk of their latest
                       consequence report (``unknown`` before the checks ran)
issues                 open and closed, and closed by reason
=====================  ========================================================================

**Filters** narrow the requirements first (ID, type, stakeholder group, owner, state, priority);
findings, change requests and issues then count when they concern one of those requirements.
"""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    CandidatePair,
    ChangeRequest,
    ConsequenceReport,
    Finding,
    Issue,
    IssueRequirement,
    Project,
    Requirement,
    RequirementState,
)
from app.models.change_request import APPROVED, NEEDS_UPDATE, OPEN
from app.models.issue import CLOSED
from app.models.issue import OPEN as ISSUE_OPEN

OPEN_REQUESTS = (OPEN, NEEDS_UPDATE, APPROVED)


@dataclass(frozen=True)
class Filters:
    requirement_id: uuid.UUID | None = None
    req_type: str | None = None
    stakeholder_group: str | None = None
    owner_id: uuid.UUID | None = None
    state: RequirementState | None = None
    priority: str | None = None

    @property
    def any(self) -> bool:
        return any(value is not None for value in vars(self).values())

    def as_json(self) -> dict[str, str]:
        return {k: str(getattr(v, "value", v)) for k, v in vars(self).items() if v is not None}


def _requirements(project_id: uuid.UUID, filters: Filters) -> Select[Any]:
    query = select(Requirement.id).where(Requirement.project_id == project_id)
    if filters.requirement_id is not None:
        query = query.where(Requirement.id == filters.requirement_id)
    if filters.req_type is not None:
        query = query.where(Requirement.req_type == filters.req_type)
    if filters.stakeholder_group is not None:
        query = query.where(
            func.lower(Requirement.stakeholder_group) == filters.stakeholder_group.lower()
        )
    if filters.owner_id is not None:
        query = query.where(Requirement.owner_id == filters.owner_id)
    if filters.state is not None:
        query = query.where(Requirement.state == filters.state)
    if filters.priority is not None:
        query = query.where(Requirement.priority == filters.priority)
    return query


def _grouped(db: Session, column: Any, query: Select[Any]) -> dict[str, int]:
    rows = db.execute(
        query.with_only_columns(column, func.count()).group_by(column).order_by(column)
    ).tuples()
    return {str(getattr(key, "value", key) if key is not None else "unset"): n for key, n in rows}


def _with_zeros(counts: dict[str, int], keys: Iterable[str]) -> dict[str, int]:
    return {**dict.fromkeys(keys, 0), **counts}


def project_dashboard(
    db: Session, project: Project, filters: Filters | None = None
) -> dict[str, Any]:
    filters = filters or Filters()
    requirement_ids = _requirements(project.id, filters)
    findings = select(Finding).where(Finding.project_id == project.id, ~Finding.is_stale)
    if filters.any:
        pairs = select(CandidatePair.id).where(
            or_(
                CandidatePair.requirement_a_id.in_(requirement_ids),
                CandidatePair.requirement_b_id.in_(requirement_ids),
            )
        )
        findings = findings.where(
            or_(Finding.requirement_id.in_(requirement_ids), Finding.candidate_pair_id.in_(pairs))
        )
    requirements = select(Requirement).where(Requirement.id.in_(requirement_ids))

    latest = (
        select(
            ConsequenceReport.change_request_id,
            ConsequenceReport.risk_level,
            func.row_number()
            .over(
                partition_by=ConsequenceReport.change_request_id,
                order_by=ConsequenceReport.created_at.desc(),
            )
            .label("n"),
        )
    ).subquery()
    risk = func.coalesce(latest.c.risk_level, "unknown")
    requests = (
        select(ChangeRequest)
        .outerjoin(latest, (latest.c.change_request_id == ChangeRequest.id) & (latest.c.n == 1))
        .where(ChangeRequest.project_id == project.id, ChangeRequest.status.in_(OPEN_REQUESTS))
    )
    if filters.any:
        requests = requests.where(ChangeRequest.requirement_id.in_(requirement_ids))

    issues = select(Issue).where(Issue.project_id == project.id)
    if filters.any:
        linked = select(IssueRequirement.issue_id).where(
            IssueRequirement.requirement_id.in_(requirement_ids)
        )
        issues = issues.where(Issue.id.in_(linked))

    def total(query: Select[Any]) -> int:
        return db.scalar(query.with_only_columns(func.count())) or 0

    return {
        "project_id": str(project.id),
        "filters": filters.as_json(),
        "findings": {
            "total": total(findings),
            "by_category": _grouped(db, Finding.category, findings),
            "by_severity": _grouped(db, Finding.severity, findings),
            "by_status": _grouped(db, Finding.status, findings),
            "by_source": _with_zeros(
                _grouped(db, Finding.source, findings), ("ai", "rule", "person")
            ),
        },
        "requirements": {
            "total": total(requirements),
            "by_state": _with_zeros(
                _grouped(db, Requirement.state, requirements), (s.value for s in RequirementState)
            ),
        },
        "change_requests": {
            "open": total(requests),
            "by_risk": _with_zeros(
                _grouped(db, risk, requests), ("low", "medium", "high", "unknown")
            ),
        },
        "issues": {
            "open": total(issues.where(Issue.status == ISSUE_OPEN)),
            "closed": total(issues.where(Issue.status == CLOSED)),
            "closed_by_reason": _grouped(
                db, Issue.close_reason, issues.where(Issue.status == CLOSED)
            ),
            "auto_open": total(issues.where(Issue.status == ISSUE_OPEN, Issue.auto.is_(True))),
        },
    }


def workspace_dashboard(db: Session, projects: list[Project]) -> dict[str, Any]:
    """Each project's headline numbers, and their sum."""
    rows = []
    for project in projects:
        board = project_dashboard(db, project)
        rows.append(
            {
                "project_id": str(project.id),
                "name": project.name,
                "status": project.status.value,
                "requirements": board["requirements"]["total"],
                "open_findings": board["findings"]["by_status"].get("flagged", 0),
                "high_findings": board["findings"]["by_severity"].get("high", 0),
                "open_change_requests": board["change_requests"]["open"],
                "high_risk_change_requests": board["change_requests"]["by_risk"]["high"],
                "open_issues": board["issues"]["open"],
            }
        )
    keys = [k for k in (rows[0] if rows else {}) if k not in ("project_id", "name", "status")]
    return {"projects": rows, "totals": {k: sum(r[k] for r in rows) for k in keys}}
