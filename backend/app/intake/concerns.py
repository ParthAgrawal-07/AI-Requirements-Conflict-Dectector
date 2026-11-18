"""Raise a concern (Bansil — US-56, FR-97, NFR-37; design update §11.2; ADR-25).

A person who sees a problem the analysis did not report raises it as a finding of their own:

1. ``POST /projects/{p}/concerns`` with a category, the requirement(s) — two for Conflicting,
   Duplicate and Dependent, one for Ambiguous and Incomplete — an explanation and, optionally,
   what they cite (``external_ref``, e.g. "Contract §7.2") and a severity (default Medium);
2. the finding is stored with ``source=person`` and ``raised_by``; a pair concern reuses the
   pair's ``candidate_pairs`` row, or adds one (``pending``, so a later analysis of the pair
   classifies it as usual and its result sits next to the concern as information);
3. an issue is opened about it (labelled ``concern``), assigned to the requirements' owners;
4. ``ai_miss`` is set when no live AI or rule finding exists on the same requirement(s): the
   count NFR-37 reports;
5. the map shows the new edge with a *Person* badge (``graph.delta``).

Raising needs ``issue.open``: a concern is an issue with a finding behind it. Closing a
person-sourced finding needs its decision owner (Sprint 5, US-57); until then it is reviewed like
any finding.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import BadRequestError
from app.graph import deltas, narrator
from app.graph.service import KIND
from app.models import (
    AuditAction,
    AuditLog,
    CandidatePair,
    Embedding,
    Finding,
    FindingCategory,
    Issue,
    Project,
    Requirement,
    Severity,
)
from app.search.relations import LIVE_STATUSES
from app.services import issues
from app.services.access import AccessContext

PAIR = (FindingCategory.CONFLICTING, FindingCategory.DUPLICATE, FindingCategory.DEPENDENT)


@dataclass
class Concern:
    finding: Finding
    issue: Issue


def _requirements(db: Session, project: Project, ids: list[uuid.UUID]) -> list[Requirement]:
    rows = {
        r.id: r
        for r in db.scalars(
            select(Requirement).where(Requirement.id.in_(ids), Requirement.project_id == project.id)
        )
    }
    if len(rows) != len(set(ids)):
        raise BadRequestError(
            "Every requirement must belong to this project", code="unknown_requirement"
        )
    return [rows[i] for i in ids]


def _similarity(db: Session, a: uuid.UUID, b: uuid.UUID) -> float:
    vectors = {
        row[0]: row[1]
        for row in db.execute(
            select(Embedding.requirement_id, Embedding.vector).where(
                Embedding.requirement_id.in_([a, b])
            )
        )
    }
    if len(vectors) < 2:
        return 0.0
    dot = sum(x * y for x, y in zip(vectors[a], vectors[b], strict=True))
    return max(-1.0, min(1.0, float(dot)))  # the stored vectors are unit length


def _pair(db: Session, a: Requirement, b: Requirement) -> CandidatePair:
    first, second = CandidatePair.ordered(a.id, b.id)
    pair = db.scalar(
        select(CandidatePair).where(
            CandidatePair.requirement_a_id == first, CandidatePair.requirement_b_id == second
        )
    )
    if pair is None:
        pair = CandidatePair(
            requirement_a_id=first,
            requirement_b_id=second,
            similarity_score=_similarity(db, first, second),
        )
        db.add(pair)
        db.flush()
    return pair


def _analysis_saw_it(db: Session, pair: CandidatePair | None, requirement: Requirement) -> bool:
    subject = (
        Finding.candidate_pair_id == pair.id
        if pair is not None
        else Finding.requirement_id == requirement.id
    )
    return (
        db.scalar(
            select(Finding.id)
            .where(
                subject,
                Finding.source != "person",
                Finding.is_stale.is_(False),
                Finding.status.in_(LIVE_STATUSES),
            )
            .limit(1)
        )
        is not None
    )


def raise_concern(
    db: Session,
    ctx: AccessContext,
    project: Project,
    *,
    category: FindingCategory,
    requirement_ids: list[uuid.UUID],
    explanation: str,
    external_ref: str | None = None,
    severity: Severity = Severity.MEDIUM,
) -> Concern:
    wanted = 2 if category in PAIR else 1
    if len(set(requirement_ids)) != wanted or len(requirement_ids) != wanted:
        raise BadRequestError(
            f"A {category.value} concern is about {'two requirements' if wanted == 2 else 'one requirement'}",
            code="wrong_requirement_count",
        )
    requirements = _requirements(db, project, requirement_ids)
    pair = _pair(db, requirements[0], requirements[1]) if wanted == 2 else None
    documents = {r.document_id for r in requirements}
    finding = Finding(
        project_id=project.id,
        document_id=documents.pop() if len(documents) == 1 else None,
        candidate_pair_id=pair.id if pair else None,
        requirement_id=None if pair else requirements[0].id,
        category=category,
        severity=severity,
        confidence=1.0,  # a person's statement, not a model's estimate
        rationale=explanation.strip(),
        explanation=explanation.strip(),
        original_ai_output={},  # nothing came from a model
        source="person",
        raised_by=ctx.user.id,
        external_ref=(external_ref or "").strip() or None,
        ai_miss=not _analysis_saw_it(db, pair, requirements[0]),
    )
    db.add(finding)
    db.flush()
    db.add(
        AuditLog(
            workspace_id=project.workspace_id,
            actor_id=ctx.user.id,
            finding_id=finding.id,
            action=AuditAction.CONCERN_RAISED,
            details={
                "requirement_ids": [str(r.id) for r in requirements],
                "category": category.value,
                "ai_miss": finding.ai_miss,
            },
        )
    )
    db.commit()

    labels = sorted(deltas.label_of(r) for r in requirements)
    deltas.publish(
        db,
        project.id,
        deltas.Change(
            new_findings={finding.id},
            sentences=[narrator.concern_raised(ctx.user.full_name, KIND[category], labels)],
        ),
        actor=ctx.user,
    )
    body = finding.explanation or ""
    if finding.external_ref:
        body += f"\n\nReference: {finding.external_ref}"
    issue = issues.open_issue(
        db,
        project=project,
        author=ctx.user,
        title=f"Concern: {category.value} — {' and '.join(labels)}",
        body=body,
        labels=["concern", category.value.lower(), f"severity:{severity.value}"],
        assignees=sorted({r.owner_id for r in requirements if r.owner_id is not None}),
        requirements=[r.id for r in requirements],
        finding=finding,
        members_only=True,
    )
    return Concern(finding, issue)
