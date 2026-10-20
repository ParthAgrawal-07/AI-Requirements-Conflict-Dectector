"""Document routes (Role 5; Parth — US-01 upload, US-03 status).

Contract: docs/engineering/api-reference.md. ``POST /projects/{p}/documents`` responds 202 with a
superset of the documented ``{document_id, status, filename}``.

Access (permission names, never role names — ADR-20):

* upload **as proposals** needs ``doc.upload``; upload **as baseline** needs ``baseline.manage``
  (the requirements become Approved, FR-01);
* reading needs ``view``.

Uploading is allowed while the project is in Setup: the initial SRS is uploaded then. A document
or project in another workspace is a 404, not a 403, so its existence isn't revealed.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile

from app.api.deps import DbSession, requires, requires_any
from app.core.config import get_settings
from app.core.errors import ForbiddenError, NotFoundError
from app.models import DocumentStatus, ImportMode
from app.schemas.common import ErrorResponse, Page
from app.schemas.documents import DocumentRead, RequirementRead
from app.services import documents as document_service
from app.services import projects as project_service
from app.services.access import AccessContext
from app.services.storage import LocalFileStorage, get_storage

router = APIRouter(tags=["documents"])

_UPLOAD_ERRORS: dict[int | str, dict[str, object]] = {
    400: {
        "model": ErrorResponse,
        "description": "Unsupported, empty, corrupted or mismatched file "
        "(`unsupported_file_type`, `empty_file`, `corrupted_file`, "
        "`file_content_mismatch`, `unsafe_file`)",
    },
    403: {"model": ErrorResponse, "description": "Missing the permission for this import mode"},
    404: {"model": ErrorResponse, "description": "Not a member, or no such project"},
    413: {"model": ErrorResponse, "description": "File exceeds the configured size limit"},
    503: {"model": ErrorResponse, "description": "Processing queue unavailable; retry"},
}


@router.post(
    "/projects/{project_id}/documents",
    status_code=202,
    response_model=DocumentRead,
    summary="Upload an SRS document into a project and queue it for extraction",
    responses=_UPLOAD_ERRORS,
)
def upload_document(
    project_id: uuid.UUID,
    file: Annotated[UploadFile, File(description="A PDF (.pdf) or Word (.docx) document")],
    ctx: Annotated[AccessContext, requires_any("doc.upload", "baseline.manage")],
    db: DbSession,
    storage: Annotated[LocalFileStorage, Depends(get_storage)],
    response: Response,
    import_mode: Annotated[
        ImportMode,
        Form(description="`baseline`: requirements become Approved. `proposals`: Proposed."),
    ] = ImportMode.PROPOSALS,
    stakeholder_group: Annotated[
        str | None, Form(max_length=120, description="Optional group that owns this document")
    ] = None,
) -> DocumentRead:
    needed = "baseline.manage" if import_mode is ImportMode.BASELINE else "doc.upload"
    if not ctx.can(needed):
        raise ForbiddenError()

    project = project_service.get_project(db, project_id)
    if project is None:  # cannot happen after the access check; defensive
        raise NotFoundError("Project not found")

    group = (stakeholder_group or "").strip() or None
    document, duplicate_of = document_service.create_document_from_upload(
        db,
        user=ctx.user,
        project=project,
        filename=file.filename,
        source=file.file,
        storage=storage,
        max_upload_size_mb=get_settings().max_upload_size_mb,
        import_mode=import_mode,
        stakeholder_group=group,
    )
    response.headers["Location"] = f"/api/v1/documents/{document.id}"
    return DocumentRead.from_model(document, requirement_count=0, duplicate_of=duplicate_of)


@router.get(
    "/projects/{project_id}/documents",
    response_model=Page[DocumentRead],
    summary="List the project's documents",
    responses={404: {"model": ErrorResponse}},
)
def list_documents(
    project_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
    status: Annotated[DocumentStatus | None, Query(description="Filter by status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[DocumentRead]:
    rows, total = document_service.list_documents(
        db, project_id, status=status, limit=limit, offset=offset
    )
    return Page[DocumentRead](
        items=[DocumentRead.from_model(doc, requirement_count=count) for doc, count in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/documents/{document_id}",
    response_model=DocumentRead,
    summary="Get a document's processing status and progress",
    responses={404: {"model": ErrorResponse}},
)
def get_document(
    document_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
) -> DocumentRead:
    # A document always belongs to a project, so the scope always carries one.
    found = (
        None
        if ctx.project_id is None
        else document_service.get_document(db, ctx.project_id, document_id)
    )
    if found is None:
        raise NotFoundError("Document not found")
    document, requirement_count = found
    return DocumentRead.from_model(document, requirement_count=requirement_count)


@router.get(
    "/projects/{project_id}/requirements",
    response_model=Page[RequirementRead],
    summary="List the requirements extracted from a project's documents",
    responses={404: {"model": ErrorResponse}},
)
def list_project_requirements(
    project_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
    q: Annotated[
        str | None,
        Query(max_length=200, description="Case-insensitive search in ID and text"),
    ] = None,
    document_id: Annotated[uuid.UUID | None, Query(description="Filter by document")] = None,
    state: Annotated[str | None, Query(description="Filter by state")] = None,
    origin: Annotated[str | None, Query(description="Filter by origin")] = None,
    owner: Annotated[uuid.UUID | None, Query(description="Filter by owner user id")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[RequirementRead]:
    result = document_service.list_requirements(
        db,
        project_id,
        query=q,
        document_id=document_id,
        state=state,
        origin=origin,
        owner=owner,
        limit=limit,
        offset=offset,
    )
    if result is None:
        raise NotFoundError("Project not found")
    requirements, total = result
    return Page[RequirementRead](
        items=[RequirementRead.from_model(item) for item in requirements],
        total=total,
        limit=limit,
        offset=offset,
    )
