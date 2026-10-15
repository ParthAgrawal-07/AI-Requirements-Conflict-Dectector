"""End-to-end extraction on realistic SRS documents (US-02 acceptance criteria)."""

from app.ingestion.pipeline import ingest_document


class TestRealisticPDF:
    def test_extracts_exactly_the_requirements(self, realistic_srs_pdf):
        result = ingest_document(realistic_srs_pdf)

        assert [r.id for r in result.requirements] == [
            "REQ-001",
            "REQ-002",
            "REQ-003",
            "UNKNOWN-2-0",
            "UNKNOWN-2-1",
            "REQ-004",
            "NFR-01",
            "UNKNOWN-3-0",
            "REQ-003",
        ]

    def test_wrapped_lines_and_page_break_are_rejoined(self, realistic_srs_pdf):
        reqs = {
            r.raw_text.split(":")[0]: r for r in ingest_document(realistic_srs_pdf).requirements
        }

        assert reqs["REQ-001"].raw_text.endswith("within two seconds for up to 10,000 records.")
        assert reqs["REQ-004"].raw_text.endswith(
            "unless the member has disabled reminders in their profile settings."
        )
        assert reqs["REQ-004"].location == "page 2"  # where it starts

    def test_list_items_stay_with_their_lead_in(self, realistic_srs_pdf):
        req = ingest_document(realistic_srs_pdf).requirements[1]

        assert req.raw_text == (
            "REQ-002: The system shall support the following notification channels:\n- Email\n- SMS"
        )

    def test_headers_footers_and_toc_are_excluded(self, realistic_srs_pdf):
        result = ingest_document(realistic_srs_pdf)
        everything = " ".join(r.raw_text for r in result.requirements)

        assert "SRS v1.0" not in everything
        assert "Page 2 of 3" not in everything
        assert "...." not in everything
        assert sum(e.reason == "toc" for e in result.excluded) == 4

    def test_section_headings_attached(self, realistic_srs_pdf):
        reqs = ingest_document(realistic_srs_pdf).requirements

        assert reqs[0].section_heading == "2 Functional Requirements"
        assert reqs[-1].section_heading == "3 Non-Functional Requirements"

    def test_uncertain_items_flagged_not_dropped(self, realistic_srs_pdf):
        reqs = ingest_document(realistic_srs_pdf).requirements
        flagged = {r.raw_text: r.review_reasons for r in reqs if r.needs_review}

        assert "The user interface will be easy to use." in flagged  # weak modal, no ID
        dupes = [t for t in flagged if t.startswith("REQ-003")]
        assert len(dupes) == 2

    def test_intro_narrative_excluded(self, realistic_srs_pdf):
        result = ingest_document(realistic_srs_pdf)

        assert any(
            e.reason == "non_requirement_section" and e.text.startswith("This document describes")
            for e in result.excluded
        )


class TestRealisticDOCX:
    def test_extracts_exactly_the_requirements(self, realistic_srs_docx):
        result = ingest_document(realistic_srs_docx)

        assert [(r.source_req_id, r.raw_text) for r in result.requirements] == [
            (
                "FR-1",
                "FR-1: The system shall let members reserve items. "
                "Reservations expire after 48 hours.",
            ),
            ("FR-2", "FR-2: The system shall export reports in these formats:\nPDF\nCSV"),
            (None, "The system shall lock an account after five failed login attempts."),
            (None, "Fines are calculated daily."),
            ("FR-10", "FR-10 | The system shall calculate fines daily. | High"),
            ("FR-11", "FR-11 | Fines must not exceed the item price. | Medium"),
            ("NFR-1", "NFR-1: Pages should load within 2 seconds."),
        ]

    def test_word_list_items_are_not_headings(self, realistic_srs_docx):
        reqs = ingest_document(realistic_srs_docx).requirements

        assert reqs[2].section_heading == "2 Functional Requirements"

    def test_modal_less_statement_in_requirements_section_is_flagged(self, realistic_srs_docx):
        reqs = ingest_document(realistic_srs_docx).requirements

        assert reqs[3].needs_review
        assert not any(r.needs_review for r in reqs[:3] + reqs[4:])

    def test_glossary_intro_and_table_header_excluded(self, realistic_srs_docx):
        excluded = {e.text: e.reason for e in ingest_document(realistic_srs_docx).excluded}

        assert excluded == {
            "This SRS describes the Online Library System.": "non_requirement_section",
            "Member: a registered library user.": "non_requirement_section",
            "ID | Requirement | Priority": "fragment",
        }
