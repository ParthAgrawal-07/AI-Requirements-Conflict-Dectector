"""
Pydantic models for the ingestion pipeline.

These models are format-agnostic — both PDFParser and DOCXParser
produce identical RawSegment instances. The Requirement model is the
final output of segmentation.
"""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


class RawSegment(BaseModel):
    """
    A chunk of text extracted from a single page (PDF) or paragraph (DOCX).

    Attributes:
        text: The extracted text content.
        source_document: Filename or path of the source document.
        page_or_paragraph: 1-based page number (PDF) or body-block index (DOCX;
            each paragraph and each table row counts as one block).
        location_type: Whether page_or_paragraph is a "page" or a "paragraph".
        section_heading: Nearest preceding heading (DOCX only for now; None for PDF).
        order_index: 0-based global ordering across the entire document.
    """

    model_config = {"frozen": True}

    text: str
    source_document: str
    page_or_paragraph: int
    location_type: Literal["page", "paragraph"]
    section_heading: str | None = None
    order_index: int

    def __repr__(self) -> str:
        preview = self.text[:60].replace("\n", "\\n")
        return (
            f"RawSegment(source={self.source_document!r}, "
            f"page_or_para={self.page_or_paragraph}, "
            f"order={self.order_index}, "
            f"text={preview!r}...)"
        )


class Requirement(BaseModel):
    """
    A single requirement extracted from a document.

    Attributes:
        id: Requirement identifier (e.g. "REQ-001") or a deterministic
            fallback ID if none was detected.
        source_req_id: The ID as written in the document, or None if the line
            had no ID (maps to requirements.source_req_id in the data model).
        raw_text: The full text of the requirement line.
        source_document: Filename or path of the source document.
        location: Human-readable location string (e.g. "page 3" or "paragraph 12").
        section_heading: Heading the requirement appears under, if known.
        extracted_at: UTC timestamp of when this requirement was extracted.
    """

    model_config = {"frozen": True}

    id: str
    source_req_id: str | None = None
    raw_text: str
    source_document: str
    location: str
    section_heading: str | None = None
    extracted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
