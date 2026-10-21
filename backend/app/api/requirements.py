"""Requirement routes (Parth — US-04).

``GET /projects/{p}/requirements`` is the data behind the requirements screen: paginated and
searchable, with the printed document ID (``REQ-n``), text, state, owner and origin, filterable by
``state``, ``origin``, ``owner``, ``document_id`` and a free-text ``q`` (case-insensitive, over
text and printed ID).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbSession, requires
from app.models import RequirementOrigin, RequirementState
from app.schemas.common import ErrorResponse, Page
from app.schemas.documents import RequirementRead
from app.services import requirements as requirement_service
from app.services.access import AccessContext

router = APIRouter(tags=["requirements"])


@router.get(
    "/projects/{project_id}/requirements",
    response_model=Page[RequirementRead],
    summary="List a project's requirements",
    responses={404: {"model": ErrorResponse, "description": "Not a member, or no such project"}},
)
def list_requirements(
    project_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
    q: Annotated[
        str | None, Query(max_length=200, description="Case-insensitive search in ID and text")
    ] = None,
    state: Annotated[
        RequirementState | None, Query(description="Filter by lifecycle state")
    ] = None,
    origin: Annotated[RequirementOrigin | None, Query(description="Filter by origin")] = None,
    owner: Annotated[uuid.UUID | None, Query(description="Filter by owner user id")] = None,
    document_id: Annotated[uuid.UUID | None, Query(description="Only this document's")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[RequirementRead]:
    requirements, total = requirement_service.list_requirements(
        db,
        project_id,
        query=q,
        state=state,
        origin=origin,
        owner_id=owner,
        document_id=document_id,
        limit=limit,
        offset=offset,
    )
    return Page[RequirementRead](
        items=[RequirementRead.from_model(item) for item in requirements],
        total=total,
        limit=limit,
        offset=offset,
    )
