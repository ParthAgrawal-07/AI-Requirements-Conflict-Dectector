"""
Document Ingestion & Extraction module.

Public API:
    ingest(file_path) -> list[Requirement]
    ingest_document(file_path) -> SegmentationResult

Models:
    RawSegment      — intermediate extraction format
    Requirement     — final segmented requirement
    DocumentSection — a heading and the verbatim text under it (for the project context)

Errors:
    DocumentParseError — corrupted, encrypted, or text-less file (a ValueError)
"""

from app.ingestion.errors import DocumentParseError
from app.ingestion.models import (
    DocumentSection,
    ExcludedText,
    RawSegment,
    Requirement,
    SegmentationResult,
)
from app.ingestion.pipeline import ingest, ingest_document

__all__ = [
    "DocumentParseError",
    "DocumentSection",
    "ExcludedText",
    "RawSegment",
    "Requirement",
    "SegmentationResult",
    "ingest",
    "ingest_document",
]
