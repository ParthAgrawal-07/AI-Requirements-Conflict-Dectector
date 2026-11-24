"""Relationship queries (Heet — US-11, FR-24, FR-25; design update §3.2, §11.4).

What is a requirement related to? The impact analysis (Madhav, ``app.consequences.impact``)
asks this for the requirement a change request touches; the findings delta asks it for the
requirements it must re-check. Three sources, strongest first:

* **findings** — a live (not stale, not dismissed or merged) Conflicting, Duplicate or Dependent
  finding links the two requirements of its pair. Dependent keeps its direction
  (``depends_on``: this requirement needs the other; ``required_by``: the other needs this one);
* **human links** — ``requirement_links`` (US-53, migration 0008a): a person asserted *depends
  on*, *refines* or *related to*. They count as confirmed and are walked like findings
  (:func:`link_edges`); nothing here or anywhere automatic removes one (DR-19);
* **shared embeddings** — the nearest neighbours of the requirement's vector above the project's
  similarity threshold that no finding links yet (``similar``): a pointer, never a verdict
  (DR-10), so the impact report marks them *potential*.

:func:`related` walks **one hop** from the source over all three, then a **second hop** over
findings only — a neighbour's neighbours by embedding would be most of a large project and say
nothing about the change. Each requirement appears once, at its smallest depth and with its
strongest relation, with the path it was reached by. Rejected and Deprecated requirements are
never related: they are out of the baseline and are not analysed again.
"""

import uuid
from collections.abc import Collection, Iterable
from dataclasses import dataclass, field
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.embeddings.candidates import EXCLUDED_STATES
from app.embeddings.store import nearest_requirements
from app.models import (
    CandidatePair,
    Embedding,
    Finding,
    FindingCategory,
    FindingStatus,
    Project,
    Requirement,
    RequirementLink,
)

# A finding still says something about its requirements in these states (US-10).
LIVE_STATUSES = (FindingStatus.FLAGGED, FindingStatus.CONFIRMED, FindingStatus.RECLASSIFIED)
SIMILAR_K = 5


class RelationKind(StrEnum):
    CONFLICT = "conflict"
    DUPLICATE = "duplicate"
    DEPENDS_ON = "depends_on"  # the source needs the related requirement
    REQUIRED_BY = "required_by"  # the related requirement needs the source
    DEPENDENCY = "dependency"  # Dependent without a direction
    REFINES = "refines"  # a person said the source refines the related requirement (US-53)
    REFINED_BY = "refined_by"  # … or the related requirement refines the source
    RELATED = "related"  # a person said the two are related (US-53)
    SIMILAR = "similar"  # shared embedding only


# Strongest first: when two relations reach the same requirement at the same depth, this wins.
STRENGTH = {
    RelationKind.CONFLICT: 0,
    RelationKind.DUPLICATE: 1,
    RelationKind.DEPENDS_ON: 2,
    RelationKind.REQUIRED_BY: 2,
    RelationKind.DEPENDENCY: 2,
    RelationKind.REFINES: 2,
    RelationKind.REFINED_BY: 2,
    RelationKind.RELATED: 3,
    RelationKind.SIMILAR: 4,
}
# A human link seen from each end: (from the link's source, from its target).
_LINK_KINDS = {
    "depends_on": (RelationKind.DEPENDS_ON, RelationKind.REQUIRED_BY),
    "refines": (RelationKind.REFINES, RelationKind.REFINED_BY),
    "related_to": (RelationKind.RELATED, RelationKind.RELATED),
}
_PAIR_KINDS = {
    FindingCategory.CONFLICTING: RelationKind.CONFLICT,
    FindingCategory.DUPLICATE: RelationKind.DUPLICATE,
    FindingCategory.DEPENDENT: RelationKind.DEPENDENCY,
}


@dataclass(frozen=True)
class Edge:
    """One finding (or human link) between two requirements, seen from ``source``."""

    source: uuid.UUID
    target: uuid.UUID
    kind: RelationKind
    finding_id: uuid.UUID | None
    severity: str | None
    link_id: uuid.UUID | None = None


@dataclass
class Related:
    requirement_id: uuid.UUID
    label: str | None  # printed ID, e.g. "REQ-014"
    depth: int  # 1 = direct, 2 = through one other requirement
    kind: RelationKind
    path: list[uuid.UUID]  # from the source to this requirement, both ends included
    finding_id: uuid.UUID | None = None  # the finding of the last hop; None for ``similar``
    similarity: float | None = None  # for ``similar``
    severity: str | None = None
    owner_id: uuid.UUID | None = None
    is_protected: bool = False
    via: list[RelationKind] = field(default_factory=list)  # the kind of every hop on the path
    link_id: uuid.UUID | None = None  # the human link of the last hop (US-53): confirmed


def _directed(kind: RelationKind, source_is_a: bool, direction: object) -> RelationKind:
    if kind is not RelationKind.DEPENDENCY or direction not in ("A_depends_on_B", "B_depends_on_A"):
        return kind
    source_depends = (direction == "A_depends_on_B") == source_is_a
    return RelationKind.DEPENDS_ON if source_depends else RelationKind.REQUIRED_BY


