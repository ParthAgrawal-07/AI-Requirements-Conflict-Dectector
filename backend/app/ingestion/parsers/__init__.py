"""Parsers sub-package. Provides PDFParser and DOCXParser."""

from app.ingestion.parsers.pdf_parser import PDFParser
from app.ingestion.parsers.docx_parser import DOCXParser

__all__ = ["PDFParser", "DOCXParser"]
