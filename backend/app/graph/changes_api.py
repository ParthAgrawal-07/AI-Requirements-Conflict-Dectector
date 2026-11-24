"""Change log, time slider and preview routes (Dhavni — US-55, US-50; design update §3.8).

==============================================================  =================================
``GET /projects/{p}/changes``                                   the written change log, newest
                                                                first; filters ``since``,
                                                                ``until``, ``actor``, ``kind``,
                                                                ``requirement``, ``until_revision``
``GET /projects/{p}/changes/summary``                           counts and important changes since
                                                                a date, a baseline or the caller's
                                                                last visit (+ Markdown)
``PUT /projects/{p}/changes/seen``                              "I have read the log up to now"
``GET /projects/{p}/graph/revisions``                           the time slider's points
``GET /projects/{p}/graph/revisions/{graph_snapshot_id}``       the map at one point, read-only
``GET /change-requests/{change_request_id}/graph-preview``      what a merge would do to the map
==============================================================  =================================

Everything needs ``view`` — whoever sees the map may read its history. ``PUT …/seen`` writes the
caller's own read marker only. A since-baseline from another project is a 404.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Any, Literal, cast, get_args

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import DbSession, requires
from app.core.errors import BadRequestError, NotFoundError
from app.graph import changelog, preview, revisions
from app.graph.schemas import EdgeKind, GraphEdge, GraphNode
from app.models import Baseline, ChangeRequest, GraphState, Project
from app.models.graph import EVENT_KINDS
from app.schemas.common import ErrorResponse
from app.services.access import AccessContext, Scope, register_scope_resolver

router = APIRouter(tags=["changes"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
}
EventKind = Literal[
    "added",
    "changed",
    "state",
    "owner",
    "analysed",
    "conflict_found",
    "conflict_resolved",
    "reviewed",
    "issue",
    "change_request",
    "merged",
    "concern",
    "link",
]
if set(get_args(EventKind)) != set(EVENT_KINDS):  # pragma: no cover — a typo is a bug
    raise RuntimeError("EventKind and EVENT_KINDS disagree")


class ChangeEventRead(BaseModel):
    id: uuid.UUID
    at: datetime
    revision: int | None
    kind: EventKind
    sentence: str
    actor_id: uuid.UUID | None
    actor_name: str | None
    node_ids: list[uuid.UUID]
    edge_ids: list[uuid.UUID]
    backfilled: bool


class ChangeLogPage(BaseModel):
    items: list[ChangeEventRead]
    # Pass as ``before`` to read older rows; None when this page reached the start.
    next_before: datetime | None


class NarrativeRead(BaseModel):
    text: str
    ai: Literal[True] = True
    provider: str | None
    model: str | None


class SummaryRead(BaseModel):
    since: datetime | None
    until: datetime
    since_label: str
    counts: dict[str, int]
    count_lines: list[str]
    highlights: list[ChangeEventRead]
    total_events: int
    markdown: str
    # Keval (US-55): the optional AI paragraph; labelled AI, never part of the counts.
    narrative: NarrativeRead | None = None


class SeenRead(BaseModel):
    seen_at: datetime
    previous: datetime | None


class PointRead(BaseModel):
    id: uuid.UUID | None
    label: str
    kind: Literal["baseline_revision", "baseline", "now"]
    baseline_revision: int
    graph_revision: int
    at: datetime | None
    baseline_id: uuid.UUID | None
    nodes: int
    edges: int


class HistoricMap(BaseModel):
    """The map at one point of the slider. Read-only: no positions are saved from it."""

    project_id: uuid.UUID
    snapshot_id: uuid.UUID
    label: str
    read_only: Literal[True] = True
    baseline_revision: int
    graph_revision: int
    captured_at: datetime
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class GhostEdgeRead(BaseModel):
    source: uuid.UUID
    target: uuid.UUID
    kind: EdgeKind
    labels: list[str]
    reason: str


class PreviewRead(BaseModel):
    change_request_id: uuid.UUID
    number: int
    kind: str
    requirement_id: uuid.UUID
    report_id: uuid.UUID | None
    checks_pending: bool
    stale: list[str]
    fading_edge_ids: list[uuid.UUID]
    glowing_edges: list[GhostEdgeRead]
    affected_node_ids: list[uuid.UUID]
    removed_node_ids: list[uuid.UUID]
    sentences: list[str]


def _event(e: changelog.Event) -> ChangeEventRead:
    return ChangeEventRead(
        id=e.id,
        at=e.at,
        revision=e.revision,
        kind=cast(EventKind, e.kind),
        sentence=e.sentence,
        actor_id=e.actor_id,
        actor_name=e.actor_name,
        node_ids=[uuid.UUID(n) for n in e.node_ids],
        edge_ids=[uuid.UUID(i) for i in e.edge_ids],
        backfilled=e.backfilled,
    )


@dataclass(frozen=True)
class Start:
    since: datetime | None
    label: str
    after_revision: int | None = None  # a labelled baseline: the map revision it froze


def window(
    db: Session,
    ctx: AccessContext,
    project_id: uuid.UUID,
    *,
    since: datetime | None,
    since_baseline_id: uuid.UUID | None,
    since_last_visit: bool,
) -> Start:
    """Where a summary starts, and how to name that start. At most one choice."""
    if (
        sum(x is not None and x is not False for x in (since, since_baseline_id, since_last_visit))
        > 1
    ):
        raise BadRequestError(
            "Choose one of since, since_baseline_id and since_last_visit", code="one_start"
        )
    if since_baseline_id is not None:
        baseline = db.get(Baseline, since_baseline_id)
        if baseline is None or baseline.project_id != project_id:
            raise NotFoundError("Baseline not found")
        frozen = db.scalar(
            select(GraphState.graph_revision).where(GraphState.baseline_id == baseline.id)
        )
        return Start(baseline.created_at, baseline.label, frozen)
    if since_last_visit:
        visit = changelog.last_visit(db, ctx.user.id, project_id)
        return Start(visit, "your last visit" if visit else "the beginning")
    if since is not None:
        return Start(since, since.strftime("%d %b %Y %H:%M"))
    return Start(None, "the beginning")


def summary_read(result: changelog.Summary) -> SummaryRead:
    return SummaryRead(
        since=result.since,
        until=result.until,
        since_label=result.since_label,
        counts=result.counts,
        count_lines=changelog.count_lines(result.counts),
        highlights=[_event(e) for e in result.highlights],
        total_events=result.total_events,
        markdown=result.markdown,
    )


@router.get(
    "/projects/{project_id}/changes",
    response_model=ChangeLogPage,
    summary="The written change log beside the map, newest first",
    responses=_ERRORS,
)
def list_changes(
    project_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
    since: datetime | None = None,
    until: datetime | None = None,
    before: Annotated[datetime | None, Query(description="Older than this (paging)")] = None,
    actor: uuid.UUID | None = None,
    kind: Annotated[list[EventKind] | None, Query()] = None,
    requirement: uuid.UUID | None = None,
    until_revision: Annotated[int | None, Query(ge=0)] = None,
    limit: Annotated[int, Query(ge=1, le=changelog.MAX_PAGE)] = 50,
) -> ChangeLogPage:
    rows = changelog.events(
        db,
        project_id,
        since=since,
        until=until,
        before=before,
        actor_id=actor,
        kinds=kind or (),
        requirement_id=requirement,
        until_revision=until_revision,
        limit=limit,
    )
    return ChangeLogPage(
        items=[_event(e) for e in rows],
        next_before=rows[-1].at if len(rows) == limit else None,
    )


@router.get(
    "/projects/{project_id}/changes/summary",
    response_model=SummaryRead,
    summary="What changed since a date, a baseline or my last visit",
    responses=_ERRORS,
)
def get_summary(
    project_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
    since: datetime | None = None,
    since_baseline_id: uuid.UUID | None = None,
    since_last_visit: bool = False,
    until: datetime | None = None,
) -> SummaryRead:
    start = window(
        db,
        ctx,
        project_id,
        since=since,
        since_baseline_id=since_baseline_id,
        since_last_visit=since_last_visit,
    )
    return summary_read(
        changelog.summary(
            db,
            project_id,
            since=start.since,
            since_label=start.label,
            until=until,
            after_revision=start.after_revision,
        )
    )


@router.put(
    "/projects/{project_id}/changes/seen",
    response_model=SeenRead,
    summary="Mark the change log read up to now (for 'since my last visit')",
    responses=_ERRORS,
)
def mark_seen(
    project_id: uuid.UUID, ctx: Annotated[AccessContext, requires("view")], db: DbSession
) -> SeenRead:
    previous = changelog.last_visit(db, ctx.user.id, project_id)
    return SeenRead(seen_at=changelog.mark_seen(db, ctx.user.id, project_id), previous=previous)


@router.get(
    "/projects/{project_id}/graph/revisions",
    response_model=list[PointRead],
    summary="The time slider: baseline revisions and labelled baselines, oldest first",
    responses=_ERRORS,
)
def list_revisions(
    project_id: uuid.UUID, ctx: Annotated[AccessContext, requires("view")], db: DbSession
) -> list[PointRead]:
    project = db.get(Project, project_id)
    if project is None:  # defensive
        raise NotFoundError("Project not found")
    return [PointRead.model_validate(vars(p)) for p in revisions.points(db, project)]


@router.get(
    "/projects/{project_id}/graph/revisions/{graph_snapshot_id}",
    response_model=HistoricMap,
    summary="The map as it was at one point of the time slider (read-only)",
    responses=_ERRORS,
)
def get_revision(
    project_id: uuid.UUID,
    graph_snapshot_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
) -> HistoricMap:
    row = db.get(GraphState, graph_snapshot_id)
    if row is None or row.project_id != project_id:  # the scope check already refuses this
        raise NotFoundError("Map snapshot not found")
    nodes, edges = revisions.state(row)
    label = f"Baseline revision {row.baseline_revision}"
    if row.baseline_id is not None:
        baseline = db.get(Baseline, row.baseline_id)
        label = baseline.label if baseline else "Baseline"
    return HistoricMap(
        project_id=project_id,
        snapshot_id=row.id,
        label=label,
        baseline_revision=row.baseline_revision,
        graph_revision=row.graph_revision,
        captured_at=row.captured_at,
        nodes=nodes,
        edges=edges,
    )


@router.get(
    "/change-requests/{change_request_id}/graph-preview",
    response_model=PreviewRead,
    summary="What merging this change request would do to the map (the Preview layer)",
    responses=_ERRORS,
)
def get_preview(
    change_request_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
) -> PreviewRead:
    row = db.get(ChangeRequest, change_request_id)
    if row is None:  # defensive
        raise NotFoundError("Change request not found")
    result = preview.for_change_request(db, row)
    return PreviewRead(
        change_request_id=result.change_request_id,
        number=result.number,
        kind=result.kind,
        requirement_id=result.requirement_id,
        report_id=result.report_id,
        checks_pending=result.checks_pending,
        stale=result.stale,
        fading_edge_ids=result.fading_edge_ids,
        glowing_edges=[GhostEdgeRead.model_validate(vars(g)) for g in result.glowing_edges],
        affected_node_ids=result.affected_node_ids,
        removed_node_ids=result.removed_node_ids,
        sentences=result.sentences,
    )


def _snapshot_scope(db: Session, graph_snapshot_id: uuid.UUID) -> Scope | None:
    row = db.get(GraphState, graph_snapshot_id)
    project = db.get(Project, row.project_id) if row else None
    return None if project is None else Scope(project.workspace_id, project.id)


register_scope_resolver("graph_snapshot_id", _snapshot_scope)
