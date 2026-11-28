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


def _write(path, items, size=11):
    """Write one page from (x, y, text) items placed one by one, the way PDF writers lay
    out borderless tables."""
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    for x, y, text in items:
        page.insert_text((x, y), text, fontsize=size)
    doc.save(str(path))
    doc.close()
    return str(path)


class TestLayout:
    """Reading order rebuilt from line positions: borderless tables, wrapped headings."""

    def test_key_value_rows_become_table_rows(self, tmp_path):
        path = _write(
            tmp_path / "kv.pdf",
            [
                (60, 200, "Description"),
                (160, 194, "Create an account and authenticate"),
                (160, 206, "securely."),
                (60, 230, "Input"),
                (160, 230, "Credentials, profile, consent"),
            ],
        )
        assert PDFParser().parse(path)[0].text == (
            "Description | Create an account and authenticate securely.\n\n"
            "Input | Credentials, profile, consent"
        )

    def test_wrapped_id_cell_is_rejoined(self, tmp_path):
        path = _write(
            tmp_path / "nfr.pdf",
            [
                (60, 200, "NU-"),
                (60, 212, "NFR-"),
                (60, 224, "01"),
                (120, 212, "Usability"),
                (220, 206, "Forms should be clear and"),
                (220, 218, "easy to learn."),
                (420, 212, "High"),
            ],
        )
        assert PDFParser().parse(path)[0].text == (
            "NU-NFR-01 | Usability | Forms should be clear and easy to learn. | High"
        )

    def test_cell_wrapped_below_a_loosely_spaced_row_stays_in_its_cell(self, tmp_path):
        path = _write(
            tmp_path / "loose.pdf",
            [
                (60, 200, "Backend"),
                (140, 200, "Bansil"),
                (220, 200, "Ingestion and authoring: extraction,"),
                (220, 214, "owners and change requests"),
                (60, 245, "Backend"),
                (140, 245, "Heet"),
                (220, 245, "Embeddings and retrieval"),
            ],
        )
        assert PDFParser().parse(path)[0].text == (
            "Backend | Bansil | Ingestion and authoring: extraction, owners and change requests"
            "\n\nBackend | Heet | Embeddings and retrieval"
        )

    def test_prose_is_not_split_into_cells(self, tmp_path):
        path = _write(
            tmp_path / "prose.pdf",
            [
                (60, 200, "The system shall let members reserve items for up to two days."),
                (60, 214, "Reservations expire automatically."),
            ],
        )
        assert "|" not in PDFParser().parse(path)[0].text

    def test_wrapped_large_heading_is_one_line(self, tmp_path):
        path = tmp_path / "heading.pdf"
        doc = pymupdf.open()
        page = doc.new_page(width=595, height=842)
        page.insert_text((60, 150), "1. Citizen (Normal User) functional", fontsize=24)
        page.insert_text((60, 178), "requirements", fontsize=24)
        page.insert_text(
            (60, 230), "Body text, which sets the usual font size of the page.", fontsize=11
        )
        doc.save(str(path))
        doc.close()
        assert (
            PDFParser()
            .parse(str(path))[0]
            .text.startswith("1. Citizen (Normal User) functional requirements\n\n")
        )
