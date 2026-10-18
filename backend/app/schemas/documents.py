"""Document and requirement schemas (Role 5 — US-01, US-03, US-04).

``DocumentRead`` is a superset of the response documented in docs/engineering/api-reference.md
(``document_id``, ``status``, ``filename``), so a frontend written against that contract keeps
working. ``storage_path`` and ``sha256`` are deliberately not exposed: they are internal.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models import Document, Requirement
from app.models.enums import DocumentFormat, DocumentStatus


class DocumentRead(BaseModel):
    document_id: uuid.UUID
    filename: str
    format: DocumentFormat
    size_bytes: int
    status: DocumentStatus
    progress_percent: int
    # Human-readable reason, prefixed with the failed stage, e.g. "[extraction] ..." (US-03).
    error_message: str | None
    requirement_count: int
    uploaded_by: uuid.UUID
    uploaded_at: datetime
    # Set only on the upload response: the earlier document in this workspace with identical
    # content, if any. Informational — the upload is still accepted.
    duplicate_of: uuid.UUID | None = None

    @classmethod
    def from_model(
        cls,
        document: Document,
        *,
        requirement_count: int,
        duplicate_of: uuid.UUID | None = None,
    ) -> "DocumentRead":
        return cls(
            document_id=document.id,
            filename=document.filename,
            format=document.format,
            size_bytes=document.size_bytes,
            status=document.status,
            progress_percent=document.progress_percent,
            error_message=document.error_message,
            requirement_count=requirement_count,
            uploaded_by=document.uploaded_by,
            uploaded_at=document.uploaded_at,
            duplicate_of=duplicate_of,
        )


class RequirementRead(BaseModel):
    requirement_id: uuid.UUID
    document_id: uuid.UUID
    # The identifier printed in the source document ("REQ-014"), or null if it had none —
    # we never present a generated ID as if it came from the document (FR-04).
    source_req_id: str | None
    body: str
    location: str | None
    order_index: int
    stakeholder_group: str | None
    is_protected: bool
    current_version: int

    @classmethod
    def from_model(cls, requirement: Requirement) -> "RequirementRead":
        return cls(
            requirement_id=requirement.id,
            document_id=requirement.document_id,
            source_req_id=requirement.source_req_id,
            body=requirement.body,
            location=requirement.location,
            order_index=requirement.order_index,
            stakeholder_group=requirement.stakeholder_group,
            is_protected=requirement.is_protected,
            current_version=requirement.current_version,
        )
