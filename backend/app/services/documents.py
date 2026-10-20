"""Document service (Role 5 — US-01 upload, US-03 status).

Routes stay thin; this module owns the transaction and the ordering rules. Documents belong to a
project (ADR-14); every query filters by ``project_id`` as well as being reached through
``require_permission`` (FR-38): a document in another project or workspace is indistinguishable
from one that doesn't exist. Requirement listing (US-04) lives in ``services/requirements.py``.

Upload ordering, chosen so a failure at any step leaves nothing behind:

1. stage the stream to a temp file (size-limited, hashed)      → discard on failure
2. validate the content                                         → discard on failure
3. insert the ``documents`` row (flush, no commit)
4. move the temp file to its final key
5. commit                                                       → delete file on failure
6. enqueue the processing task *after* the commit, so the worker can never look for a row
   that isn't visible yet                                       → delete row + file on failure
"""

import logging
import uuid
from typing import Any, BinaryIO

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.errors import PayloadTooLargeError, ServiceUnavailableError
from app.models import (
    AuditAction,
    AuditLog,
    Document,
    DocumentStatus,
    ImportMode,
    Project,
    Requirement,
    User,
)
from app.services.storage import LocalFileStorage, StagedFile, UploadTooLargeError
from app.services.upload_validation import sanitize_filename, validate_upload

logger = logging.getLogger(__name__)


def too_large_message(max_upload_size_mb: int) -> str:
    return f"File is too large. The maximum upload size is {max_upload_size_mb} MB."


def storage_key(document: Document, extension: str) -> str:
    return f"{document.workspace_id}/{document.id}{extension}"


def dispatch_processing(document_id: uuid.UUID) -> str:
    """Queue the extraction job and return the Celery task id.

    Imported lazily so importing this module (and the API routes) never requires a broker.
    Tests replace this function; nothing here should be called at import time.
    """
    from app.core.tasks import process_document_task

    return str(process_document_task.delay(str(document_id)).id)


def create_document_from_upload(
    db: Session,
    *,
    user: User,
    project: Project,
    filename: str | None,
    source: BinaryIO,
    storage: LocalFileStorage,
    max_upload_size_mb: int,
    import_mode: ImportMode = ImportMode.PROPOSALS,
    stakeholder_group: str | None = None,
) -> tuple[Document, uuid.UUID | None]:
    """Accept an upload into ``project``. Returns the document and an earlier identical one, if any.

    The caller has already checked the permission for ``import_mode`` (``baseline.manage`` for a
    baseline import, ``doc.upload`` for proposals). Extraction is allowed while the project is in
    Setup — the initial SRS is uploaded then; only *analysis* is gated (ContextGate).

    Raises ``BadRequestError`` (400), ``PayloadTooLargeError`` (413) or
    ``ServiceUnavailableError`` (503); on any error nothing is stored.
    """
    safe_name = sanitize_filename(filename)

    staged = _stage(storage, source, max_upload_size_mb)
    try:
        detected_format = validate_upload(staged.path, safe_name)
    except BaseException:
        storage.discard(staged)
        raise

    duplicate_of = find_duplicate(db, project.workspace_id, project.id, staged.sha256)
    document = Document(
        workspace_id=project.workspace_id,
        project_id=project.id,
        import_mode=import_mode,
        stakeholder_group=stakeholder_group,
        uploaded_by=user.id,
        filename=safe_name,
        format=detected_format,
        size_bytes=staged.size_bytes,
        sha256=staged.sha256,
        storage_path="",  # needs the generated id; set right after the flush below
        status=DocumentStatus.QUEUED,
    )
    key: str | None = None
    try:
        db.add(document)
        db.flush()  # assigns document.id without ending the transaction
        key = storage_key(document, f".{detected_format.value}")
        document.storage_path = key
        storage.commit(staged, key)
        db.commit()
    except BaseException:
        db.rollback()
        storage.discard(staged)
        if key is not None:
            storage.delete(key)
        raise

    try:
        document.task_id = dispatch_processing(document.id)
        # Audited only once the upload is certain to stand; identifiers only (CR-04).
        db.add(
            AuditLog(
                workspace_id=document.workspace_id,
                actor_id=user.id,
                action=AuditAction.DOCUMENT_UPLOADED,
                details={
                    "document_id": str(document.id),
                    "project_id": str(project.id),
                    "import_mode": import_mode.value,
                },
            )
        )
        db.commit()
    except Exception as exc:
        # The queue (Redis) is unreachable. Uploading is all-or-nothing: remove what we just
        # committed so the client can simply retry, rather than leaving an orphan that
        # nothing will ever process.
        logger.exception("Could not queue document %s for processing", document.id)
        db.rollback()
        db.delete(document)
        db.commit()
        storage.delete(key)
        raise ServiceUnavailableError(
            "The processing queue is temporarily unavailable. Please try again in a moment.",
            code="queue_unavailable",
        ) from exc

    return document, duplicate_of


def _stage(storage: LocalFileStorage, source: BinaryIO, max_upload_size_mb: int) -> StagedFile:
    try:
        return storage.stage(source, max_bytes=max_upload_size_mb * 1024 * 1024)
    except UploadTooLargeError:
        raise PayloadTooLargeError(too_large_message(max_upload_size_mb)) from None


def find_duplicate(
    db: Session, workspace_id: uuid.UUID, project_id: uuid.UUID, sha256: str
) -> uuid.UUID | None:
    """The oldest earlier document in the project with identical content that did not fail.

    ``workspace_id`` is redundant for correctness (a project has one workspace) but lets
    PostgreSQL use ``ix_documents_workspace_id_sha256`` instead of scanning the project.
    """
    return db.scalar(
        select(Document.id)
        .where(
            Document.workspace_id == workspace_id,
            Document.project_id == project_id,
            Document.sha256 == sha256,
            Document.status != DocumentStatus.FAILED,
        )
        .order_by(Document.uploaded_at, Document.id)
        .limit(1)
    )


# ── reads ────────────────────────────────────────────────────────────────────
def _requirement_count() -> Select[Any]:
    return (
        select(func.count(Requirement.id))
        .where(Requirement.document_id == Document.id)
        .correlate(Document)
    )


def get_document(
    db: Session, project_id: uuid.UUID, document_id: uuid.UUID
) -> tuple[Document, int] | None:
    row = db.execute(
        select(Document, _requirement_count().scalar_subquery()).where(
            Document.id == document_id, Document.project_id == project_id
        )
    ).first()
    return None if row is None else (row[0], int(row[1]))


def list_documents(
    db: Session,
    project_id: uuid.UUID,
    *,
    status: DocumentStatus | None,
    limit: int,
    offset: int,
) -> tuple[list[tuple[Document, int]], int]:
    conditions = [Document.project_id == project_id]
    if status is not None:
        conditions.append(Document.status == status)

    total = db.scalar(select(func.count(Document.id)).where(*conditions)) or 0
    rows = db.execute(
        select(Document, _requirement_count().scalar_subquery())
        .where(*conditions)
        # id as a tiebreaker keeps pagination stable when timestamps collide
        .order_by(Document.uploaded_at.desc(), Document.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [(row[0], int(row[1])) for row in rows], total
