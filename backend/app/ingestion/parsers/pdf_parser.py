"""
PDF parser using PyMuPDF.

Extracts text page-by-page from born-digital PDFs. No OCR is performed.

Each page becomes one RawSegment whose paragraphs are separated by a blank line,
so the segmenter can tell a paragraph break from a line that merely wrapped. The
paragraphs are rebuilt from line positions (pdf_layout): borderless table rows come
out as one "cell | cell" line each, and lines a PDF writer split apart are rejoined.

Running headers, footers and page numbers are removed here because only the
parser knows where on the page a block sits: a block in the top/bottom margin
is dropped if it is a bare page number, or if the same text (ignoring digits)
sits in the margin of at least half the pages.
"""

import math
import re
from collections import Counter

import pymupdf  # PyMuPDF (fitz API is deprecated)

from app.ingestion.errors import DocumentParseError
from app.ingestion.models import RawSegment
from app.ingestion.parsers.base import Parser
from app.ingestion.parsers.pdf_layout import Line, body_font_size, page_lines, read_page
from app.ingestion.segmentation.rules import (
    PAGE_NUMBER_PATTERN,
    REQUIREMENT_ID_PATTERN,
    STRONG_MODAL_PATTERN,
)

# Fraction of the page height treated as header (top) / footer (bottom) margin.
_MARGIN_FRACTION = 0.1
# Longer blocks are body text, never running headers/footers.
_MAX_HEADER_FOOTER_CHARS = 120

# (text, in_margin) per block, per page
_PageBlocks = list[tuple[str, bool]]


def _normalize(text: str) -> str:
    """Key for spotting repeated headers/footers: "Page 3 of 10" == "Page 7 of 10"."""
    return re.sub(r"\d+", "#", " ".join(text.lower().split()))


def _could_be_header_footer(text: str) -> bool:
    return (
        len(text) <= _MAX_HEADER_FOOTER_CHARS
        and not REQUIREMENT_ID_PATTERN.match(text)
        and not STRONG_MODAL_PATTERN.search(text)
    )


class PDFParser(Parser):
    """Parse a PDF document into RawSegment objects, one per non-empty page."""

    def parse(self, file_path: str) -> list[RawSegment]:
        path = self._validate_file_exists(file_path)

        if path.suffix.lower() != ".pdf":
            raise ValueError(
                f"Unsupported file format for PDFParser: '{path.suffix}'. "
                f"Only .pdf files are supported."
            )

        doc_name = path.name

        try:
            doc = pymupdf.open(str(path))
        except pymupdf.FileDataError as exc:
            raise DocumentParseError(f"'{doc_name}' is not a valid PDF or is corrupted.") from exc

        with doc:
            if doc.needs_pass:
                raise DocumentParseError(
                    f"'{doc_name}' is password-protected. Please upload an unencrypted PDF."
                )
            heights = [doc[i].rect.height for i in range(len(doc))]
            lines = [page_lines(doc[i]) for i in range(len(doc))]

        body_size = body_font_size(lines)
        pages = [
            self._page_blocks(page, height, body_size)
            for page, height in zip(lines, heights, strict=True)
        ]

        repeated = self._repeated_margin_texts(pages)

        segments: list[RawSegment] = []
        order_index = 0
        for page_num, blocks in enumerate(pages):
            kept = [
                text
                for text, in_margin in blocks
                if not (
                    in_margin
                    and _could_be_header_footer(text)
                    and (PAGE_NUMBER_PATTERN.match(text) or _normalize(text) in repeated)
                )
            ]
            if not kept:
                continue

            segments.append(
                RawSegment(
                    text="\n\n".join(kept),
                    source_document=doc_name,
                    page_or_paragraph=page_num + 1,  # 1-based page number
                    location_type="page",
                    order_index=order_index,
                )
            )
            order_index += 1

        return segments

    @staticmethod
    def _page_blocks(lines: list[Line], height: float, body_size: float) -> _PageBlocks:
        top, bottom = height * _MARGIN_FRACTION, height * (1 - _MARGIN_FRACTION)
        return [
            (block.text, block.y1 <= top or block.y0 >= bottom)
            for block in read_page(lines, body_size)
        ]

    @staticmethod
    def _repeated_margin_texts(pages: list[_PageBlocks]) -> set[str]:
        """Normalized margin texts appearing on at least half the pages (min. 2)."""
        if len(pages) < 2:
            return set()
        counts: Counter[str] = Counter()
        for blocks in pages:
            counts.update(
                {
                    _normalize(t)
                    for t, in_margin in blocks
                    if in_margin and _could_be_header_footer(t)
                }
            )
        threshold = max(2, math.ceil(len(pages) / 2))
        return {text for text, n in counts.items() if n >= threshold}
