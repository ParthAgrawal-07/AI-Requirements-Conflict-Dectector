"""Requirement activity timeline route (Dhavni — US-42, FR-72).

``GET /requirements/{requirement_id}/timeline`` (``view``) — everything that happened to the
requirement, newest first (``order=asc`` for oldest first), optionally filtered by ``kind``
(repeatable). Visible to every member who can see the requirement; another workspace's
requirement is a 404.
"""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal, get_args

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.api.deps import DbSession, requires
from app.core.errors import NotFoundError
from app.models import Requirement
from app.schemas.common import ErrorResponse
from app.services import compliance
from app.services import timeline as timeline_service
from app.services.access import AccessContext

router = APIRouter(tags=["timeline"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
}
TimelineKind = Literal[
    "post",
    "version",
    "state",
    "analysis",
    "finding",
    "review",
    "clarification",
    "issue",
    "change_request",
    "merge",
    "comment",
    "owner",
    "baseline",
    "vote",
    "link",
]
if set(get_args(TimelineKind)) != set(timeline_service.KINDS):  # pragma: no cover
    raise RuntimeError("TimelineKind and timeline KINDS disagree")


class TimelineEntryRead(BaseModel):
    at: datetime
    kind: str
    title: str
    actor_id: uuid.UUID | None
    actor_name: str | None
    link_type: str | None
    link_id: uuid.UUID | None
    detail: str | None


class TimelineRead(BaseModel):
    requirement_id: uuid.UUID
    label: str | None
    kinds: list[str]  # every kind the filter can take
    entries: list[TimelineEntryRead]


@router.get(
    "/requirements/{requirement_id}/timeline",
    response_model=TimelineRead,
    summary="Everything that happened to a requirement",
    responses=_ERRORS,
)
def get_timeline(
    requirement_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
    kind: Annotated[list[TimelineKind] | None, Query()] = None,
    order: Literal["asc", "desc"] = "desc",
) -> TimelineRead:
    requirement = db.get(Requirement, requirement_id)
    if requirement is None:  # defensive
        raise NotFoundError("Requirement not found")
    compliance.record_view(db, ctx, requirement, "timeline")  # Parth (US-18, NFR-13)
    entries = timeline_service.timeline(
        db, requirement, kinds=kind or (), newest_first=order == "desc"
    )
    return TimelineRead(
        requirement_id=requirement.id,
        label=requirement.source_req_id,
        kinds=list(timeline_service.KINDS),
        entries=[TimelineEntryRead.model_validate(vars(e)) for e in entries],
    )