def finding_edges(db: Session, requirement_ids: Collection[uuid.UUID]) -> list[Edge]:
    """Every live pair finding touching ``requirement_ids``, once per end in the set."""
    if not requirement_ids:
        return []
    ids = list(requirement_ids)
    rows = db.execute(
        select(Finding, CandidatePair)
        .join(CandidatePair, CandidatePair.id == Finding.candidate_pair_id)
        .where(
            ~Finding.is_stale,
            Finding.status.in_(LIVE_STATUSES),
            Finding.category.in_(list(_PAIR_KINDS)),
            (CandidatePair.requirement_a_id.in_(ids)) | (CandidatePair.requirement_b_id.in_(ids)),
        )
    )
    wanted = set(ids)
    edges: list[Edge] = []
    for finding, pair in rows:
        direction = (finding.original_ai_output or {}).get("dependency_direction")
        severity = finding.severity.value if finding.severity else None
        kind = _PAIR_KINDS[finding.category]
        a, b = pair.requirement_a_id, pair.requirement_b_id
        if a in wanted:
            edges.append(Edge(a, b, _directed(kind, True, direction), finding.id, severity))
        if b in wanted:
            edges.append(Edge(b, a, _directed(kind, False, direction), finding.id, severity))
    return edges


def link_edges(db: Session, requirement_ids: Collection[uuid.UUID]) -> list[Edge]:
    """Every human link touching ``requirement_ids``, once per end in the set (US-53)."""
    if not requirement_ids:
        return []
    ids = list(requirement_ids)
    wanted = set(ids)
    rows = db.scalars(
        select(RequirementLink).where(
            RequirementLink.source_id.in_(ids) | RequirementLink.target_id.in_(ids)
        )
    )
    edges: list[Edge] = []
    for link in rows:
        forward, backward = _LINK_KINDS[link.kind]
        if link.source_id in wanted:
            edges.append(Edge(link.source_id, link.target_id, forward, None, None, link.id))
        if link.target_id in wanted:
            edges.append(Edge(link.target_id, link.source_id, backward, None, None, link.id))
    return edges


def similar_neighbours(
    db: Session, requirement: Requirement, *, k: int = SIMILAR_K, exclude: Iterable[uuid.UUID] = ()
) -> list[tuple[uuid.UUID, float]]:
    """The requirement's nearest neighbours by embedding, above the project's threshold."""
    vector = db.scalar(select(Embedding.vector).where(Embedding.requirement_id == requirement.id))
    if vector is None:
        return []
    project = db.get(Project, requirement.project_id)
    threshold = project.similarity_threshold if project else None
    neighbours = nearest_requirements(
        db,
        requirement.project_id,
        list(vector),
        k=k,
        min_similarity=threshold,
        exclude={requirement.id, *exclude},
        exclude_states=EXCLUDED_STATES,
    )
    return [(n.requirement_id, min(1.0, n.similarity)) for n in neighbours]


def related(
    db: Session,
    requirement_id: uuid.UUID,
    *,
    hops: int = 2,
    similar_k: int = SIMILAR_K,
) -> list[Related]:
    """Requirements related to ``requirement_id``, nearest and strongest first (see module doc)."""
    source = db.get(Requirement, requirement_id)
    if source is None:
        return []
    found: dict[uuid.UUID, Related] = {}

    def offer(candidate: Related) -> None:
        current = found.get(candidate.requirement_id)
        if current is None or (candidate.depth, STRENGTH[candidate.kind]) < (
            current.depth,
            STRENGTH[current.kind],
        ):
            found[candidate.requirement_id] = candidate

    for edge in [*finding_edges(db, [source.id]), *link_edges(db, [source.id])]:
        offer(
            Related(
                edge.target,
                None,
                1,
                edge.kind,
                [source.id, edge.target],
                edge.finding_id,
                severity=edge.severity,
                via=[edge.kind],
                link_id=edge.link_id,
            )
        )
    linked = set(found)
    for neighbour_id, similarity in similar_neighbours(db, source, k=similar_k, exclude=linked):
        offer(
            Related(
                neighbour_id,
                None,
                1,
                RelationKind.SIMILAR,
                [source.id, neighbour_id],
                similarity=round(similarity, 3),
                via=[RelationKind.SIMILAR],
            )
        )

    rows = _in_baseline_or_proposed(db, found)
    found = {key: value for key, value in found.items() if key in rows}
    if hops >= 2:
        first = {r.requirement_id: r for r in found.values() if r.depth == 1}
        for edge in [*finding_edges(db, list(first)), *link_edges(db, list(first))]:
            if edge.target == source.id:
                continue
            parent = first[edge.source]
            offer(
                Related(
                    edge.target,
                    None,
                    2,
                    edge.kind,
                    [*parent.path, edge.target],
                    edge.finding_id,
                    severity=edge.severity,
                    via=[*parent.via, edge.kind],
                    link_id=edge.link_id,
                )
            )

    found.pop(source.id, None)
    rows.update(_in_baseline_or_proposed(db, set(found) - set(rows)))
    result = []
    for item in found.values():
        requirement = rows.get(item.requirement_id)
        if requirement is None:
            continue
        item.label = requirement.source_req_id
        item.owner_id = requirement.owner_id
        item.is_protected = requirement.is_protected
        result.append(item)
    result.sort(key=lambda r: (r.depth, STRENGTH[r.kind], r.label or "", str(r.requirement_id)))
    return result


def _in_baseline_or_proposed(
    db: Session, requirement_ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, Requirement]:
    if not requirement_ids:
        return {}
    return {
        r.id: r
        for r in db.scalars(select(Requirement).where(Requirement.id.in_(list(requirement_ids))))
        if r.state not in EXCLUDED_STATES
    }
