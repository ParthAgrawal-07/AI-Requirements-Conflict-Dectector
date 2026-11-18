"""Persisted map layout (Dhavni — US-14; interface design §9 "Stable layout").

* :func:`save` — ``PUT /projects/{p}/graph/positions``: a client that has laid out or dragged
  nodes stores where they are, for everyone. Only the project's own requirements; upsert.
* :func:`place_near_neighbours` — a new node appears **next to its nearest neighbour** instead of
  wherever a fresh layout would throw it, so nothing else on the map moves. The offset is
  derived from the requirement id, so two new neighbours of one node do not land on each other.

A requirement nobody has placed yet has no row; the client lays it out and saves the result.
"""

import hashlib
import math
import uuid
from collections.abc import Collection, Mapping, Sequence

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.errors import BadRequestError
from app.graph.schemas import NodePlacement
from app.models import NodePosition, Requirement

NEIGHBOUR_DISTANCE = 140.0  # map units: about one node width plus a label


def save(
    db: Session, project_id: uuid.UUID, placements: Sequence[NodePlacement], actor_id: uuid.UUID
) -> list[uuid.UUID]:
    """Store positions; returns the requirement ids saved. Unknown ids are a 400, not ignored:
    a client sending another project's ids has a bug worth seeing."""
    wanted = {p.requirement_id: p for p in placements}  # last write wins within one request
    known = set(
        db.scalars(
            select(Requirement.id).where(
                Requirement.project_id == project_id, Requirement.id.in_(list(wanted))
            )
        )
    )
    if known != set(wanted):
        raise BadRequestError(
            "Some positions are for requirements that are not in this project",
            code="unknown_requirement",
        )
    _upsert(
        db,
        project_id,
        {rid: (p.x, p.y) for rid, p in wanted.items()},
        actor_id=actor_id,
    )
    db.commit()
    return list(wanted)


def place_near_neighbours(
    db: Session,
    project_id: uuid.UUID,
    neighbours: Mapping[uuid.UUID, Sequence[uuid.UUID]],
) -> set[uuid.UUID]:
    """Give each requirement in ``neighbours`` that has no position one next to the first of its
    neighbours that has. Returns the ids placed (the caller commits)."""
    if not neighbours:
        return set()
    involved: set[uuid.UUID] = set(neighbours)
    for others in neighbours.values():
        involved |= set(others)
    placed = {
        row.requirement_id: (row.x, row.y)
        for row in db.scalars(
            select(NodePosition).where(NodePosition.requirement_id.in_(list(involved)))
        )
    }
    new: dict[uuid.UUID, tuple[float, float]] = {}
    for requirement_id, others in neighbours.items():
        if requirement_id in placed:
            continue
        anchor = next((placed[o] for o in others if o in placed), None)
        if anchor is None:
            continue
        angle = _angle(requirement_id)
        new[requirement_id] = (
            anchor[0] + NEIGHBOUR_DISTANCE * math.cos(angle),
            anchor[1] + NEIGHBOUR_DISTANCE * math.sin(angle),
        )
        placed[requirement_id] = new[requirement_id]
    if new:
        _upsert(db, project_id, new, actor_id=None)
    return set(new)


def positioned(db: Session, requirement_ids: Collection[uuid.UUID]) -> set[uuid.UUID]:
    return set(
        db.scalars(
            select(NodePosition.requirement_id).where(
                NodePosition.requirement_id.in_(list(requirement_ids))
            )
        )
    )


def _angle(requirement_id: uuid.UUID) -> float:
    digest = hashlib.sha256(requirement_id.bytes).digest()
    return (int.from_bytes(digest[:4], "big") / 2**32) * 2 * math.pi


def _upsert(
    db: Session,
    project_id: uuid.UUID,
    coordinates: Mapping[uuid.UUID, tuple[float, float]],
    *,
    actor_id: uuid.UUID | None,
) -> None:
    rows = [
        {"requirement_id": rid, "project_id": project_id, "x": x, "y": y, "updated_by": actor_id}
        for rid, (x, y) in coordinates.items()
    ]
    statement = insert(NodePosition).values(rows)
    db.execute(
        statement.on_conflict_do_update(
            index_elements=[NodePosition.requirement_id],
            set_={
                "x": statement.excluded.x,
                "y": statement.excluded.y,
                "updated_by": statement.excluded.updated_by,
                "updated_at": func.now(),
            },
        )
    )
