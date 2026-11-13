"""Findings, read side (Keval — US-07, FR-13, FR-14, NFR-17).

Lists and loads a project's findings with everything the finding card needs: the requirements
involved (with their source section, or the post they came from), so every flag can be judged
without leaving the card. Stale findings (US-34, Sprint 4) are history and not listed.

Reviewing findings (confirm, dismiss, merge, reclassify) is US-10, Sprint 3.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, aliased

from app.core.errors import NotFoundError
from app.models import (
    AuditAction,
    AuditLog,
    CandidatePair,
    Finding,
    FindingCategory,
    FindingStatus,
    Project,
    Requirement,
    User,
)
from app.services.access import Scope, register_scope_resolver


@dataclass(frozen=True)
class FindingView:
    finding: Finding
    requirements: list[Requirement]  # A then B for a pair; the one requirement otherwise
    confidence_threshold: float

    @property
    def low_confidence(self) -> bool:
        return self.finding.confidence < self.confidence_threshold


def _involved(db: Session, findings: list[Finding]) -> dict[uuid.UUID, list[Requirement]]:
    pair_ids = [f.candidate_pair_id for f in findings if f.candidate_pair_id]
    pairs = {
        pair.id: pair
        for pair in db.scalars(select(CandidatePair).where(CandidatePair.id.in_(pair_ids)))
    }
    wanted: set[uuid.UUID] = {f.requirement_id for f in findings if f.requirement_id}
    for pair in pairs.values():
        wanted |= {pair.requirement_a_id, pair.requirement_b_id}
    by_id = {r.id: r for r in db.scalars(select(Requirement).where(Requirement.id.in_(wanted)))}
    involved: dict[uuid.UUID, list[Requirement]] = {}
    for finding in findings:
        if finding.candidate_pair_id and (subject := pairs.get(finding.candidate_pair_id)):
            ids = [subject.requirement_a_id, subject.requirement_b_id]
        else:
            ids = [finding.requirement_id] if finding.requirement_id else []
        involved[finding.id] = [by_id[i] for i in ids if i in by_id]
    return involved


def list_findings(
    db: Session,
    project: Project,
    *,
    category: FindingCategory | None = None,
    status: FindingStatus | None = None,
    requirement_id: uuid.UUID | None = None,
    low_confidence: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[FindingView], int]:
    """A page of the project's live findings, most confident first, and the total."""
    conditions = [Finding.project_id == project.id, Finding.is_stale.is_(False)]
    if category is not None:
        conditions.append(Finding.category == category)
    if status is not None:
        conditions.append(Finding.status == status)
    if low_confidence is True:
        conditions.append(Finding.confidence < project.confidence_threshold)
    elif low_confidence is False:
        conditions.append(Finding.confidence >= project.confidence_threshold)
    if requirement_id is not None:
        pair = aliased(CandidatePair)
        conditions.append(
            or_(
                Finding.requirement_id == requirement_id,
                Finding.candidate_pair_id.in_(
                    select(pair.id).where(
                        or_(
                            pair.requirement_a_id == requirement_id,
                            pair.requirement_b_id == requirement_id,
                        )
                    )
                ),
            )
        )
    total = db.scalar(select(func.count(Finding.id)).where(*conditions)) or 0
    rows = list(
        db.scalars(
            select(Finding)
            .where(*conditions)
            .order_by(Finding.confidence.desc(), Finding.created_at, Finding.id)
            .limit(limit)
            .offset(offset)
        )
    )
    involved = _involved(db, rows)
    views = [FindingView(f, involved[f.id], project.confidence_threshold) for f in rows]
    return views, total


def get_finding(
    db: Session, finding_id: uuid.UUID, viewer: User, workspace_id: uuid.UUID
) -> FindingView:
    """One finding. Opening a finding about a protected requirement is audited (NFR-13)."""
    finding = db.get(Finding, finding_id)
    if finding is None:
        raise NotFoundError("Finding not found")
    project = db.get(Project, finding.project_id)
    if project is None:
        raise NotFoundError("Finding not found")
    requirements = _involved(db, [finding])[finding.id]
    for requirement in requirements:
        if requirement.is_protected:
            db.add(
                AuditLog(
                    workspace_id=workspace_id,
                    actor_id=viewer.id,
                    finding_id=finding.id,
                    requirement_id=requirement.id,
                    action=AuditAction.VIEWED_PROTECTED,
                )
            )
    db.commit()
    return FindingView(finding, requirements, project.confidence_threshold)


def _finding_scope(db: Session, finding_id: uuid.UUID) -> Scope | None:
    row = db.execute(
        select(Project.workspace_id, Project.id)
        .join(Finding, Finding.project_id == Project.id)
        .where(Finding.id == finding_id)
    ).first()
    return None if row is None else Scope(row[0], row[1])


register_scope_resolver("finding_id", _finding_scope)
