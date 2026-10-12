"""Validation of uploaded files (Role 5 — US-01, FR-02).

A file is accepted only if **all** of these hold:

* its extension is one the ingestion pipeline can actually process (``SUPPORTED_FORMATS``) —
  accepting a file that ingestion will reject later would just move the failure downstream;
* it is not empty;
* its *content* matches its extension (magic bytes), so ``malware.exe`` renamed to ``srs.pdf``
  or a Word file named ``srs.pdf`` is rejected with a specific message. The client-supplied
  ``Content-Type`` header is never consulted — it is attacker-controlled;
* it is structurally plausible: a PDF has an end-of-file marker (truncated downloads don't),
  and a DOCX is a ZIP holding ``word/document.xml`` whose declared uncompressed size and entry
  count are bounded (zip-bomb protection).

These are cheap checks that run in the API process. Deep parsing (encrypted PDFs, damaged
XML...) is the worker's job; anything it can't read fails the document with a readable reason.
"""

import re
import unicodedata
import zipfile
from pathlib import Path
from typing import NoReturn

from app.core.errors import BadRequestError
from app.models.enums import DocumentFormat

# Single source of truth for what upload accepts. tests/services/test_upload_validation.py
# asserts this matches what app.ingestion can parse, so the two can't silently drift apart.
SUPPORTED_FORMATS: dict[str, DocumentFormat] = {
    ".pdf": DocumentFormat.PDF,
    ".docx": DocumentFormat.DOCX,
}

MAX_FILENAME_LENGTH = 255
MAX_DOCX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024
MAX_DOCX_ENTRIES = 5_000

_PDF_HEAD_WINDOW = 1024  # PDF readers accept the %PDF- header anywhere in the first 1 KiB
_PDF_EOF_WINDOW = 2048  # ...and the %%EOF marker within the last 2 KiB
_ZIP_MAGIC = b"PK\x03\x04"
_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"  # legacy .doc, or a password-protected .docx
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")

_SUPPORTED_SUMMARY = "Supported formats: PDF (.pdf) and Word (.docx)."
_KNOWN_UNSUPPORTED_HINTS: dict[str, str] = {
    ".doc": "Legacy .doc files are not supported — save the document as .docx and upload that.",
    ".rtf": "RTF files are not supported — save the document as .docx or .pdf.",
    ".odt": "OpenDocument files are not supported — save the document as .docx or .pdf.",
    ".txt": "Plain-text (.txt) upload is not supported yet.",
    ".reqif": "ReqIF upload is not supported yet.",
    ".reqifz": "ReqIF upload is not supported yet.",
}


def sanitize_filename(raw: str | None) -> str:
    """Return a safe display name: no directories, no control characters, bounded length.

    The result is only ever used for display and validation — stored files are named by
    document id, never by anything the client sent.
    """
    name = unicodedata.normalize("NFC", raw or "")
    name = name.replace("\\", "/").rsplit("/", 1)[-1]  # drop any client-side directory
    name = _CONTROL_CHARS.sub("", name).strip().rstrip(". ")
    if not name:
        return "document"
    if len(name) > MAX_FILENAME_LENGTH:
        suffix = Path(name).suffix[:16]
        name = name[: MAX_FILENAME_LENGTH - len(suffix)] + suffix
    return name


def extension_of(filename: str) -> str:
    return Path(filename).suffix.lower()


def validate_upload(path: Path, filename: str) -> DocumentFormat:
    """Validate the staged file at ``path`` and return its detected format.

    ``filename`` must already be sanitized. Raises :class:`BadRequestError` with a specific,
    user-presentable message and a machine-readable code:

    ``unsupported_file_type`` · ``empty_file`` · ``file_content_mismatch`` ·
    ``corrupted_file`` · ``unsafe_file``
    """
    extension = extension_of(filename)
    expected = SUPPORTED_FORMATS.get(extension)
    if expected is None:
        raise BadRequestError(_unsupported_message(extension), code="unsupported_file_type")

    size = path.stat().st_size
    if size == 0:
        raise BadRequestError("The uploaded file is empty.", code="empty_file")

    with path.open("rb") as handle:
        head = handle.read(_PDF_HEAD_WINDOW)
    actual = _sniff(head)

    if expected is DocumentFormat.PDF:
        if actual == "pdf":
            _check_pdf_complete(path, size)
            return expected
        _raise_wrong_content(extension, actual, "a PDF")
    if actual == "zip":
        _check_docx_structure(path)
        return expected
    _raise_wrong_content(extension, actual, "a Word (.docx) document")


def _sniff(head: bytes) -> str | None:
    if b"%PDF-" in head:
        return "pdf"
    if head.startswith(_ZIP_MAGIC):
        return "zip"
    if head.startswith(_OLE_MAGIC):
        return "ole"
    return None


def _unsupported_message(extension: str) -> str:
    if not extension:
        return f"The file has no extension, so its type can't be determined. {_SUPPORTED_SUMMARY}"
    shown = extension[:16]
    hint = _KNOWN_UNSUPPORTED_HINTS.get(extension)
    parts = [f"Unsupported file type '{shown}'."]
    if hint:
        parts.append(hint)
    parts.append(_SUPPORTED_SUMMARY)
    return " ".join(parts)


def _raise_wrong_content(extension: str, actual: str | None, wanted: str) -> NoReturn:
    if actual is None:
        raise BadRequestError(
            f"The file has a '{extension}' extension but its content is not {wanted}; it may be "
            "corrupted or incomplete. Re-export the document and try again.",
            code="corrupted_file",
        )
    if actual == "ole":
        raise BadRequestError(
            f"The file has a '{extension}' extension but looks like a legacy Word (.doc) file or a "
            "password-protected Office file. Save it as an unprotected .docx and upload that.",
            code="file_content_mismatch",
        )
    described = {"pdf": "a PDF document", "zip": "a ZIP-based file (for example a Word .docx)"}
    raise BadRequestError(
        f"The file has a '{extension}' extension but its content is {described[actual]}, not {wanted}. "
        "Upload the correct file or fix its extension.",
        code="file_content_mismatch",
    )


def _check_pdf_complete(path: Path, size: int) -> None:
    with path.open("rb") as handle:
        handle.seek(max(0, size - _PDF_EOF_WINDOW))
        tail = handle.read()
    if b"%%EOF" not in tail:
        raise BadRequestError(
            "The PDF appears to be truncated (no end-of-file marker). It may have been only "
            "partly downloaded or saved — re-export it and try again.",
            code="corrupted_file",
        )


def _check_docx_structure(path: Path) -> None:
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            names = {entry.filename for entry in entries}
    except (zipfile.BadZipFile, NotImplementedError, EOFError):
        raise BadRequestError(
            "The .docx file is corrupted and could not be opened as a Word document.",
            code="corrupted_file",
        ) from None

    if len(entries) > MAX_DOCX_ENTRIES or (
        sum(entry.file_size for entry in entries) > MAX_DOCX_UNCOMPRESSED_BYTES
    ):
        raise BadRequestError(
            "The document expands to an unreasonable size and was rejected for safety.",
            code="unsafe_file",
        )
    if "[Content_Types].xml" not in names or "word/document.xml" not in names:
        raise BadRequestError(
            "This ZIP archive is not a Word document (word/document.xml is missing). "
            "Upload a real .docx file.",
            code="file_content_mismatch",
        )
