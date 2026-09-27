"""
DOCX parser using python-docx.

Extracts text paragraph-by-paragraph from .docx files.
Empty paragraphs are skipped.

Unsupported formats (.doc, .txt, .odt, etc.) raise a clear ValueError.
"""

import docx
from typing import List

from app.ingestion.parsers.base import Parser
from app.ingestion.models import RawSegment

# Formats that users might accidentally provide instead of .docx
_UNSUPPORTED_ALTERNATIVES = {
    ".doc": "Legacy binary .doc format is not supported. Please convert to .docx.",
    ".odt": "OpenDocument .odt format is not supported. Please convert to .docx.",
    ".txt": "Plain text .txt is not supported by DOCXParser.",
    ".rtf": "Rich Text Format .rtf is not supported. Please convert to .docx.",
}


class DOCXParser(Parser):
    """Parse a .docx document into RawSegment objects, one per non-empty paragraph."""

    def parse(self, file_path: str) -> List[RawSegment]:
        path = self._validate_file_exists(file_path)
        suffix = path.suffix.lower()

        if suffix != ".docx":
            hint = _UNSUPPORTED_ALTERNATIVES.get(suffix, "")
            msg = f"Unsupported file format for DOCXParser: '{suffix}'."
            if hint:
                msg += f" {hint}"
            raise ValueError(msg)

        segments: List[RawSegment] = []
        doc_name = path.name
        order_index = 0

        document = docx.Document(str(path))
        for i, para in enumerate(document.paragraphs):
            text = para.text.strip()
            if not text:
                continue

            segments.append(
                RawSegment(
                    text=text,
                    source_document=doc_name,
                    page_or_paragraph=i + 1,  # 1-based paragraph index
                    order_index=order_index,
                )
            )
            order_index += 1

        return segments
