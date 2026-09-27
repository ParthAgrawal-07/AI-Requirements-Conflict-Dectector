"""
Ingestion pipeline entry point.

Provides the `ingest()` function which is the single public interface
for converting a document file into a list of Requirement objects.

Usage:
    from app.ingestion.pipeline import ingest
    requirements = ingest("/path/to/document.pdf")
"""

import logging
from pathlib import Path

from app.ingestion.models import Requirement
from app.ingestion.parsers.base import Parser
from app.ingestion.parsers.docx_parser import DOCXParser
from app.ingestion.parsers.pdf_parser import PDFParser
from app.ingestion.segmentation.segmenter import Segmenter

logger = logging.getLogger(__name__)

# Map of supported extensions to their parser classes
_PARSERS: dict[str, type[Parser]] = {
    ".pdf": PDFParser,
    ".docx": DOCXParser,
}

# Common unsupported formats with helpful messages
_UNSUPPORTED_HINTS: dict[str, str] = {
    ".doc": "Legacy .doc format is not supported. Please convert to .docx.",
    ".txt": "Plain text files are not supported.",
    ".odt": "OpenDocument format is not supported. Please convert to .docx or .pdf.",
    ".rtf": "RTF format is not supported. Please convert to .docx or .pdf.",
}


def ingest(file_path: str) -> list[Requirement]:
    """
    Parse a document and extract requirements from it.

    This is the main entry point for the ingestion module. It:
    1. Validates the file exists
    2. Selects the appropriate parser based on file extension
    3. Parses the document into RawSegments
    4. Segments RawSegments into individual Requirements

    Args:
        file_path: Path to a .pdf or .docx file.

    Returns:
        List of Requirement objects extracted from the document.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file format is not supported.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {file_path}")

    ext = path.suffix.lower()

    parser_cls = _PARSERS.get(ext)
    if parser_cls is None:
        hint = _UNSUPPORTED_HINTS.get(ext, "")
        msg = f"Unsupported file format: '{ext}'."
        if hint:
            msg += f" {hint}"
        raise ValueError(msg)

    logger.info("Ingesting %s with %s", path.name, parser_cls.__name__)

    parser = parser_cls()
    raw_segments = parser.parse(file_path)

    logger.info("Extracted %d raw segments from %s", len(raw_segments), path.name)

    segmenter = Segmenter()
    requirements = segmenter.segment(raw_segments)

    logger.info("Produced %d requirements from %s", len(requirements), path.name)

    return requirements
