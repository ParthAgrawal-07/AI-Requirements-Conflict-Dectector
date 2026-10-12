"""Tests for the ingestion pipeline (end-to-end)."""

import shutil

import pymupdf
import pytest

from app.ingestion.errors import DocumentParseError
from app.ingestion.models import Requirement
from app.ingestion.pipeline import ingest


class TestPipeline:
    """End-to-end tests for pipeline.ingest()."""

    def test_pdf_end_to_end(self, sample_pdf):
        """Full pipeline: PDF → RawSegments → Requirements."""
        reqs = ingest(sample_pdf)

        assert len(reqs) > 0
        assert all(isinstance(r, Requirement) for r in reqs)
        assert reqs[0].id == "REQ-001"

    def test_docx_end_to_end(self, sample_docx):
        """Full pipeline: DOCX → RawSegments → Requirements."""
        reqs = ingest(sample_docx)

        assert len(reqs) > 0
        assert all(isinstance(r, Requirement) for r in reqs)
        assert reqs[0].id == "REQ-003"

    def test_rejects_unsupported_txt(self, tmp_path):
        fake = tmp_path / "file.txt"
        fake.write_text("hello")

        with pytest.raises(ValueError, match="Unsupported file format"):
            ingest(str(fake))

    def test_rejects_unsupported_doc(self, tmp_path):
        """Legacy .doc should fail with a helpful hint."""
        fake = tmp_path / "legacy.doc"
        fake.write_bytes(b"\x00" * 10)

        with pytest.raises(ValueError, match="not supported"):
            ingest(str(fake))

    def test_rejects_nonexistent_file(self):
        with pytest.raises(FileNotFoundError, match="File not found"):
            ingest("/nonexistent/path/document.pdf")

    def test_case_insensitive_extension(self, sample_pdf, tmp_path):
        """Pipeline should handle .PDF (uppercase) extensions."""
        upper_path = tmp_path / "DOCUMENT.PDF"
        shutil.copy(sample_pdf, str(upper_path))

        reqs = ingest(str(upper_path))
        assert len(reqs) > 0

    def test_extracted_at_is_set(self, sample_pdf):
        """Every requirement should have an extracted_at timestamp."""
        reqs = ingest(sample_pdf)

        for r in reqs:
            assert r.extracted_at is not None

    def test_rejects_pdf_without_text(self, tmp_path):
        """Scanned/blank PDFs should fail loudly, not return an empty list."""
        path = tmp_path / "scanned.pdf"
        doc = pymupdf.open()
        doc.new_page()
        doc.save(str(path))
        doc.close()

        with pytest.raises(DocumentParseError, match="No extractable text"):
            ingest(str(path))

    def test_docx_table_requirements_end_to_end(self, sample_docx_structured):
        reqs = ingest(sample_docx_structured)

        assert [r.id for r in reqs] == ["REQ-001", "REQ-010", "REQ-011"]
        assert reqs[1].section_heading == "3. Functional Requirements"
        assert reqs[1].location.startswith("paragraph ")
