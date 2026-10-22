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
        section_heading: Nearest preceding heading (DOCX only; the segmenter
            detects PDF headings from the text itself).
        is_list_item: True for a DOCX list paragraph (Word bullets/numbering are
            formatting, not text, so the segmenter can't see them otherwise).
        order_index: 0-based global ordering across the entire document.
    """

    model_config = {"frozen": True}

    text: str
    source_document: str
    page_or_paragraph: int
    location_type: Literal["page", "paragraph"]
    section_heading: str | None = None
    is_list_item: bool = False
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
        raw_text: The requirement's full text, verbatim from the source (wrapped
            lines re-joined; list sub-items kept on their own lines).
        source_document: Filename or path of the source document.
        location: Human-readable location string (e.g. "page 3" or "paragraph 12").
        section_heading: Heading the requirement appears under, if known.
        order_index: 0-based position of the requirement within the document.
        needs_review: True when segmentation is uncertain and a human should
            check this item (US-02: surfaced for manual review, not dropped).
        review_reasons: Why needs_review is set; empty when it is not.
        extracted_at: UTC timestamp of when this requirement was extracted.
    """

    model_config = {"frozen": True}

    id: str
    source_req_id: str | None = None
    raw_text: str
    source_document: str
    location: str
    section_heading: str | None = None
    order_index: int = 0
    needs_review: bool = False
    review_reasons: tuple[str, ...] = ()
    extracted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ExcludedText(BaseModel):
    """Text the segmenter decided is not a requirement (kept so it can be audited)."""

    model_config = {"frozen": True}

    text: str
    location: str
    reason: str


class DocumentSection(BaseModel):
    """One heading of the document and the text under it, verbatim (design update §12.1).

    Sections hold *all* text, requirements and prose alike. They feed ``document_sections``:
    the brief drafter reads the introduction and overall description from them (FR-104), and
    the context pack picks the most relevant ones for each LLM call (FR-105).

    Attributes:
        heading: The heading text, or None for text before the first heading.
        body: Paragraphs under the heading, separated by blank lines.
        location: Where the section starts (e.g. "page 2" or "paragraph 14").
        order_index: 0-based position of the section within the document.
    """

    model_config = {"frozen": True}

    heading: str | None
    body: str
    location: str
    order_index: int


class SegmentationResult(BaseModel):
    """Everything the segmenter produced for one document."""

    model_config = {"frozen": True}

    requirements: list[Requirement]
    excluded: list[ExcludedText] = Field(default_factory=list)
    sections: list[DocumentSection] = Field(default_factory=list)
