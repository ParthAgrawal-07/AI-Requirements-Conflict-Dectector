"""Project context routes (Bansil — US-60, FR-103 to FR-105; design update §12.5).

Access (permission names, never role names — ADR-20):

* reading the context and its versions needs ``view`` — every member reads the brief
  (onboarding checklist, NFR-31);
* writing, confirming and re-drafting need ``project.context``.

``POST /projects/{p}/rerun-open-findings`` (design update §12.5) arrives with the analysis
orchestrator in Sprint 2; until then ``PUT`` reports how many open findings a re-run would cover.
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.deps import DbSession, requires
from app.context import service as context_service
from app.context.drafter import get_brief_drafter
from app.core.errors import ConflictError, NotFoundError
from app.models import Document, DocumentSection, DocumentStatus, Project
from app.schemas.common import ErrorResponse, Page
from app.schemas.context import (
    ContextDraftRequest,
    ContextDraftResult,
    ContextSaveResult,
    ContextUpdate,
    ContextVersionRead,
    ProjectContextRead,
)
from app.services import projects as project_service
from app.services.access import AccessContext

router = APIRouter(tags=["project context"])

_NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Not a member, or no such project"}
}
_WRITE_ERRORS: dict[int | str, dict[str, Any]] = {
    **_NOT_FOUND,
    400: {
        "model": ErrorResponse,
        "description": "`context_field_empty`, `context_empty`, `context_required_field_empty` "
        "or `context_reason_required`",
    },
    403: {"model": ErrorResponse, "description": "Missing `project.context`"},
    409: {"model": ErrorResponse, "description": "The project is archived"},
}


def _project(db: DbSession, project_id: uuid.UUID) -> Project:
    project = project_service.get_project(db, project_id)
    if project is None:  # cannot happen after require_permission; defensive
        raise NotFoundError("Project not found")
    return project


def _read(db: DbSession, project: Project) -> ProjectContextRead:
    return ProjectContextRead.build(
        project_id=project.id,
        project_status=project.status,
        context_version=project.context_version,
        latest=context_service.latest_context(db, project.id),
    )


@router.get(
    "/projects/{project_id}/context",
    response_model=ProjectContextRead,
    summary="The project brief, its field states and what Setup still needs",
    responses=_NOT_FOUND,
)
def get_context(
    project_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
) -> ProjectContextRead:
    return _read(db, _project(db, project_id))


@router.put(
    "/projects/{project_id}/context",
    response_model=ContextSaveResult,
    summary="Edit or confirm brief fields (activates the project when all required are confirmed)",
    responses=_WRITE_ERRORS,
)
def put_context(
    project_id: uuid.UUID,
    body: ContextUpdate,
    ctx: Annotated[AccessContext, requires("project.context")],
    db: DbSession,
) -> ContextSaveResult:
    result = context_service.save_context(
        db,
        project_id=project_id,
        actor=ctx.user,
        changes=body.fields,
        confirm=body.confirm,
        reason=body.reason,
    )
    project = _project(db, project_id)
    db.refresh(project)
    return ContextSaveResult(
        context=_read(db, project),
        created=result.created,
        activated=result.activated,
        open_findings_to_rerun=result.open_findings,
    )


@router.get(
    "/projects/{project_id}/context/versions",
    response_model=Page[ContextVersionRead],
    summary="Version history of the project brief, newest first",
    responses=_NOT_FOUND,
)
def list_context_versions(
    project_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[ContextVersionRead]:
    rows, total = context_service.list_versions(db, project_id, limit=limit, offset=offset)
    return Page[ContextVersionRead](
        items=[ContextVersionRead.from_model(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/projects/{project_id}/context/draft",
    response_model=ContextDraftResult,
    summary="Draft the brief fields nobody has confirmed from one of the project's documents",
    responses={
        **_NOT_FOUND,
        403: {"model": ErrorResponse, "description": "Missing `project.context`"},
        409: {"model": ErrorResponse, "description": "Document not processed yet, or archived"},
    },
)
def draft_context(
    project_id: uuid.UUID,
    body: ContextDraftRequest,
    ctx: Annotated[AccessContext, requires("project.context")],
    db: DbSession,
) -> ContextDraftResult:
    document = db.scalar(
        select(Document).where(Document.id == body.document_id, Document.project_id == project_id)
    )
    if document is None:
        raise NotFoundError("Document not found")
    if document.status is not DocumentStatus.DONE:
        raise ConflictError("The document has not finished processing yet")
    sections = db.scalars(
        select(DocumentSection)
        .where(DocumentSection.document_id == document.id)
        .order_by(DocumentSection.order_index)
    ).all()
    context = context_service.draft_from_sections(
        db,
        project_id=project_id,
        sections=sections,
        drafter=get_brief_drafter(),
        document=document,
        actor=ctx.user,
    )
    return ContextDraftResult(
        context=_read(db, _project(db, project_id)), drafted=context is not None
    )
