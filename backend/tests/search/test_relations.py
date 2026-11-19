"""Relationship queries on a fixture graph (Heet — US-11).

::

    R2 ──conflict── R1 ──depends on── R3          R1's embedding is close to R9's
     │               │╲
  conflict      dismissed  stale   conflict        R9 ──conflict── R10
     │               │        ╲       │
    R4              R5         R6    R7 (Deprecated) ──conflict── R8
"""

import math
import uuid
from collections.abc import Callable

import pytest
from sqlalchemy.orm import Session

from app.models import (
    CandidatePair,
    Embedding,
    Finding,
    FindingCategory,
    FindingStatus,
    Project,
    Requirement,
    RequirementState,
    Severity,
)
from app.models.embedding import EMBEDDING_DIM
from app.search.relations import Related, RelationKind, finding_edges, related


def unit(angle: float) -> list[float]:
    """A unit vector at ``angle`` radians in the first plane: cosine = cos(angle difference)."""
    vector = [0.0] * EMBEDDING_DIM
    vector[0], vector[1] = math.cos(angle), math.sin(angle)
    return vector


class Graph:
    def __init__(self, db: Session, project: Project, make: Callable[..., Requirement]) -> None:
        self.db, self.project, self.make = db, project, make
        self.r: dict[int, Requirement] = {}

    def node(self, n: int, **kwargs: object) -> Requirement:
        self.r[n] = self.make(f"Requirement {n}.", source_req_id=f"REQ-{n:03d}", **kwargs)
        return self.r[n]

    def finding(
        self,
        a: int,
        b: int,
        category: FindingCategory = FindingCategory.CONFLICTING,
        *,
        direction: str | None = None,
        status: FindingStatus = FindingStatus.FLAGGED,
        stale: bool = False,
    ) -> Finding:
        first, second = CandidatePair.ordered(self.r[a].id, self.r[b].id)
        pair = CandidatePair(requirement_a_id=first, requirement_b_id=second, similarity_score=0.9)
        self.db.add(pair)
        self.db.flush()
        # The direction is stated for the pair's own A/B order, as the classifier states it.
        if direction is not None and first != self.r[a].id:
            direction = {"A_depends_on_B": "B_depends_on_A", "B_depends_on_A": "A_depends_on_B"}[
                direction
            ]
        finding = Finding(
            project_id=self.project.id,
            candidate_pair_id=pair.id,
            category=category,
            confidence=0.9,
            rationale="r",
            severity=Severity.HIGH,
            status=status,
            is_stale=stale,
            original_ai_output={"dependency_direction": direction},
        )
        self.db.add(finding)
        self.db.commit()
        return finding

    def embed(self, n: int, angle: float) -> None:
        self.db.add(Embedding(requirement_id=self.r[n].id, vector=unit(angle), model_version="t"))
        self.db.commit()


@pytest.fixture
def graph(
    db_session: Session, project: Project, make_requirement: Callable[..., Requirement]
) -> Graph:
    project.similarity_threshold = 0.8
    g = Graph(db_session, project, make_requirement)
    for n in (1, 2, 3, 4, 5, 6, 8, 9, 10, 11):
        g.node(n, state=RequirementState.APPROVED)
    g.node(7, state=RequirementState.DEPRECATED)
    g.finding(1, 2)
    g.finding(1, 3, FindingCategory.DEPENDENT, direction="A_depends_on_B")  # R1 needs R3
    g.finding(2, 4)
    g.finding(1, 5, status=FindingStatus.DISMISSED)
    g.finding(1, 6, stale=True)
    g.finding(1, 7)
    g.finding(7, 8)
    g.finding(9, 10)
    g.embed(1, 0.0)
    g.embed(9, 0.3)  # cos 0.3 ≈ 0.955: above the threshold
    g.embed(2, 0.2)  # similar too, but the conflict is the stronger relation
    g.embed(4, 1.2)  # cos 1.2 ≈ 0.36: not similar
    g.embed(11, 0.65)  # close to R2 (cos 0.45 ≈ 0.90), not to R1 (cos 0.65 ≈ 0.80 − ε)
    return g


def by_label(graph: Graph, source: int) -> dict[str | None, Related]:
    return {r.label: r for r in related(graph.db, graph.r[source].id)}


def test_one_hop_from_findings_with_direction(graph: Graph) -> None:
    found = by_label(graph, 1)
    conflict, dependency = found["REQ-002"], found["REQ-003"]
    assert (conflict.depth, conflict.kind) == (1, RelationKind.CONFLICT)
    assert conflict.severity == "high"
    assert dependency.kind is RelationKind.DEPENDS_ON


def test_the_direction_reverses_from_the_other_end(graph: Graph) -> None:
    assert by_label(graph, 3)["REQ-001"].kind is RelationKind.REQUIRED_BY


def test_two_hops_keep_the_path(graph: Graph) -> None:
    far = by_label(graph, 1)["REQ-004"]
    assert far.depth == 2
    assert far.path == [graph.r[1].id, graph.r[2].id, graph.r[4].id]
    assert far.via == [RelationKind.CONFLICT, RelationKind.CONFLICT]


def test_dismissed_stale_and_deprecated_relations_are_left_out(graph: Graph) -> None:
    found = by_label(graph, 1)
    assert {"REQ-005", "REQ-006", "REQ-007"}.isdisjoint(found)
    assert "REQ-008" not in found  # only reachable through the deprecated R7


def test_shared_embeddings_add_similar_requirements_no_finding_links(graph: Graph) -> None:
    found = by_label(graph, 1)
    similar = found["REQ-009"]
    assert (similar.depth, similar.kind) == (1, RelationKind.SIMILAR)
    assert similar.finding_id is None and similar.similarity > 0.9
    assert found["REQ-002"].kind is RelationKind.CONFLICT


def test_the_second_hop_follows_findings_only(graph: Graph) -> None:
    found = by_label(graph, 1)
    assert "REQ-011" not in found  # an embedding neighbour of R2, not of R1
    through_similar = found["REQ-010"]  # R9's conflict, R9 being similar to R1
    assert (through_similar.depth, through_similar.via) == (
        2,
        [RelationKind.SIMILAR, RelationKind.CONFLICT],
    )


def test_one_hop_only_and_order(graph: Graph) -> None:
    labels = [r.label for r in related(graph.db, graph.r[1].id, hops=1)]
    assert labels == ["REQ-002", "REQ-003", "REQ-009"]


def test_finding_edges_seen_from_each_end(graph: Graph) -> None:
    edges = finding_edges(graph.db, [graph.r[2].id, graph.r[4].id])
    labels = {r.id: r.source_req_id for r in graph.r.values()}
    pairs = {(labels[e.source], e.kind) for e in edges}  # type: ignore[union-attr]
    assert pairs == {
        ("REQ-002", RelationKind.CONFLICT),
        ("REQ-004", RelationKind.CONFLICT),
    }
    assert len(edges) == 3  # R2–R1, R2–R4 from R2; R4–R2 from R4


def test_an_unknown_requirement_has_no_relations(db_session: Session) -> None:
    assert related(db_session, uuid.uuid4()) == []
