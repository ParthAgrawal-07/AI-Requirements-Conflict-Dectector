"""Requirement listing (Parth — US-04, FR-04, DR-06).

Read side of the requirements table for the UI's requirements screen: a paginated,
searchable list for one project, filterable by lifecycle state, origin, owner and document.
Source order is kept within a document so printed IDs read naturally (FR-04).

Not here yet: the "issue badges" of the US-04 card need the issues tables (Sprint 4).
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models import Requirement, RequirementOrigin, RequirementState


def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def list_requirements(
    db: Session,
    project_id: uuid.UUID,
    *,
    query: str | None = None,
    state: RequirementState | None = None,
    origin: RequirementOrigin | None = None,
    owner_id: uuid.UUID | None = None,
    document_id: uuid.UUID | None = None,
    limit: int,
    offset: int,
) -> tuple[list[Requirement], int]:
    """A page of the project's requirements and the total number of matches."""
    conditions = [Requirement.project_id == project_id]
    if query and query.strip():
        pattern = f"%{_escape_like(query.strip())}%"
        conditions.append(
            Requirement.body.ilike(pattern, escape="\\")
            | Requirement.source_req_id.ilike(pattern, escape="\\")
        )
    if state is not None:
        conditions.append(Requirement.state == state)
    if origin is not None:
        conditions.append(Requirement.origin == origin)
    if owner_id is not None:
        conditions.append(Requirement.owner_id == owner_id)
    if document_id is not None:
        conditions.append(Requirement.document_id == document_id)

    total = db.scalar(select(func.count(Requirement.id)).where(*conditions)) or 0
    rows = db.scalars(
        select(Requirement)
        .where(*conditions)
        .options(joinedload(Requirement.owner))
        # created_at groups a document's rows (inserted together); order_index keeps source
        # order inside it; id makes pagination stable when both tie.
        .order_by(Requirement.created_at, Requirement.order_index, Requirement.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return list(rows), total
