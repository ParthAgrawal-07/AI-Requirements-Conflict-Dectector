"""
Abstract base class for document parsers.

Every parser (PDF, DOCX, or future formats) MUST implement the
`parse()` method and return a list of format-agnostic RawSegment objects.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List

from app.ingestion.models import RawSegment


class Parser(ABC):
    """
    Abstract interface for document parsers.

    Concrete implementations:
        - PDFParser  (pdf_parser.py)
        - DOCXParser (docx_parser.py)
    """

    @abstractmethod
    def parse(self, file_path: str) -> List[RawSegment]:
        """
        Parse a document and return a list of RawSegment objects.

        Args:
            file_path: Absolute or relative path to the document file.

        Returns:
            Ordered list of RawSegment objects extracted from the document.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If the file format is unsupported by this parser.
        """
        ...

    @staticmethod
    def _validate_file_exists(file_path: str) -> Path:
        """Validate that a file exists and return a resolved Path object."""
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"File not found: {file_path}")
        return path
