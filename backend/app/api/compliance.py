"""Compliance routes (Parth — US-18, FR-21, FR-36, NFR-13, DR-05, DR-12).

=================================================  ==========================  =======================
Route                                              Permission                  What
=================================================  ==========================  =======================
``PUT /requirements/{r}/protection``               ``req.protect``             protect / unprotect
                                                                               (a reason to remove)
``POST /projects/{p}/protection``                  ``req.protect``             protect many at once,
                                                                               by id or printed ID
                                                                               (after an import)
``GET /projects/{p}/compliance/queue``             ``protected.signoff``,      what waits for a
                                                   ``req.protect`` or          compliance reviewer
                                                   ``audit.export``
``GET /projects/{p}/compliance/audit``             ``audit.export``            the immutable trail
                                                                               of protected
                                                                               requirements, JSON or
                                                                               CSV (the export is
                                                                               audited)
=================================================  ==========================  =======================
"""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api.deps import DbSession, requires, requires_any
from app.core.errors import NotFoundError
from app.models import Project, Requirement, User
from app.schemas.common import ErrorResponse
from app.services import compliance
from app.services.access import AccessContext

router = APIRouter(tags=["compliance"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
}


class ProtectionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protected: bool
    reason: str | None = Field(default=None, max_length=compliance.MAX_REASON)


class ProtectionRead(BaseModel):
    requirement_id: uuid.UUID
    label: str | None
    is_protected: bool
    protected_by: uuid.UUID | None
    protected_at: datetime | None
    protection_reason: str | None


class BulkProtection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement_ids: list[uuid.UUID] = Field(default_factory=list, max_length=compliance.MAX_BULK)
    labels: list[str] = Field(
        default_factory=list,
        max_length=compliance.MAX_BULK,
        description='Printed IDs as in the document, e.g. ["REQ-007", "REQ-009"]',
    )
    reason: str | None = Field(default=None, max_length=compliance.MAX_REASON)


class BulkProtectionRead(BaseModel):
    protected: list[ProtectionRead]
    not_found: list[str]  # printed IDs that matched no requirement of the project


class QueueItemRead(BaseModel):
    kind: Literal["finding", "change_request", "signoff"]
    id: uuid.UUID
    requirement_ids: list[uuid.UUID]
    labels: list[str]
    title: str
    status: Literal["awaiting_decision", "awaiting_approval", "approved", "awaiting_signoff"]
    since: datetime
    done_by: uuid.UUID | None
    done_by_name: str | None


class ProtectedRead(BaseModel):
    requirement_id: uuid.UUID
    label: str
    state: str
    current_version: int
    signed_off_version: int | None
    signed_off_by: uuid.UUID | None
    signed_off_by_name: str | None
    signed_off_at: datetime | None
    protected_by: uuid.UUID | None
    protected_by_name: str | None
    protected_at: datetime | None
    protection_reason: str | None


class QueueRead(BaseModel):
    pending: list[QueueItemRead]
    protected: list[ProtectedRead]


class TrailRowRead(BaseModel):
    at: datetime
    actor_id: uuid.UUID
    actor_name: str | None
    action: str
    requirement_id: uuid.UUID | None
    requirement_label: str | None
    finding_id: uuid.UUID | None
    details: dict[str, Any]


def _protection(requirement: Requirement) -> ProtectionRead:
    return ProtectionRead(
        requirement_id=requirement.id,
        label=requirement.source_req_id,
        is_protected=requirement.is_protected,
        protected_by=requirement.protected_by,
        protected_at=requirement.protected_at,
        protection_reason=requirement.protection_reason,
    )


def _project(db: DbSession, project_id: uuid.UUID) -> Project:
    project = db.get(Project, project_id)
    if project is None:  # defensive
        raise NotFoundError("Project not found")
    return project


@router.put(
    "/requirements/{requirement_id}/protection",
    response_model=ProtectionRead,
    summary="Mark a requirement protected (compliance-critical), or remove it with a reason",
    responses=_ERRORS,
)
def put_protection(
    requirement_id: uuid.UUID,
    body: ProtectionUpdate,
    ctx: Annotated[AccessContext, requires("req.protect")],
    db: DbSession,
) -> ProtectionRead:
    requirement = db.get(Requirement, requirement_id)
    if requirement is None:  # defensive
        raise NotFoundError("Requirement not found")
    compliance.set_protection(db, ctx, requirement, protected=body.protected, reason=body.reason)
    return _protection(requirement)


@router.post(
    "/projects/{project_id}/protection",
    response_model=BulkProtectionRead,
    summary="Protect many requirements at once, e.g. right after an import",
    responses=_ERRORS,
)
def post_protection(
    project_id: uuid.UUID,
    body: BulkProtection,
    ctx: Annotated[AccessContext, requires("req.protect")],
    db: DbSession,
) -> BulkProtectionRead:
    rows, missing = compliance.protect_many(
        db,
        ctx,
        _project(db, project_id),
        requirement_ids=body.requirement_ids,
        labels=body.labels,
        reason=body.reason,
    )
    return BulkProtectionRead(protected=[_protection(r) for r in rows], not_found=missing)


@router.get(
    "/projects/{project_id}/compliance/queue",
    response_model=QueueRead,
    summary="What waits for a compliance reviewer, and every protected requirement",
    responses=_ERRORS,
)
def get_queue(
    project_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires_any("protected.signoff", "req.protect", "audit.export")],
    db: DbSession,
) -> QueueRead:
    result = compliance.queue(db, _project(db, project_id))
    people = {i.done_by for i in result.pending} | {
        p[k] for p in result.protected for k in ("signed_off_by", "protected_by")
    }
    wanted = [u for u in people if u is not None]
    names = (
        {u.id: u.full_name for u in db.scalars(select(User).where(User.id.in_(wanted)))}
        if wanted
        else {}
    )
    return QueueRead(
        pending=[
            QueueItemRead(
                **vars(item), done_by_name=names.get(item.done_by) if item.done_by else None
            )
            for item in result.pending
        ],
        protected=[
            ProtectedRead(
                **p,
                signed_off_by_name=names.get(p["signed_off_by"]) if p["signed_off_by"] else None,
                protected_by_name=names.get(p["protected_by"]) if p["protected_by"] else None,
            )
            for p in result.protected
        ],
    )


@router.get(
    "/projects/{project_id}/compliance/audit",
    response_model=list[TrailRowRead],
    summary="The audit trail of protected requirements (JSON, or CSV with format=csv)",
    responses={**_ERRORS, 200: {"content": {"text/csv": {}}}},
)
def get_audit(
    project_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("audit.export")],
    db: DbSession,
    format: Annotated[Literal["json", "csv"], Query()] = "json",
    requirement: uuid.UUID | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[TrailRowRead] | Response:
    project = _project(db, project_id)
    rows = compliance.trail(db, project, requirement_id=requirement, since=since, until=until)
    compliance.record_export(db, ctx, project, fmt=format, rows=len(rows),
                             requirement=requirement, since=since, until=until)  # fmt: skip
    if format == "csv":
        return Response(
            content=compliance.as_csv(rows),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="audit-{project_id}.csv"'},
        )
    return [TrailRowRead.model_validate(vars(r)) for r in rows]
