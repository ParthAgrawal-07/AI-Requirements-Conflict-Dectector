"""Graph routes (Dhavni — US-14 groundwork). ``GET /projects/{p}/graph`` needs ``view``."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbSession, requires
from app.graph import service as graph_service
from app.graph.schemas import GraphSnapshot
from app.schemas.common import ErrorResponse
from app.services.access import AccessContext

router = APIRouter(tags=["map"])


@router.get(
    "/projects/{project_id}/graph",
    response_model=GraphSnapshot,
    summary="The requirements map: requirements as nodes, findings as edges",
    responses={404: {"model": ErrorResponse}},
)
def get_graph(
    project_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
    include_dismissed: Annotated[bool, Query()] = False,
) -> GraphSnapshot:
    return graph_service.snapshot(db, project_id, include_dismissed=include_dismissed)
