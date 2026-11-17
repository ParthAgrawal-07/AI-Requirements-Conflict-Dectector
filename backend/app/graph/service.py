"""The requirements map from stored results (Dhavni — US-14, FR-29, FR-84; SX-16).

Nodes are the project's requirements, with their persisted positions; edges are findings — a pair
finding joins its two requirements, a single-requirement finding (Ambiguous, Incomplete) is a
self-edge the map draws as a badge. An edge is **on the map** while its finding is live: not stale
(superseded by an edit) and not dismissed or merged by a reviewer. ``include_dismissed`` puts
dismissed ones back for the "show dismissed" filter.

Everything is read from the database; building the map never starts an analysis (SX-16).
:func:`nodes` and :func:`edges` load single elements by id for ``app.graph.deltas``.
"""

import uuid
from collections.abc import Collection
from typing import Literal, cast

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, aliased

from app.graph.schemas import EdgeKind, EdgeStatus, GraphEdge, GraphNode, GraphSnapshot, NodeState
from app.models import (
    CandidatePair,
    Finding,
    FindingCategory,
    FindingStatus,
    NodePosition,
    Project,
    Requirement,
    RequirementState,
)

EdgeSeverity = Literal["low", "medium", "high"]

KIND: dict[FindingCategory, EdgeKind] = {
    FindingCategory.CONFLICTING: "conflict",
    FindingCategory.DUPLICATE: "duplicate",
    FindingCategory.DEPENDENT: "depends_on",
    FindingCategory.AMBIGUOUS: "ambiguous",
    FindingCategory.INCOMPLETE: "incomplete",
}
OFF_THE_MAP = (FindingStatus.DISMISSED, FindingStatus.MERGED)


def on_the_map(finding: Finding, *, include_dismissed: bool = False) -> bool:
    if finding.is_stale or finding.status is FindingStatus.MERGED:
        return False
    return include_dismissed or finding.status is not FindingStatus.DISMISSED


def snapshot(
    db: Session, project_id: uuid.UUID, *, include_dismissed: bool = False
) -> GraphSnapshot:
    project = db.get(Project, project_id)
    revision = project.graph_revision if project is not None else 0
    return GraphSnapshot(
        project_id=project_id,
        revision=revision,
        nodes=nodes(db, project_id),
        edges=edges(db, project_id, include_dismissed=include_dismissed),
    )


def nodes(
    db: Session, project_id: uuid.UUID, requirement_ids: Collection[uuid.UUID] | None = None
) -> list[GraphNode]:
    """The project's nodes (all, or those in ``requirement_ids``), in source order."""
    query = (
        select(Requirement, NodePosition)
        .outerjoin(NodePosition, NodePosition.requirement_id == Requirement.id)
        .where(Requirement.project_id == project_id)
        .order_by(Requirement.created_at, Requirement.order_index, Requirement.id)
    )
    if requirement_ids is not None:
        query = query.where(Requirement.id.in_(list(requirement_ids)))
    return [
        GraphNode(
            id=r.id,
            label=r.source_req_id,
            state=cast(NodeState, RequirementState(r.state).value),
            group=r.stakeholder_group,
            owner_id=r.owner_id,
            req_type=r.req_type,
            origin=r.origin.value,
            is_protected=r.is_protected,
            x=position.x if position else None,
            y=position.y if position else None,
        )
        for r, position in db.execute(query)
    ]


def edges(
    db: Session,
    project_id: uuid.UUID,
    finding_ids: Collection[uuid.UUID] | None = None,
    *,
    include_dismissed: bool = False,
    include_hidden: bool = False,
) -> list[GraphEdge]:
    """Edges of the project's findings (all, or those in ``finding_ids``).

    ``include_hidden`` also returns findings that are off the map (stale, dismissed, merged) —
    the delta builder needs them to know what to remove.
    """
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
    if finding_ids is not None:
        query = query.where(Finding.id.in_(list(finding_ids)))
    if not include_hidden:
        query = query.where(Finding.is_stale.is_(False), Finding.status != FindingStatus.MERGED)
        if not include_dismissed:
            query = query.where(Finding.status != FindingStatus.DISMISSED)
    result: list[GraphEdge] = []
    for finding, pair in db.execute(query):
        edge = edge_of(finding, pair)
        if edge is not None:
            result.append(edge)
    return result


def edge_of(finding: Finding, pair: CandidatePair | None) -> GraphEdge | None:
    if pair is not None:
        source, target = pair.requirement_a_id, pair.requirement_b_id
        direction = (finding.original_ai_output or {}).get("dependency_direction")
        if finding.category is FindingCategory.DEPENDENT and direction == "B_depends_on_A":
            source, target = target, source  # an edge points from dependant to dependency
    elif finding.requirement_id is not None:
        source = target = finding.requirement_id
    else:  # pragma: no cover — the subject CHECK makes this impossible
        return None
    return GraphEdge(
        id=finding.id,
        source=source,
        target=target,
        kind=KIND[finding.category],
        status=cast(EdgeStatus, finding.status.value),
        severity=cast(EdgeSeverity, finding.severity.value) if finding.severity else None,
        confidence=finding.confidence,
    )
