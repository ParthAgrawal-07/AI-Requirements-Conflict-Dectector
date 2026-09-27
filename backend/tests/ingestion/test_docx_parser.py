"""Tests for DOCXParser."""

import pytest
from app.ingestion.parsers.docx_parser import DOCXParser
from app.ingestion.models import RawSegment


class TestDOCXParser:
    """Tests for the DOCX parser."""

    def test_returns_list_of_raw_segments(self, sample_docx):
        parser = DOCXParser()
        segments = parser.parse(sample_docx)

        assert isinstance(segments, list)
        assert len(segments) > 0
        assert all(isinstance(s, RawSegment) for s in segments)

    def test_extracts_text_content(self, sample_docx):
        parser = DOCXParser()
        segments = parser.parse(sample_docx)

        assert segments[0].text  # non-empty
        assert "REQ-003" in segments[0].text

    def test_preserves_paragraph_index(self, sample_docx):
        parser = DOCXParser()
        segments = parser.parse(sample_docx)

        assert segments[0].page_or_paragraph == 1  # 1-based

    def test_preserves_source_document(self, sample_docx):
        parser = DOCXParser()
        segments = parser.parse(sample_docx)

        assert segments[0].source_document == "sample.docx"

    def test_skips_empty_paragraphs(self, sample_docx_multi):
        parser = DOCXParser()
        segments = parser.parse(sample_docx_multi)

        # 4 paragraphs, but 1 is empty → 3 segments
        assert len(segments) == 3
        texts = [s.text for s in segments]
        assert any("FR-1" in t for t in texts)
        assert any("NFR-02" in t for t in texts)
        # Ensure order_index is sequential
        assert [s.order_index for s in segments] == [0, 1, 2]

    def test_rejects_doc_format(self, tmp_path):
        """Explicitly test that .doc is rejected with a helpful message."""
        fake_file = tmp_path / "legacy.doc"
        fake_file.write_bytes(b"\x00" * 10)

        parser = DOCXParser()
        with pytest.raises(ValueError, match="not supported"):
            parser.parse(str(fake_file))

    def test_rejects_txt_format(self, tmp_path):
        fake_file = tmp_path / "notes.txt"
        fake_file.write_text("hello")

        parser = DOCXParser()
        with pytest.raises(ValueError, match="Unsupported file format"):
            parser.parse(str(fake_file))

    def test_rejects_nonexistent_file(self):
        parser = DOCXParser()
        with pytest.raises(FileNotFoundError, match="File not found"):
            parser.parse("/nonexistent/path/document.docx")
