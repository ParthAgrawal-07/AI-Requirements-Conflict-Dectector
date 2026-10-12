"""
Document Ingestion & Extraction module.

Public API:
    ingest(file_path) -> list[Requirement]

Models:
    RawSegment  — intermediate extraction format
    Requirement — final segmented requirement

Errors:
    DocumentParseError — corrupted, encrypted, or text-less file (a ValueError)
"""

from app.ingestion.errors import DocumentParseError
from app.ingestion.models import RawSegment, Requirement
from app.ingestion.pipeline import ingest

__all__ = ["ingest", "DocumentParseError", "RawSegment", "Requirement"]
