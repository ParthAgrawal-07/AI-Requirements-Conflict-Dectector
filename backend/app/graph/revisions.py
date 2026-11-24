"""The map at earlier points in time (Dhavni — US-50, FR-85; the time slider).

The slider moves through **baseline revisions** (each merge into the agreed baseline starts a new
one, US-35) and **labelled baselines** (US-40). At each such point the whole map is frozen into
``graph_snapshots`` so it can be shown later exactly as it was, read-only:

* :func:`capture_revision` — called by ``app.graph.deltas.publish`` for every delta: when the
  project's baseline revision has no snapshot yet, the map as it stands right after that merge is
  stored (one query to check, so the common case costs almost nothing);
* :func:`capture_baseline` — called by ``app.services.baselines.snapshot`` in the transaction that
  freezes a labelled baseline.

:func:`points` lists what the slider can show, oldest first, ending with "now"; :func:`state`
returns one point's map. A snapshot stores what the map showed then (nodes with their state and
position, edges with their review status), so a later review or edit does not rewrite history.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.graph import service as graph_service
from app.graph.schemas import GraphEdge, GraphNode
from app.models import Baseline, GraphState, Project


@dataclass(frozen=True)
class Point:
    id: uuid.UUID | None  # the snapshot; None for "now"
    label: str  # "Baseline revision 3", "v1.0 sign-off", "Now"
    kind: str  # "baseline_revision", "baseline", "now"
    baseline_revision: int
    graph_revision: int
    at: datetime | None
    baseline_id: uuid.UUID | None = None
    nodes: int = 0
    edges: int = 0


def _freeze(
    db: Session, project: Project
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    snapshot = graph_service.snapshot(db, project.id)
    return (
        [n.model_dump(mode="json") for n in snapshot.nodes],
        [e.model_dump(mode="json") for e in snapshot.edges],
    )


def capture_revision(db: Session, project_id: uuid.UUID) -> bool:
    """Freeze the map for the project's current baseline revision if not done yet (commits).

    Baseline revision 0 (nothing merged yet) is not frozen: there is no agreed baseline to show.
    """
    project = db.get(Project, project_id)
    if project is None or project.baseline_revision < 1:
        return False
    exists = db.scalar(
        select(GraphState.id).where(
            GraphState.project_id == project_id,
            GraphState.baseline_revision == project.baseline_revision,
            GraphState.baseline_id.is_(None),
        )
    )
    if exists is not None:
        return False
    nodes, edges = _freeze(db, project)
    db.execute(
        insert(GraphState)
        .values(
            project_id=project_id,
            graph_revision=project.graph_revision,
            baseline_revision=project.baseline_revision,
            nodes=nodes,
            edges=edges,
        )
        .on_conflict_do_nothing(
            index_elements=["project_id", "baseline_revision"],
            index_where=GraphState.baseline_id.is_(None),
        )
    )
    db.commit()
    return True


def capture_baseline(db: Session, project: Project, baseline: Baseline) -> GraphState:
    """Freeze the map with a labelled baseline. Does not commit (the caller's transaction)."""
    nodes, edges = _freeze(db, project)
    row = GraphState(
        project_id=project.id,
        graph_revision=project.graph_revision,
        baseline_revision=project.baseline_revision,
        baseline_id=baseline.id,
        nodes=nodes,
        edges=edges,
    )
    db.add(row)
    return row


def points(db: Session, project: Project) -> list[Point]:
    labels = {
        b.id: b.label for b in db.scalars(select(Baseline).where(Baseline.project_id == project.id))
    }
    rows = db.scalars(
        select(GraphState)
        .where(GraphState.project_id == project.id)
        .order_by(GraphState.captured_at, GraphState.graph_revision)
    )
    result = [
        Point(
            id=row.id,
            label=(
                labels.get(row.baseline_id, "Baseline")
                if row.baseline_id
                else f"Baseline revision {row.baseline_revision}"
            ),
            kind="baseline" if row.baseline_id else "baseline_revision",
            baseline_revision=row.baseline_revision,
            graph_revision=row.graph_revision,
            at=row.captured_at,
            baseline_id=row.baseline_id,
            nodes=len(row.nodes or []),
            edges=len(row.edges or []),
        )
        for row in rows
    ]
    result.append(
        Point(
            id=None,
            label="Now",
            kind="now",
            baseline_revision=project.baseline_revision,
            graph_revision=project.graph_revision,
            at=None,
        )
    )
    return result


def state(row: GraphState) -> tuple[list[GraphNode], list[GraphEdge]]:
    """A frozen map, validated back into the live map's schema."""
    return (
        [GraphNode.model_validate(n) for n in row.nodes or []],
        [GraphEdge.model_validate(e) for e in row.edges or []],
    )
