"""The requirements map from stored results (Dhavni — US-14, FR-29, FR-84; SX-16).

Nodes are the project's requirements, with their persisted positions; edges are findings — a pair
finding joins its two requirements, a single-requirement finding (Ambiguous, Incomplete) is a
self-edge the map draws as a badge. An edge is **on the map** while its finding is live: not stale
(superseded by an edit) and not dismissed or merged by a reviewer. ``include_dismissed`` puts
dismissed ones back for the "show dismissed" filter.

Everything is read from the database; building the map never starts an analysis (SX-16).
:func:`nodes` and :func:`edges` load single elements by id for ``app.graph.deltas``.

A 500-requirement map has thousands of edges, so :func:`edges` reads only the columns an edge
shows — not whole findings with their stored model output — and the API serialises the snapshot
once (the CP2 load test: ~0.5 s of CPU per snapshot before, which 50 maps opening together turned
into a 16 s wait).
"""

import uuid
from collections.abc import Collection
from typing import Literal, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.graph.schemas import (
    EdgeKind,
    EdgeStatus,
    GraphEdge,
    GraphNode,
    GraphSnapshot,
    LinkKind,
    NodeState,
)
from app.models import (
    CandidatePair,
    Finding,
    FindingCategory,
    FindingStatus,
    NodePosition,
    Project,
    Requirement,
    RequirementLink,
    RequirementState,
    Severity,
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
        edges=edges(db, project_id, include_dismissed=include_dismissed)
        + link_edges(db, project_id),
    )


def link_edges(
    db: Session, project_id: uuid.UUID, link_ids: Collection[uuid.UUID] | None = None
) -> list[GraphEdge]:
    """Human links (Madhav — US-53, DR-19) as edges of kind ``link``, found by a person and
    confirmed by definition. The edge id is the link id."""
    query = (
        select(RequirementLink)
        .where(RequirementLink.project_id == project_id)
        .order_by(RequirementLink.created_at, RequirementLink.id)
    )
    if link_ids is not None:
        query = query.where(RequirementLink.id.in_(list(link_ids)))
    return [
        GraphEdge(
            id=link.id,
            source=link.source_id,
            target=link.target_id,
            kind="link",
            status="confirmed",
            found_by="person",
            link_kind=cast(LinkKind, link.kind),
        )
        for link in db.scalars(query)
    ]


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
    from app.services.issues import open_counts  # issues import the graph for their deltas

    issues = open_counts(db, project_id, requirement_ids)
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
            open_issues=issues.get(r.id, 0),
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
    query = (
        select(
            Finding.id,
            Finding.category,
            Finding.status,
            Finding.severity,
            Finding.confidence,
            Finding.source,
            Finding.requirement_id,
            Finding.original_ai_output["dependency_direction"].astext,
            CandidatePair.requirement_a_id,
            CandidatePair.requirement_b_id,
        )
        .outerjoin(CandidatePair, CandidatePair.id == Finding.candidate_pair_id)
        .where(Finding.project_id == project_id)
        .order_by(Finding.created_at, Finding.id)
    )
    if finding_ids is not None:
        query = query.where(Finding.id.in_(list(finding_ids)))
    if not include_hidden:
        query = query.where(~Finding.is_stale, Finding.status != FindingStatus.MERGED)
        if not include_dismissed:
            query = query.where(Finding.status != FindingStatus.DISMISSED)
    result: list[GraphEdge] = []
    for row in db.execute(query):
        edge = _edge(*row)
        if edge is not None:
            result.append(edge)
    return result


def edge_of(finding: Finding, pair: CandidatePair | None) -> GraphEdge | None:
    return _edge(
        finding.id,
        finding.category,
        finding.status,
        finding.severity,
        finding.confidence,
        finding.source,
        finding.requirement_id,
        (finding.original_ai_output or {}).get("dependency_direction"),
        pair.requirement_a_id if pair else None,
        pair.requirement_b_id if pair else None,
    )


def _edge(
    finding_id: uuid.UUID,
    category: FindingCategory,
    status: FindingStatus,
    severity: Severity | None,
    confidence: float | None,
    source: str,
    requirement_id: uuid.UUID | None,
    direction: str | None,
    a_id: uuid.UUID | None,
    b_id: uuid.UUID | None,
) -> GraphEdge | None:
    if a_id is not None and b_id is not None:
        source_id, target_id = a_id, b_id
        if category is FindingCategory.DEPENDENT and direction == "B_depends_on_A":
            source_id, target_id = target_id, source_id  # from dependant to dependency
    elif requirement_id is not None:
        source_id = target_id = requirement_id
    else:  # pragma: no cover — the subject CHECK makes this impossible
        return None
    return GraphEdge(
        id=finding_id,
        source=source_id,
        target=target_id,
        kind=KIND[category],
        status=cast(EdgeStatus, status.value),
        severity=cast(EdgeSeverity, severity.value) if severity else None,
        confidence=confidence,
        found_by=cast(Literal["ai", "rule", "person"], source),
    )
