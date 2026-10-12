"""Document routes (Role 5 — US-01 upload, US-03 status, US-04 requirement list).

Contract: docs/engineering/api-reference.md. ``POST /documents`` responds 202 with a superset of
the documented ``{document_id, status, filename}``.

Access: uploading needs analyst/admin; reading is open to analyst, admin and compliance
reviewer. ``read_only`` (dashboard/reports only) and ``service`` accounts get 403. Every read is
scoped to the caller's workspace, and another workspace's document is a 404, not a 403, so its
existence isn't revealed.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from sqlalchemy.orm import Session

from app.core.auth import require_roles
from app.core.config import get_settings
from app.core.database import get_db
from app.core.errors import NotFoundError
from app.models import DocumentStatus, Role, User
from app.schemas.common import ErrorResponse, Page
from app.schemas.documents import DocumentRead, RequirementRead
from app.services import documents as document_service
from app.services.storage import LocalFileStorage, get_storage

router = APIRouter()

DbSession = Annotated[Session, Depends(get_db)]
Uploader = Annotated[User, Depends(require_roles(Role.ANALYST, Role.ADMIN))]
Reader = Annotated[User, Depends(require_roles(Role.ANALYST, Role.ADMIN, Role.COMPLIANCE_REVIEWER))]

_UPLOAD_ERRORS: dict[int | str, dict[str, object]] = {
    400: {
        "model": ErrorResponse,
        "description": "Unsupported, empty, corrupted or mismatched file "
        "(`unsupported_file_type`, `empty_file`, `corrupted_file`, "
        "`file_content_mismatch`, `unsafe_file`)",
    },
    403: {"model": ErrorResponse, "description": "Role may not upload"},
    413: {"model": ErrorResponse, "description": "File exceeds the configured size limit"},
    503: {"model": ErrorResponse, "description": "Processing queue unavailable; retry"},
}


@router.post(
    "",
    status_code=202,
    response_model=DocumentRead,
    summary="Upload an SRS document and queue it for extraction",
    responses=_UPLOAD_ERRORS,
)
def upload_document(
    file: Annotated[UploadFile, File(description="A PDF (.pdf) or Word (.docx) document")],
    user: Uploader,
    db: DbSession,
    storage: Annotated[LocalFileStorage, Depends(get_storage)],
    response: Response,
) -> DocumentRead:
    document, duplicate_of = document_service.create_document_from_upload(
        db,
        user=user,
        filename=file.filename,
        source=file.file,
        storage=storage,
        max_upload_size_mb=get_settings().max_upload_size_mb,
    )
    response.headers["Location"] = f"/api/v1/documents/{document.id}"
    return DocumentRead.from_model(document, requirement_count=0, duplicate_of=duplicate_of)


@router.get("", response_model=Page[DocumentRead], summary="List the workspace's documents")
def list_documents(
    user: Reader,
    db: DbSession,
    status: Annotated[DocumentStatus | None, Query(description="Filter by status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[DocumentRead]:
    rows, total = document_service.list_documents(
        db, user.workspace_id, status=status, limit=limit, offset=offset
    )
    return Page[DocumentRead](
        items=[DocumentRead.from_model(doc, requirement_count=count) for doc, count in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{document_id}",
    response_model=DocumentRead,
    summary="Get a document's processing status and progress",
    responses={404: {"model": ErrorResponse}},
)
def get_document(document_id: uuid.UUID, user: Reader, db: DbSession) -> DocumentRead:
    found = document_service.get_document(db, user.workspace_id, document_id)
    if found is None:
        raise NotFoundError("Document not found")
    document, requirement_count = found
    return DocumentRead.from_model(document, requirement_count=requirement_count)


@router.get(
    "/{document_id}/requirements",
    response_model=Page[RequirementRead],
    summary="List the requirements extracted from a document",
    responses={404: {"model": ErrorResponse}},
)
def list_document_requirements(
    document_id: uuid.UUID,
    user: Reader,
    db: DbSession,
    q: Annotated[
        str | None,
        Query(max_length=200, description="Case-insensitive search in ID and text"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[RequirementRead]:
    result = document_service.list_requirements(
        db, user.workspace_id, document_id, query=q, limit=limit, offset=offset
    )
    if result is None:
        raise NotFoundError("Document not found")
    requirements, total = result
    return Page[RequirementRead](
        items=[RequirementRead.from_model(item) for item in requirements],
        total=total,
        limit=limit,
        offset=offset,
    )
