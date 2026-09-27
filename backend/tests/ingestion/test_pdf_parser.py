"""Tests for PDFParser."""

import pytest
from app.ingestion.parsers.pdf_parser import PDFParser
from app.ingestion.models import RawSegment


class TestPDFParser:
    """Tests for the PDF parser."""

    def test_returns_list_of_raw_segments(self, sample_pdf):
        parser = PDFParser()
        segments = parser.parse(sample_pdf)

        assert isinstance(segments, list)
        assert len(segments) > 0
        assert all(isinstance(s, RawSegment) for s in segments)

    def test_extracts_text_content(self, sample_pdf):
        parser = PDFParser()
        segments = parser.parse(sample_pdf)

        assert segments[0].text  # non-empty
        assert "REQ-001" in segments[0].text
        assert "REQ-002" in segments[0].text

    def test_preserves_page_number(self, sample_pdf):
        parser = PDFParser()
        segments = parser.parse(sample_pdf)

        assert segments[0].page_or_paragraph == 1  # 1-based

    def test_preserves_source_document(self, sample_pdf):
        parser = PDFParser()
        segments = parser.parse(sample_pdf)

        assert segments[0].source_document == "sample.pdf"

    def test_preserves_order_index(self, sample_pdf):
        parser = PDFParser()
        segments = parser.parse(sample_pdf)

        assert segments[0].order_index == 0

    def test_skips_empty_pages(self, sample_pdf_multipage):
        parser = PDFParser()
        segments = parser.parse(sample_pdf_multipage)

        # 3 pages, but page 2 is empty → only 2 segments
        assert len(segments) == 2
        assert segments[0].page_or_paragraph == 1
        assert segments[1].page_or_paragraph == 3  # page 2 was skipped
        assert segments[0].order_index == 0
        assert segments[1].order_index == 1

    def test_rejects_non_pdf(self, tmp_path):
        fake_file = tmp_path / "document.txt"
        fake_file.write_text("hello")

        parser = PDFParser()
        with pytest.raises(ValueError, match="Unsupported file format"):
            parser.parse(str(fake_file))

    def test_rejects_nonexistent_file(self):
        parser = PDFParser()
        with pytest.raises(FileNotFoundError, match="File not found"):
            parser.parse("/nonexistent/path/document.pdf")
