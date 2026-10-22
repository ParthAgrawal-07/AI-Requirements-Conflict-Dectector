"""Tests for PDFParser."""

import pymupdf
import pytest

from app.ingestion.errors import DocumentParseError
from app.ingestion.models import RawSegment
from app.ingestion.parsers.pdf_parser import PDFParser


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

    def test_corrupted_pdf_raises_parse_error(self, tmp_path):
        bad = tmp_path / "broken.pdf"
        bad.write_bytes(b"not a pdf")

        with pytest.raises(DocumentParseError, match="corrupted"):
            PDFParser().parse(str(bad))

    def test_encrypted_pdf_raises_parse_error(self, tmp_path):
        path = tmp_path / "locked.pdf"
        doc = pymupdf.open()
        doc.new_page().insert_text((50, 50), "REQ-001: Secret.")
        doc.save(
            str(path),
            encryption=pymupdf.PDF_ENCRYPT_AES_256,
            owner_pw="owner",
            user_pw="user",
        )
        doc.close()

        with pytest.raises(DocumentParseError, match="password-protected"):
            PDFParser().parse(str(path))


class TestHeaderFooterRemoval:
    def _build(self, tmp_path, bodies, *, header=None, footer=None):
        path = tmp_path / "hf.pdf"
        doc = pymupdf.open()
        for n, body in enumerate(bodies, start=1):
            page = doc.new_page(width=595, height=842)
            if header:
                page.insert_text((50, 30), header, fontsize=8)
            if footer:
                page.insert_text((270, 820), footer.format(n=n), fontsize=8)
            page.insert_text((50, 300), body)
        doc.save(str(path))
        doc.close()
        return str(path)

    def test_repeated_header_and_page_numbers_removed(self, tmp_path):
        path = self._build(
            tmp_path,
            ["REQ-1: One shall work.", "REQ-2: Two shall work."],
            header="ACME Corp - Confidential",
            footer="Page {n} of 2",
        )
        texts = [s.text for s in PDFParser().parse(path)]
        assert texts == ["REQ-1: One shall work.", "REQ-2: Two shall work."]

    def test_lone_page_number_removed_on_single_page(self, tmp_path):
        path = self._build(tmp_path, ["REQ-1: One shall work."], footer="{n}")
        assert [s.text for s in PDFParser().parse(path)] == ["REQ-1: One shall work."]

    def test_margin_text_on_one_page_only_is_kept(self, tmp_path):
        path = self._build(tmp_path, ["Body one.", "Body two."])
        doc = pymupdf.open(path)
        doc[0].insert_text((50, 30), "Draft title")
        doc.saveIncr()
        doc.close()
        assert "Draft title" in PDFParser().parse(path)[0].text

    def test_paragraph_blocks_separated_by_blank_line(self, sample_pdf_multipage, tmp_path):
        path = tmp_path / "blocks.pdf"
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((50, 300), "First paragraph.")
        page.insert_text((50, 400), "Second paragraph.")
        doc.save(str(path))
        doc.close()
        assert PDFParser().parse(str(path))[0].text == "First paragraph.\n\nSecond paragraph."
