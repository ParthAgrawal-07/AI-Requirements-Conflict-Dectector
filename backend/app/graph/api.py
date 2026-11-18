"""Map routes (Dhavni — US-14).

* ``GET /projects/{p}/graph`` (``view``) — the snapshot. ``?revision=r`` answers **304** when *r*
  is still current, so a client re-checking after a reconnect downloads nothing.
* ``PUT /projects/{p}/graph/positions`` (``req.comment``) — save where nodes are. The layout is
  shared, so arranging it is for members who take part in the discussion, not viewers. Publishes
  a layout-only ``graph.delta`` (no sentences) so other open maps move the same nodes.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response

from app.api.deps import DbSession, requires
from app.graph import deltas, positions
from app.graph import service as graph_service
from app.graph.schemas import GraphSnapshot, PositionsUpdate
from app.models import Project
from app.schemas.common import ErrorResponse
from app.services.access import AccessContext

router = APIRouter(tags=["map"])


@router.get(
    "/projects/{project_id}/graph",
    response_model=GraphSnapshot,
    summary="The requirements map: requirements as nodes, findings as edges",
    responses={
        304: {"description": "`revision` is still the current revision"},
        404: {"model": ErrorResponse},
    },
)
def get_graph(
    project_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
    include_dismissed: Annotated[bool, Query()] = False,
    revision: Annotated[
        int | None, Query(ge=0, description="The revision the client holds")
    ] = None,
) -> GraphSnapshot | Response:
    if revision is not None:
        project = db.get(Project, project_id)
        if project is not None and project.graph_revision == revision:
            return Response(status_code=304)
    return graph_service.snapshot(db, project_id, include_dismissed=include_dismissed)


@router.put(
    "/projects/{project_id}/graph/positions",
    status_code=204,
    summary="Save node positions (the shared layout)",
    responses={400: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
def put_positions(
    project_id: uuid.UUID,
    body: PositionsUpdate,
    ctx: Annotated[AccessContext, requires("req.comment")],
    db: DbSession,
) -> Response:
    saved = positions.save(db, project_id, body.positions, ctx.user.id)
    deltas.publish(db, project_id, deltas.Change(requirements=set(saved)), actor=ctx.user)
    return Response(status_code=204)
