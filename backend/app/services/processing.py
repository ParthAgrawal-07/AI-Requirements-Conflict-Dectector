"""Document processing (Role 5 orchestration) — runs inside the Celery worker.

``process_document`` is the glue between the upload (US-01), Bansil's extraction pipeline
(``app.ingestion.ingest``, US-02) and the ``requirements`` table (US-04). It contains no parsing
logic: it claims the document, calls ``ingest`` on the stored file, and persists the result.

Properties the rest of the system relies on:

* **Idempotent.** Celery may deliver a task twice (``task_acks_late``). A document already
  ``done``/``failed`` is skipped; one left ``processing`` by a crashed worker is re-run from
  scratch, replacing any partial output — never duplicating requirements.
* **Never silent.** Every failure ends in ``status=failed`` with a human-readable
  ``error_message`` naming the stage (``[storage]``, ``[extraction]``, ``[persistence]``) —
  US-03 / US-02. Raw exception text is logged, not stored: it can contain file paths.
* **Requirement text is stored verbatim** (FR-04), except NUL bytes, which PostgreSQL text
  columns cannot hold and PDF extraction sometimes emits.

After the requirements, the document's sections are stored (``document_sections``) and, while the
project is still in Setup, the project brief is drafted from them (US-60, Bansil —
``app.context``). Drafting is best effort: if it fails the document is still ``done`` and the
Project Manager writes the brief by hand.
"""

import logging
import uuid
from collections.abc import Callable
from enum import StrEnum

from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.context import service as context_service
from app.context.drafter import get_brief_drafter
from app.ingestion import DocumentSection as ExtractedSection
from app.ingestion import Requirement as ExtractedRequirement
from app.ingestion import SegmentationResult, ingest_document
from app.models import (
    Document,
    DocumentSection,
    DocumentStatus,
    ImportMode,
    Project,
    ProjectStatus,
    Requirement,
    RequirementOrigin,
    RequirementState,
    RequirementVersion,
)
from app.services.storage import LocalFileStorage, get_storage

logger = logging.getLogger(__name__)

MAX_LOCATION_LENGTH = 64  # requirements.location is VARCHAR(64)

PROGRESS_STARTED = 10
PROGRESS_DONE = 100


class Stage(StrEnum):
    STORAGE = "storage"
    EXTRACTION = "extraction"
    PERSISTENCE = "persistence"


class ProcessingOutcome(StrEnum):
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


Extractor = Callable[[str], SegmentationResult | list[ExtractedRequirement]]


class _StageFailure(Exception):
    def __init__(self, stage: Stage, message: str) -> None:
        super().__init__(message)
        self.stage = stage
        self.message = message


def process_document(
    db: Session,
    document_id: uuid.UUID,
    *,
    storage: LocalFileStorage | None = None,
    extract: Extractor = ingest_document,
) -> ProcessingOutcome:
    storage = storage or get_storage()

    # FOR UPDATE serialises concurrent deliveries of the same task for the claim step only.
    document = db.scalar(select(Document).where(Document.id == document_id).with_for_update())
    if document is None:
        db.rollback()
        logger.warning("Processing skipped: document %s no longer exists", document_id)
        return ProcessingOutcome.SKIPPED
    if document.status in (DocumentStatus.DONE, DocumentStatus.FAILED):
        db.rollback()
        logger.info("Processing skipped: document %s is already %s", document_id, document.status)
        return ProcessingOutcome.SKIPPED

    document.status = DocumentStatus.PROCESSING
    document.progress_percent = PROGRESS_STARTED
    document.error_message = None
    db.commit()  # visible to status polling immediately (US-03), and releases the row lock

    try:
        result = _extract(document, storage, extract)
        _persist(db, document, result)
    except _StageFailure as failure:
        return _fail(db, document_id, failure.stage, failure.message)

    logger.info("Processed document %s: %d requirements", document_id, len(result.requirements))
    _draft_project_context(db, document_id, result.sections)
    return ProcessingOutcome.DONE


