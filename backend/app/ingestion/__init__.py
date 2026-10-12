"""
Document Ingestion & Extraction module.

Public API:
    ingest(file_path) -> list[Requirement]
    ingest_document(file_path) -> SegmentationResult

Models:
    RawSegment  — intermediate extraction format
    Requirement — final segmented requirement

Errors:
    DocumentParseError — corrupted, encrypted, or text-less file (a ValueError)
"""

from app.ingestion.errors import DocumentParseError
from app.ingestion.models import ExcludedText, RawSegment, Requirement, SegmentationResult
from app.ingestion.pipeline import ingest, ingest_document

__all__ = [
    "DocumentParseError",
    "ExcludedText",
    "RawSegment",
    "Requirement",
    "SegmentationResult",
    "ingest",
    "ingest_document",
]
