"""Upload validation: filename hygiene, format allow-list, content sniffing, zip-bomb limits."""

import io
import zipfile
from pathlib import Path

import pytest

from app.core.errors import BadRequestError
from app.ingestion.pipeline import _PARSERS
from app.models.enums import DocumentFormat
from app.services import upload_validation
from app.services.upload_validation import (
    SUPPORTED_FORMATS,
    sanitize_filename,
    validate_upload,
)
from tests.factories import OLE_HEADER, make_docx, make_pdf


def write(tmp_path: Path, data: bytes, name: str = "upload.bin") -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


def code_of(tmp_path: Path, data: bytes, filename: str) -> str:
    with pytest.raises(BadRequestError) as caught:
        validate_upload(write(tmp_path, data), filename)
    return caught.value.code


def message_of(tmp_path: Path, data: bytes, filename: str) -> str:
    with pytest.raises(BadRequestError) as caught:
        validate_upload(write(tmp_path, data), filename)
    return caught.value.message


def make_zip(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_upload_accepts_exactly_the_formats_ingestion_can_parse() -> None:
    """If Bansil adds a parser (e.g. .txt), this fails until upload validation is extended too."""
    assert set(SUPPORTED_FORMATS) == set(_PARSERS)


class TestSanitizeFilename:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("srs.pdf", "srs.pdf"),
            ("../../etc/passwd.pdf", "passwd.pdf"),
            ("C:\\Users\\ana\\srs v2.docx", "srs v2.docx"),
            ("/abs/path/spec.docx", "spec.docx"),
            ("evil\x00name\r\n.pdf", "evilname.pdf"),
            ("  padded.pdf  ", "padded.pdf"),
            ("trailing-dots.pdf...", "trailing-dots.pdf"),
            ("", "document"),
            (None, "document"),
            ("///", "document"),
            ("\u0065\u0301.pdf", "\u00e9.pdf"),  # NFC-normalised
        ],
    )
    def test_cleans_names(self, raw: str | None, expected: str) -> None:
        assert sanitize_filename(raw) == expected

    def test_long_names_are_truncated_but_keep_their_extension(self) -> None:
        cleaned = sanitize_filename("a" * 400 + ".pdf")
        assert len(cleaned) == 255
        assert cleaned.endswith(".pdf")


class TestAccepted:
    def test_pdf(self, tmp_path: Path) -> None:
        assert validate_upload(write(tmp_path, make_pdf()), "srs.pdf") is DocumentFormat.PDF

    def test_docx(self, tmp_path: Path) -> None:
        assert (
            validate_upload(write(tmp_path, make_docx("hello")), "srs.docx") is DocumentFormat.DOCX
        )

    def test_extension_case_does_not_matter(self, tmp_path: Path) -> None:
        assert validate_upload(write(tmp_path, make_pdf()), "SRS.PDF") is DocumentFormat.PDF

    def test_pdf_header_may_follow_a_little_leading_junk(self, tmp_path: Path) -> None:
        data = b"\n\n  junk before header\n" + make_pdf()
        assert validate_upload(write(tmp_path, data), "srs.pdf") is DocumentFormat.PDF


class TestRejected:
    @pytest.mark.parametrize("name", ["notes.txt", "old.doc", "spec.reqif", "x.exe", "a.PNG"])
    def test_unsupported_extension(self, tmp_path: Path, name: str) -> None:
        assert code_of(tmp_path, make_pdf(), name) == "unsupported_file_type"

    def test_unsupported_message_names_the_supported_formats(self, tmp_path: Path) -> None:
        message = message_of(tmp_path, b"hello", "notes.txt")
        assert "'.txt'" in message
        assert "PDF (.pdf)" in message
        assert "Word (.docx)" in message

    def test_legacy_doc_gets_a_conversion_hint(self, tmp_path: Path) -> None:
        assert "save the document as .docx" in message_of(tmp_path, OLE_HEADER, "old.doc")

    def test_missing_extension_is_explained(self, tmp_path: Path) -> None:
        message = message_of(tmp_path, make_pdf(), "srs")
        assert "no extension" in message

    def test_empty_file(self, tmp_path: Path) -> None:
        assert code_of(tmp_path, b"", "srs.pdf") == "empty_file"

    def test_random_bytes_named_pdf_are_corrupted(self, tmp_path: Path) -> None:
        assert (
            code_of(tmp_path, b"this is definitely not a pdf" * 20, "srs.pdf") == "corrupted_file"
        )

    def test_truncated_pdf_is_corrupted(self, tmp_path: Path) -> None:
        pdf = make_pdf()
        truncated = pdf[: len(pdf) // 2]
        assert b"%%EOF" not in truncated[-2048:]
        assert code_of(tmp_path, truncated, "srs.pdf") == "corrupted_file"

    def test_docx_named_pdf_is_a_mismatch(self, tmp_path: Path) -> None:
        message = message_of(tmp_path, make_docx("x"), "srs.pdf")
        assert "ZIP-based" in message
        assert code_of(tmp_path, make_docx("x"), "srs.pdf") == "file_content_mismatch"

    def test_pdf_named_docx_is_a_mismatch(self, tmp_path: Path) -> None:
        assert code_of(tmp_path, make_pdf(), "srs.docx") == "file_content_mismatch"

    def test_ole_container_named_docx_explains_password_protection(self, tmp_path: Path) -> None:
        message = message_of(tmp_path, OLE_HEADER, "srs.docx")
        assert "password-protected" in message

    def test_garbage_named_docx_is_corrupted(self, tmp_path: Path) -> None:
        assert code_of(tmp_path, b"not a zip at all", "srs.docx") == "corrupted_file"

    def test_zip_magic_but_broken_archive_is_corrupted(self, tmp_path: Path) -> None:
        assert code_of(tmp_path, b"PK\x03\x04" + b"\xff" * 200, "srs.docx") == "corrupted_file"

    def test_arbitrary_zip_named_docx_is_not_a_word_document(self, tmp_path: Path) -> None:
        archive = make_zip({"hello.txt": b"hi"})
        assert code_of(tmp_path, archive, "srs.docx") == "file_content_mismatch"

    def test_zip_bomb_is_rejected(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(upload_validation, "MAX_DOCX_UNCOMPRESSED_BYTES", 1024 * 1024)
        bomb = make_zip(
            {
                "[Content_Types].xml": b"<Types/>",
                "word/document.xml": b"<w:document/>",
                "word/padding.bin": b"\x00" * (2 * 1024 * 1024),  # compresses to a few KB
            }
        )
        assert len(bomb) < 100 * 1024
        assert code_of(tmp_path, bomb, "srs.docx") == "unsafe_file"

    def test_too_many_entries_is_rejected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(upload_validation, "MAX_DOCX_ENTRIES", 3)
        many = make_zip({f"f{i}.xml": b"x" for i in range(10)})
        assert code_of(tmp_path, many, "srs.docx") == "unsafe_file"

    def test_error_carries_http_400(self, tmp_path: Path) -> None:
        with pytest.raises(BadRequestError) as caught:
            validate_upload(write(tmp_path, b""), "srs.pdf")
        assert caught.value.status_code == 400
