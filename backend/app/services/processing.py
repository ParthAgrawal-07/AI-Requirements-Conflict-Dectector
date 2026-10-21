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
"""

import logging
import uuid
from collections.abc import Callable
from enum import StrEnum

from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.ingestion import Requirement as ExtractedRequirement
from app.ingestion import ingest
from app.ingestion.segmentation.rules import REQUIREMENT_ID_PATTERN
from app.models import (
    Document,
    DocumentStatus,
    ImportMode,
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
    extract: Callable[[str], list[ExtractedRequirement]] = ingest,
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
        extracted = _extract(document, storage, extract)
        _persist(db, document, extracted)
    except _StageFailure as failure:
        return _fail(db, document_id, failure.stage, failure.message)

    logger.info("Processed document %s: %d requirements", document_id, len(extracted))
    return ProcessingOutcome.DONE


def _extract(
    document: Document,
    storage: LocalFileStorage,
    extract: Callable[[str], list[ExtractedRequirement]],
) -> list[ExtractedRequirement]:
    path = storage.resolve(document.storage_path)
    if not path.is_file():
        raise _StageFailure(
            Stage.STORAGE,
            "The uploaded file could not be found by the processing worker. If this keeps "
            "happening, the API and worker do not share the uploads volume.",
        )
    try:
        extracted = extract(str(path))
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
    if not extracted:
        raise _StageFailure(
            Stage.EXTRACTION,
            "No requirement statements were found in this document. Scanned (image-only) and "
            "password-protected files are not supported.",
        )
    return extracted


def _persist(db: Session, document: Document, extracted: list[ExtractedRequirement]) -> None:
    try:
        # A re-run replaces earlier partial output. Versions/embeddings go with it (ON DELETE CASCADE).
        db.execute(delete(Requirement).where(Requirement.document_id == document.id))

        rows = [
            row
            for index, item in enumerate(extracted)
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
        # The segmenter invents "UNKNOWN-<page>-<line>" IDs for lines without one. Those are
        # not identifiers from the document, so they are not stored as such (FR-04).
        source_req_id=item.id if REQUIREMENT_ID_PATTERN.fullmatch(item.id) else None,
        body=body,
        location=(item.location or None) and item.location[:MAX_LOCATION_LENGTH],
        order_index=order_index,
    )


def _fail(db: Session, document_id: uuid.UUID, stage: Stage, message: str) -> ProcessingOutcome:
    db.rollback()
    document = db.get(Document, document_id)
    if document is not None:
        document.status = DocumentStatus.FAILED
        document.progress_percent = 0
        document.error_message = f"[{stage.value}] {message}"
        db.commit()
    return ProcessingOutcome.FAILED
