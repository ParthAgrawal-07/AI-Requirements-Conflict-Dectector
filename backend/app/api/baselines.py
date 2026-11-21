"""Baselines API (Parth — US-40, FR-73, DR-08).

=================================================  ============================================
``POST /projects/{p}/baselines``                   freeze a labelled snapshot (``baseline.manage``)
``GET /projects/{p}/baselines``                    the project's snapshots, newest first (``view``)
``GET /baselines/{b}``                             one snapshot with its requirements (``view``)
``GET /baselines/{b}/compare/{other_baseline_id}``  added, changed (both texts) and removed
=================================================  ============================================

Both baselines of a comparison must belong to the same project: the access layer resolves both
ids and answers 404 otherwise.
"""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import DbSession, requires
from app.core.errors import NotFoundError
from app.models import Project, User
from app.models.baseline import Baseline
from app.schemas.common import ErrorResponse
from app.services import baselines
from app.services.access import AccessContext, Scope, register_scope_resolver

router = APIRouter(tags=["baselines"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
}


class BaselineCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=80)
    note: str | None = Field(default=None, max_length=2000)


class BaselineRead(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    label: str
    note: str | None
    baseline_revision: int
    requirement_count: int
    created_by: uuid.UUID | None
    created_by_name: str | None
    created_at: datetime


class ItemRead(BaseModel):
    requirement_id: uuid.UUID
    label: str | None
    version: int
    state: str
    body: str


class BaselineDetail(BaselineRead):
    items: list[ItemRead]


class EntryRead(BaseModel):
    requirement_id: uuid.UUID
    label: str | None
    version: int | None
    state: str | None
    body: str | None


class ChangedRead(BaseModel):
    requirement_id: uuid.UUID
    label: str | None
    from_version: int
    to_version: int
    before: str
    after: str


class ComparisonRead(BaseModel):
    base: BaselineRead
    target: BaselineRead
    added: list[EntryRead]
    changed: list[ChangedRead]
    removed: list[EntryRead]
    unchanged: int


def _read(db: Session, row: Baseline) -> BaselineRead:
    author = db.get(User, row.created_by) if row.created_by else None
    return BaselineRead(
        id=row.id,
        project_id=row.project_id,
        label=row.label,
        note=row.note,
        baseline_revision=row.baseline_revision,
        requirement_count=row.requirement_count,
        created_by=row.created_by,
        created_by_name=author.full_name if author else None,
        created_at=row.created_at,
    )


def _baseline(db: Session, baseline_id: uuid.UUID) -> Baseline:
    row = db.get(Baseline, baseline_id)
    if row is None:  # cannot happen after require_permission; defensive
        raise NotFoundError("Baseline not found")
    return row


@router.post(
    "/projects/{project_id}/baselines",
    response_model=BaselineRead,
    status_code=status.HTTP_201_CREATED,
    summary="Freeze a labelled snapshot of the agreed baseline",
    responses=_ERRORS,
)
def create_baseline(
    project_id: uuid.UUID,
    body: BaselineCreate,
    ctx: Annotated[AccessContext, requires("baseline.manage")],
    db: DbSession,
) -> BaselineRead:
    project = db.get(Project, project_id)
    if project is None:  # defensive
        raise NotFoundError("Project not found")
    return _read(db, baselines.snapshot(db, project, ctx.user, label=body.label, note=body.note))


@router.get(
    "/projects/{project_id}/baselines",
    response_model=list[BaselineRead],
    summary="The project's baselines",
    responses=_ERRORS,
)
def list_baselines(
    project_id: uuid.UUID, ctx: Annotated[AccessContext, requires("view")], db: DbSession
) -> list[BaselineRead]:
    return [_read(db, row) for row in baselines.list_baselines(db, project_id)]


@router.get(
    "/baselines/{baseline_id}",
    response_model=BaselineDetail,
    summary="One baseline and the requirements it froze",
    responses=_ERRORS,
)
def get_baseline(
    baseline_id: uuid.UUID, ctx: Annotated[AccessContext, requires("view")], db: DbSession
) -> BaselineDetail:
    row = _baseline(db, baseline_id)
    return BaselineDetail(
        **_read(db, row).model_dump(),
        items=[
            ItemRead(
                requirement_id=i.requirement_id,
                label=i.label,
                version=i.version_no,
                state=i.state,
                body=i.body,
            )  # fmt: skip
            for i in baselines.items_of(db, row.id)
        ],
    )


@router.get(
    "/baselines/{baseline_id}/compare/{other_baseline_id}",
    response_model=ComparisonRead,
    summary="What changed from one baseline to another",
    responses=_ERRORS,
)
def compare_baselines(
    baseline_id: uuid.UUID,
    other_baseline_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
) -> ComparisonRead:
    result = baselines.compare(db, _baseline(db, baseline_id), _baseline(db, other_baseline_id))
    return ComparisonRead(
        base=_read(db, result.base),
        target=_read(db, result.target),
        added=[EntryRead.model_validate(vars(e)) for e in result.added],
        changed=[ChangedRead.model_validate(vars(c)) for c in result.changed],
        removed=[EntryRead.model_validate(vars(e)) for e in result.removed],
        unchanged=result.unchanged,
    )


def _baseline_scope(db: Session, baseline_id: uuid.UUID) -> Scope | None:
    row = db.get(Baseline, baseline_id)
    project = db.get(Project, row.project_id) if row else None
    return None if project is None else Scope(project.workspace_id, project.id)


register_scope_resolver("baseline_id", _baseline_scope)
register_scope_resolver("other_baseline_id", _baseline_scope)
