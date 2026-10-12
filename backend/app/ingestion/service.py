"""
Run extraction for an uploaded document and store the results (US-02).

Called by the Celery task in ``app.ingestion.tasks``; kept separate so it can be
tested against a database session without a worker.

Flow:
    QUEUED -> PROCESSING -> DONE   (requirements + version-1 snapshots stored)
                         -> FAILED (error_message says why, in user-facing words)

Re-running is safe: a DONE document is left alone, and any rows left behind by an
interrupted run are replaced (Celery is configured with acks_late, so a task can
be delivered twice).
"""

import logging
import uuid
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.ingestion.pipeline import ingest_document
from app.models import Document, DocumentStatus, Requirement, RequirementVersion

logger = logging.getLogger(__name__)

# Column sizes from app.models.requirement
_MAX_LOCATION = 64
_MAX_SECTION_HEADING = 255
_MAX_SOURCE_REQ_ID = 64


def _clip(value: str | None, max_len: int) -> str | None:
    return value[:max_len] if value else None


def _fail(session: Session, document: Document, message: str) -> Document:
    document.status = DocumentStatus.FAILED
    document.error_message = message
    session.commit()
    return document


def extract_document(session: Session, document_id: uuid.UUID) -> Document | None:
    """Extract requirements from a stored upload and persist them.

    Returns the document, or None if it no longer exists.
    Unexpected errors mark the document FAILED and are re-raised.
    """
    document = session.get(Document, document_id)
    if document is None:
        logger.warning("Document %s not found; skipping extraction", document_id)
        return None
    if document.status == DocumentStatus.DONE:
        logger.info("Document %s already extracted; skipping", document_id)
        return document

    document.status = DocumentStatus.PROCESSING
    document.progress_percent = 10
    document.error_message = None
    session.commit()  # make PROCESSING visible to status polling (US-03)

    stored_name = Path(document.storage_path).name
    try:
        result = ingest_document(document.storage_path)
    except FileNotFoundError:
        # Don't leak the server-side storage path into a user-facing message.
        return _fail(session, document, "The uploaded file could not be found on the server.")
    except ValueError as exc:  # unsupported format, or DocumentParseError
        # Parsers name the file they opened; show the user the name they uploaded.
        return _fail(session, document, str(exc).replace(stored_name, document.filename))
    except Exception:
        logger.exception("Extraction crashed for document %s", document_id)
        _fail(session, document, "Unexpected error while extracting requirements.")
        raise

    if not result.requirements:
        return _fail(
            session,
            document,
            "No requirement statements were found in this document "
            f"({len(result.excluded)} passages were recognised as non-requirement text).",
        )

    session.execute(delete(Requirement).where(Requirement.document_id == document.id))
    for extracted in result.requirements:
        requirement = Requirement(
            document_id=document.id,
            source_req_id=_clip(extracted.source_req_id, _MAX_SOURCE_REQ_ID),
            body=extracted.raw_text,
            location=extracted.location[:_MAX_LOCATION],
            section_heading=_clip(extracted.section_heading, _MAX_SECTION_HEADING),
            order_index=extracted.order_index,
            needs_review=extracted.needs_review,
            review_reason="; ".join(extracted.review_reasons) or None,
        )
        # Initial snapshot; changed_by is NULL because the system, not a person, wrote it.
        requirement.versions.append(
            RequirementVersion(version_no=1, body_snapshot=extracted.raw_text)
        )
        session.add(requirement)

    document.status = DocumentStatus.DONE
    document.progress_percent = 100
    session.commit()

    logger.info(
        "Stored %d requirements for document %s (%d need review, %d passages excluded)",
        len(result.requirements),
        document_id,
        sum(r.needs_review for r in result.requirements),
        len(result.excluded),
    )
    return document
