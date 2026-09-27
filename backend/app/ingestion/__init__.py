"""
Document Ingestion & Extraction module.

Public API:
    ingest(file_path) -> list[Requirement]

Models:
    RawSegment  — intermediate extraction format
    Requirement — final segmented requirement
"""

from app.ingestion.models import RawSegment, Requirement
from app.ingestion.pipeline import ingest

__all__ = ["ingest", "RawSegment", "Requirement"]
