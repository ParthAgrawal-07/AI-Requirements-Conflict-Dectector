"""
DOCX parser using python-docx.

Walks the document body in reading order, emitting one segment per non-empty
paragraph and one per non-empty table row (cells joined with " | "), since SRS
documents frequently list requirements in ID/description tables.

Heading paragraphs are not emitted as segments; their text is attached as
`section_heading` to the segments that follow them. Table-of-contents paragraphs
(Word's "TOC n" styles) are skipped. List paragraphs are marked is_list_item,
because Word bullets/numbering are formatting and never appear in the text.

Unsupported formats (.doc, .txt, .odt, etc.) raise a clear ValueError.
"""

from typing import Literal
from zipfile import BadZipFile

import docx
from docx.opc.exceptions import PackageNotFoundError
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.ingestion.errors import DocumentParseError
from app.ingestion.models import RawSegment
from app.ingestion.parsers.base import Parser

# Formats that users might accidentally provide instead of .docx
_UNSUPPORTED_ALTERNATIVES = {
    ".doc": "Legacy binary .doc format is not supported. Please convert to .docx.",
    ".odt": "OpenDocument .odt format is not supported. Please convert to .docx.",
    ".txt": "Plain text .txt is not supported by DOCXParser.",
    ".rtf": "Rich Text Format .rtf is not supported. Please convert to .docx.",
}


_BlockKind = Literal["text", "heading", "list", "toc"]


def _paragraph_kind(para: Paragraph) -> _BlockKind:
    style_name = (para.style.name if para.style is not None else None) or ""
    if style_name.startswith("TOC"):  # "TOC 1", "TOC 2", ..., "TOC Heading"
        return "toc"
    if style_name == "Title" or style_name.startswith("Heading"):
        return "heading"
    p_pr = para._p.pPr
    if style_name.startswith("List") or (p_pr is not None and p_pr.numPr is not None):
        return "list"
    return "text"


def _row_text(row) -> str:
    """Join a table row's cell texts, skipping blanks and horizontally merged duplicates."""
    cells: list[str] = []
    for cell in row.cells:
        text = cell.text.strip()
        if text and (not cells or cells[-1] != text):
            cells.append(text)
    return " | ".join(cells)


class DOCXParser(Parser):
    """Parse a .docx document into RawSegment objects (paragraphs and table rows)."""

    def parse(self, file_path: str) -> list[RawSegment]:
        path = self._validate_file_exists(file_path)
        suffix = path.suffix.lower()

        if suffix != ".docx":
            hint = _UNSUPPORTED_ALTERNATIVES.get(suffix, "")
            msg = f"Unsupported file format for DOCXParser: '{suffix}'."
            if hint:
                msg += f" {hint}"
            raise ValueError(msg)

        doc_name = path.name

        try:
            document = docx.Document(str(path))
        except (PackageNotFoundError, BadZipFile, KeyError) as exc:
            raise DocumentParseError(
                f"'{doc_name}' is not a valid .docx file or is corrupted."
            ) from exc

        # Flatten the body into (block_text, kind) in reading order;
        # each table row is its own block so a row = one candidate requirement.
        blocks: list[tuple[str, _BlockKind]] = []
        for item in document.iter_inner_content():
            if isinstance(item, Paragraph):
                blocks.append((item.text.strip(), _paragraph_kind(item)))
            elif isinstance(item, Table):
                blocks.extend((_row_text(row), "text") for row in item.rows)

        segments: list[RawSegment] = []
        current_heading: str | None = None
        order_index = 0

        for i, (text, kind) in enumerate(blocks):
            if not text or kind == "toc":
                continue
            if kind == "heading":
                current_heading = text
                continue

            segments.append(
                RawSegment(
                    text=text,
                    source_document=doc_name,
                    page_or_paragraph=i + 1,  # 1-based block index
                    location_type="paragraph",
                    section_heading=current_heading,
                    is_list_item=kind == "list",
                    order_index=order_index,
                )
            )
            order_index += 1

        return segments
