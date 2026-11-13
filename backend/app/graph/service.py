"""Graph API v0 (Dhavni — US-14 groundwork, Sprint 2): the map snapshot from stored findings.

Nodes are the project's requirements; edges are findings — a pair finding joins its two
requirements, a single-requirement finding (Ambiguous, Incomplete) is a self-edge the map draws as
a badge. Dismissed findings are left out unless asked for. Findings are found through their
requirements' project, so the query does not depend on how findings are tied to documents.

``revision`` is 0 until ``projects.graph_revision`` and ``graph.delta`` arrive with US-14
(Sprint 3); a client treats every snapshot as fresh until then.
"""

import uuid
from typing import Literal, cast

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, aliased

from app.graph.schemas import EdgeKind, GraphEdge, GraphNode, GraphSnapshot, NodeState
from app.models import (
    CandidatePair,
    Finding,
    FindingCategory,
    FindingStatus,
    Requirement,
    RequirementState,
)

EdgeSeverity = Literal["low", "medium", "high"]

_KIND: dict[FindingCategory, EdgeKind] = {
    FindingCategory.CONFLICTING: "conflict",
    FindingCategory.DUPLICATE: "duplicate",
    FindingCategory.DEPENDENT: "depends_on",
    FindingCategory.AMBIGUOUS: "ambiguous",
    FindingCategory.INCOMPLETE: "incomplete",
}


def snapshot(
    db: Session, project_id: uuid.UUID, *, include_dismissed: bool = False
) -> GraphSnapshot:
    requirements = list(
        db.scalars(
            select(Requirement)
            .where(Requirement.project_id == project_id)
            .order_by(Requirement.order_index, Requirement.id)
        )
    )
    nodes = [
        GraphNode(
            id=r.id,
            label=r.source_req_id,
            state=cast(NodeState, RequirementState(r.state).value),
            group=r.stakeholder_group,
            owner_id=r.owner_id,
        )
        for r in requirements
    ]
    return GraphSnapshot(
        project_id=project_id,
        revision=0,
        nodes=nodes,
        edges=_edges(db, project_id, include_dismissed=include_dismissed),
    )


def _edges(db: Session, project_id: uuid.UUID, *, include_dismissed: bool) -> list[GraphEdge]:
    a = aliased(Requirement)
    single = aliased(Requirement)
    query = (
        select(Finding, CandidatePair)
        .outerjoin(CandidatePair, CandidatePair.id == Finding.candidate_pair_id)
        .outerjoin(a, a.id == CandidatePair.requirement_a_id)
        .outerjoin(single, single.id == Finding.requirement_id)
        .where(or_(a.project_id == project_id, single.project_id == project_id))
        .order_by(Finding.created_at, Finding.id)
    )
    if not include_dismissed:
        query = query.where(Finding.status != FindingStatus.DISMISSED)
    edges: list[GraphEdge] = []
    for finding, pair in db.execute(query):
        if pair is not None:
            source, target = pair.requirement_a_id, pair.requirement_b_id
            direction = (finding.original_ai_output or {}).get("dependency_direction")
            if finding.category is FindingCategory.DEPENDENT and direction == "B_depends_on_A":
                source, target = target, source  # an edge points from dependant to dependency
        elif finding.requirement_id is not None:
            source = target = finding.requirement_id
        else:  # pragma: no cover — the subject CHECK makes this impossible
            continue
        edges.append(
            GraphEdge(
                id=finding.id,
                source=source,
                target=target,
                kind=_KIND[finding.category],
                severity=cast(EdgeSeverity, finding.severity.value) if finding.severity else None,
                confidence=finding.confidence,
            )
        )
    return edges
