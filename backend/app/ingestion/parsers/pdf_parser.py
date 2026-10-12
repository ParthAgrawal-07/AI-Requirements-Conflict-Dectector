"""
PDF parser using PyMuPDF.

Extracts text page-by-page from born-digital PDFs.
Empty pages are skipped. No OCR is performed.
"""

import pymupdf  # PyMuPDF (fitz API is deprecated)

from app.ingestion.errors import DocumentParseError
from app.ingestion.models import RawSegment
from app.ingestion.parsers.base import Parser


class PDFParser(Parser):
    """Parse a PDF document into RawSegment objects, one per non-empty page."""

    def parse(self, file_path: str) -> list[RawSegment]:
        path = self._validate_file_exists(file_path)

        if path.suffix.lower() != ".pdf":
            raise ValueError(
                f"Unsupported file format for PDFParser: '{path.suffix}'. "
                f"Only .pdf files are supported."
            )

        segments: list[RawSegment] = []
        doc_name = path.name
        order_index = 0

        try:
            doc = pymupdf.open(str(path))
        except pymupdf.FileDataError as exc:
            raise DocumentParseError(f"'{doc_name}' is not a valid PDF or is corrupted.") from exc

        with doc:
            if doc.needs_pass:
                raise DocumentParseError(
                    f"'{doc_name}' is password-protected. Please upload an unencrypted PDF."
                )

            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text().strip()
                if not text:
                    continue

                segments.append(
                    RawSegment(
                        text=text,
                        source_document=doc_name,
                        page_or_paragraph=page_num + 1,  # 1-based page number
                        location_type="page",
                        order_index=order_index,
                    )
                )
                order_index += 1

        return segments