def _extract(
    document: Document,
    storage: LocalFileStorage,
    extract: Extractor,
) -> SegmentationResult:
    path = storage.resolve(document.storage_path)
    if not path.is_file():
        raise _StageFailure(
            Stage.STORAGE,
            "The uploaded file could not be found by the processing worker. If this keeps "
            "happening, the API and worker do not share the uploads volume.",
        )
    try:
        result = extract(str(path))
    except SoftTimeLimitExceeded:
        raise _StageFailure(
            Stage.EXTRACTION, "Extraction took too long and was stopped. Try a smaller document."
        ) from None
    except Exception:
        logger.exception("Extraction failed for document %s", document.id)
        raise _StageFailure(
            Stage.EXTRACTION,
            "The document could not be read. It may be corrupted, password-protected, or "
            "contain only scanned images.",
        ) from None
    if isinstance(result, list):  # a bare requirements list, e.g. from ``ingest``
        result = SegmentationResult(requirements=result)
    if not result.requirements:
        raise _StageFailure(
            Stage.EXTRACTION,
            "No requirement statements were found in this document. Scanned (image-only) and "
            "password-protected files are not supported.",
        )
    return result


def _persist(db: Session, document: Document, result: SegmentationResult) -> None:
    try:
        # A re-run replaces earlier partial output. Versions/embeddings go with it (ON DELETE CASCADE).
        db.execute(delete(Requirement).where(Requirement.document_id == document.id))
        db.execute(delete(DocumentSection).where(DocumentSection.document_id == document.id))

        rows = [
            row
            for index, item in enumerate(result.requirements)
            if (row := _to_row(document, index, item)) is not None
        ]
        if not rows:
            raise _StageFailure(
                Stage.EXTRACTION, "No readable requirement text was found in this document."
            )
        db.add_all(rows)
        db.flush()  # assigns ids
        db.add_all(
            RequirementVersion(requirement_id=row.id, version_no=1, body_snapshot=row.body)
            for row in rows
        )
        db.add_all(_section_row(document, section) for section in result.sections)
        document.status = DocumentStatus.DONE
        document.progress_percent = PROGRESS_DONE
        db.commit()
    except _StageFailure:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        logger.exception("Could not persist requirements for document %s", document.id)
        raise _StageFailure(
            Stage.PERSISTENCE, "The extracted requirements could not be saved. Please try again."
        ) from None


def _to_row(document: Document, order_index: int, item: ExtractedRequirement) -> Requirement | None:
    body = item.raw_text.replace("\x00", "")
    if not body.strip():
        return None
    return Requirement(
        document_id=document.id,
        project_id=document.project_id,
        # "Import as baseline" makes the requirements Approved (the baseline is the Approved
        # set, DR-13); "import as proposals" leaves them Proposed for review (FR-01, SX-08).
        state=(
            RequirementState.APPROVED
            if document.import_mode is ImportMode.BASELINE
            else RequirementState.PROPOSED
        ),
        origin=RequirementOrigin.DOCUMENT,
        stakeholder_group=document.stakeholder_group,
        # The ID printed in the document, or None. The segmenter's fallback "UNKNOWN-…" ``id``
        # is not an identifier from the document, so it is never stored as one (FR-04).
        source_req_id=item.source_req_id,
        body=body,
        location=(item.location or None) and item.location[:MAX_LOCATION_LENGTH],
        order_index=order_index,
        section_heading=item.section_heading,
        needs_review=item.needs_review,
        review_reasons=list(item.review_reasons),
    )


def _section_row(document: Document, section: ExtractedSection) -> DocumentSection:
    return DocumentSection(
        document_id=document.id,
        project_id=document.project_id,
        heading=section.heading and section.heading.replace("\x00", ""),
        body=section.body.replace("\x00", ""),
        location=section.location,
        order_index=section.order_index,
    )


def _draft_project_context(
    db: Session, document_id: uuid.UUID, sections: list[ExtractedSection]
) -> None:
    """Draft the brief from the initial SRS while the project is in Setup (FR-104)."""
    document = db.get(Document, document_id)
    if document is None or not sections:
        return
    project = db.get(Project, document.project_id)
    if project is None or project.status is not ProjectStatus.SETUP:
        return  # an active project's brief changes only when a person asks (POST …/draft)
    try:
        context_service.draft_from_sections(
            db,
            project_id=project.id,
            sections=sections,
            drafter=get_brief_drafter(project_id=project.id),
            document=document,
        )
    except Exception:
        db.rollback()
        logger.exception("Could not draft the project brief from document %s", document_id)


def _fail(db: Session, document_id: uuid.UUID, stage: Stage, message: str) -> ProcessingOutcome:
    db.rollback()
    document = db.get(Document, document_id)
    if document is not None:
        document.status = DocumentStatus.FAILED
        document.progress_percent = 0
        document.error_message = f"[{stage.value}] {message}"
        db.commit()
    return ProcessingOutcome.FAILED
