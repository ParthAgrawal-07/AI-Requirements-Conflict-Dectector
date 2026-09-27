"""
Pydantic models for the ingestion pipeline.

These models are format-agnostic — both PDFParser and DOCXParser
produce identical RawSegment instances. The Requirement model is the
final output of segmentation.
"""

from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import Optional


class RawSegment(BaseModel):
    """
    A chunk of text extracted from a single page (PDF) or paragraph (DOCX).

    Attributes:
        text: The extracted text content.
        source_document: Filename or path of the source document.
        page_or_paragraph: 1-based page number (PDF) or paragraph index (DOCX).
        section_heading: Nearest section heading, if detected. None in Sprint 0.
        order_index: 0-based global ordering across the entire document.
    """

    model_config = {"frozen": True}

    text: str
    source_document: str
    page_or_paragraph: int
    section_heading: Optional[str] = None
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
        raw_text: The full text of the requirement line.
        source_document: Filename or path of the source document.
        location: Human-readable location string (e.g. "page 3" or "paragraph 12").
        extracted_at: UTC timestamp of when this requirement was extracted.
    """

    model_config = {"frozen": True}

    id: str
    raw_text: str
    source_document: str
    location: str
    extracted_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
