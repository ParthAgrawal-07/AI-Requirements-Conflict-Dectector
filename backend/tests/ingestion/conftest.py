"""
Shared pytest fixtures for ingestion tests.

Creates small deterministic PDF and DOCX test files on the fly
so tests don't depend on external sample documents.
"""

import pytest
import pymupdf  # PyMuPDF
import docx
import tempfile
import os


@pytest.fixture
def sample_pdf(tmp_path):
    """Create a minimal PDF with two requirement lines on page 1."""
    path = tmp_path / "sample.pdf"

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text(
        (50, 50),
        "REQ-001: The system shall allow user login.\n"
        "REQ-002: The system shall support logout.",
    )
    doc.save(str(path))
    doc.close()

    return str(path)


@pytest.fixture
def sample_pdf_multipage(tmp_path):
    """Create a PDF with content on page 1, empty page 2, content on page 3."""
    path = tmp_path / "multipage.pdf"

    doc = pymupdf.open()

    # Page 1 — has content
    page1 = doc.new_page()
    page1.insert_text((50, 50), "FR-1: Functional requirement one.")

    # Page 2 — intentionally empty
    doc.new_page()

    # Page 3 — has content
    page3 = doc.new_page()
    page3.insert_text((50, 50), "NFR-01: Non-functional requirement.")

    doc.save(str(path))
    doc.close()

    return str(path)


@pytest.fixture
def sample_docx(tmp_path):
    """Create a minimal DOCX with one requirement paragraph."""
    path = tmp_path / "sample.docx"

    doc = docx.Document()
    doc.add_paragraph("REQ-003: The system shall export reports.")
    doc.save(str(path))

    return str(path)


@pytest.fixture
def sample_docx_multi(tmp_path):
    """Create a DOCX with mixed content: requirements, empty paras, and plain text."""
    path = tmp_path / "multi.docx"

    doc = docx.Document()
    doc.add_paragraph("FR-1: First functional requirement.")
    doc.add_paragraph("")  # empty paragraph — should be skipped
    doc.add_paragraph("This is an introductory paragraph with no ID.")
    doc.add_paragraph("NFR-02: Performance requirement.")
    doc.save(str(path))

    return str(path)
