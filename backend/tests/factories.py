"""Builders for real documents used across upload/processing tests.

Real PDF and DOCX bytes (not mocks): the point of these tests is that validation and extraction
work on what users actually upload.
"""

import io
import uuid

import docx
import pymupdf

OLE_HEADER = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 512  # legacy .doc / encrypted docx


def make_pdf(*lines: str) -> bytes:
    """A one-page PDF with each line on its own row. Unique by default (no accidental dupes)."""
    document = pymupdf.open()
    page = document.new_page()
    y = 72.0
    for line in lines or (f"REQ-001: The system shall do {uuid.uuid4().hex}.",):
        page.insert_text((72, y), line)
        y += 18
    data: bytes = document.tobytes()
    document.close()
    return data


def make_docx(*paragraphs: str) -> bytes:
    document = docx.Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def unique_docx() -> bytes:
    return make_docx(f"REQ-001: The system shall do {uuid.uuid4().hex}.")


def pad_pdf(data: bytes, size: int) -> bytes:
    """Grow a valid PDF to exactly ``size`` bytes with a comment (legal anywhere in a PDF)."""
    missing = size - len(data)
    assert missing >= 2, "target size smaller than the PDF itself"  # noqa: S101
    header_end = data.index(b"\n") + 1
    return data[:header_end] + b"%" + b"p" * (missing - 2) + b"\n" + data[header_end:]
