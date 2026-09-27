"""
Document Ingestion & Extraction module.

Public API:
    ingest(file_path) -> list[Requirement]

Models:
    RawSegment  — intermediate extraction format
    Requirement — final segmented requirement
"""

from app.ingestion.pipeline import ingest
from app.ingestion.models import RawSegment, Requirement

__all__ = ["ingest", "RawSegment", "Requirement"]
