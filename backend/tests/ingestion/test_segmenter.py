"""Tests for the Segmenter."""

from app.ingestion.models import RawSegment, Requirement
from app.ingestion.segmentation.segmenter import Segmenter


class TestSegmenter:
    """Tests for Sprint 0 requirement segmentation."""

    def test_splits_multiple_requirements(self):
        """Two requirements on separate lines should produce two Requirement objects."""
        raw_segments = [
            RawSegment(
                text="REQ-001: The user shall log in.\nREQ-002: The user shall log out.",
                source_document="test.pdf",
                page_or_paragraph=1,
                location_type="page",
                order_index=0,
            )
        ]

        segmenter = Segmenter()
        requirements = segmenter.segment(raw_segments)

        req_ids = [r.id for r in requirements]
        assert "REQ-001" in req_ids
        assert "REQ-002" in req_ids
        assert requirements[0].raw_text == "REQ-001: The user shall log in."
        assert requirements[1].raw_text == "REQ-002: The user shall log out."

    def test_extracts_correct_ids(self):
        """Verify various ID formats are extracted correctly."""
        raw_segments = [
            RawSegment(
                text="FR-1: Feature one.\nFR-1.2: Sub-feature.\nNFR-01: Performance.",
                source_document="spec.docx",
                page_or_paragraph=1,
                location_type="page",
                order_index=0,
            )
        ]

        segmenter = Segmenter()
        requirements = segmenter.segment(raw_segments)

        ids = [r.id for r in requirements]
        assert ids == ["FR-1", "FR-1.2", "NFR-01"]

    def test_fallback_id_for_unrecognized_lines(self):
        """Lines without a requirement ID get a deterministic fallback ID."""
        raw_segments = [
            RawSegment(
                text="This is an intro paragraph.",
                source_document="test.pdf",
                page_or_paragraph=2,
                location_type="page",
                order_index=1,
            )
        ]

        segmenter = Segmenter()
        requirements = segmenter.segment(raw_segments)

        assert len(requirements) == 1
        assert requirements[0].id == "UNKNOWN-2-0"
        assert requirements[0].raw_text == "This is an intro paragraph."

    def test_mixed_recognized_and_unrecognized(self):
        """Segments with both requirement IDs and plain text produce correct mix."""
        raw_segments = [
            RawSegment(
                text="REQ-001: The user shall log in.\nREQ-002: The user shall log out.",
                source_document="test.pdf",
                page_or_paragraph=1,
                location_type="page",
                order_index=0,
            ),
            RawSegment(
                text="This is an intro paragraph.",
                source_document="test.pdf",
                page_or_paragraph=2,
                location_type="page",
                order_index=1,
            ),
        ]

        segmenter = Segmenter()
        requirements = segmenter.segment(raw_segments)

        assert len(requirements) == 3
        assert requirements[0].id == "REQ-001"
        assert requirements[1].id == "REQ-002"
        assert requirements[2].id.startswith("UNKNOWN-2")

    def test_skips_empty_lines(self):
        """Empty lines within a segment should be silently skipped."""
        raw_segments = [
            RawSegment(
                text="REQ-001: First.\n\n\nREQ-002: Second.",
                source_document="test.pdf",
                page_or_paragraph=1,
                location_type="page",
                order_index=0,
            )
        ]

        segmenter = Segmenter()
        requirements = segmenter.segment(raw_segments)

        assert len(requirements) == 2

    def test_preserves_location_and_source(self):
        """Verify that location and source_document are correctly set."""
        raw_segments = [
            RawSegment(
                text="REQ-010: Something.",
                source_document="my_srs.pdf",
                page_or_paragraph=5,
                location_type="page",
                order_index=4,
            )
        ]

        segmenter = Segmenter()
        requirements = segmenter.segment(raw_segments)

        assert requirements[0].source_document == "my_srs.pdf"
        assert requirements[0].location == "page 5"

    def test_returns_requirement_type(self):
        """All items in the output must be Requirement instances."""
        raw_segments = [
            RawSegment(
                text="REQ-001: Test.",
                source_document="test.pdf",
                page_or_paragraph=1,
                location_type="page",
                order_index=0,
            )
        ]

        segmenter = Segmenter()
        requirements = segmenter.segment(raw_segments)

        assert all(isinstance(r, Requirement) for r in requirements)

    def test_empty_input_returns_empty_list(self):
        """An empty list of segments should return an empty list."""
        segmenter = Segmenter()
        requirements = segmenter.segment([])

        assert requirements == []

    def test_cross_reference_is_not_treated_as_own_id(self):
        """An ID mentioned mid-sentence is a reference, not the line's own ID."""
        raw_segments = [
            RawSegment(
                text="This statement contradicts FR-1 above.",
                source_document="spec.docx",
                page_or_paragraph=3,
                location_type="paragraph",
                order_index=0,
            )
        ]

        requirements = Segmenter().segment(raw_segments)

        assert requirements[0].id == "UNKNOWN-3-0"
        assert requirements[0].source_req_id is None
        assert requirements[0].location == "paragraph 3"

    def test_leading_bullets_and_nested_ids(self):
        """IDs after bullets/brackets are found, and multi-level IDs are kept whole."""
        raw_segments = [
            RawSegment(
                text="\u2022 FR-1.2.3: Nested.\n[DR-03] Data rule.\n- REQ-7 Dash bullet.",
                source_document="spec.pdf",
                page_or_paragraph=1,
                location_type="page",
                order_index=0,
            )
        ]

        requirements = Segmenter().segment(raw_segments)

        assert [r.id for r in requirements] == ["FR-1.2.3", "DR-03", "REQ-7"]
        assert all(r.source_req_id == r.id for r in requirements)

    def test_carries_section_heading(self):
        raw_segments = [
            RawSegment(
                text="REQ-001: Something.",
                source_document="spec.docx",
                page_or_paragraph=2,
                location_type="paragraph",
                section_heading="3. Functional Requirements",
                order_index=0,
            )
        ]

        requirements = Segmenter().segment(raw_segments)

        assert requirements[0].section_heading == "3. Functional Requirements"


def _pages(*texts: str) -> list[RawSegment]:
    return [
        RawSegment(
            text=t,
            source_document="srs.pdf",
            page_or_paragraph=i + 1,
            location_type="page",
            order_index=i,
        )
        for i, t in enumerate(texts)
    ]


def _paragraphs(*texts: str, list_items: tuple[int, ...] = ()) -> list[RawSegment]:
    return [
        RawSegment(
            text=t,
            source_document="srs.docx",
            page_or_paragraph=i + 1,
            location_type="paragraph",
            is_list_item=i in list_items,
            order_index=i,
        )
        for i, t in enumerate(texts)
    ]


def _texts(segments: list[RawSegment]) -> list[str]:
    return [r.raw_text for r in Segmenter().segment(segments)]


class TestGrouping:
    """Sprint 1: how lines are grouped into requirement units."""

    def test_wrapped_lines_are_joined(self):
        assert _texts(_pages("REQ-1: The system shall\nrespond within two seconds.")) == [
            "REQ-1: The system shall respond within two seconds."
        ]

    def test_hyphenated_line_break_is_joined_without_space(self):
        assert _texts(_pages("REQ-1: The system shall support real-\ntime updates.")) == [
            "REQ-1: The system shall support real-time updates."
        ]

    def test_new_paragraph_starts_new_unit(self):
        texts = _texts(_pages("REQ-1: The system shall log in.\n\nThe system shall log out."))
        assert texts == ["REQ-1: The system shall log in.", "The system shall log out."]

    def test_sentence_cut_by_page_break_continues(self):
        reqs = Segmenter().segment(
            _pages("REQ-1: The system shall send reminders unless", "disabled by the user.")
        )
        assert [r.raw_text for r in reqs] == [
            "REQ-1: The system shall send reminders unless disabled by the user."
        ]
        assert reqs[0].location == "page 1"

    def test_complete_sentence_does_not_continue_across_page(self):
        texts = _texts(_pages("REQ-1: The system shall log in.", "The system shall log out."))
        assert len(texts) == 2

    def test_bare_id_joins_following_block(self):
        texts = _texts(_pages("REQ-001\n\nThe system shall export reports."))
        assert texts == ["REQ-001 The system shall export reports."]

    def test_list_after_lead_in_stays_together(self):
        texts = _texts(_pages("REQ-2: The system shall support:\n\n• Email\n\n• SMS"))
        assert texts == ["REQ-2: The system shall support:\n• Email\n• SMS"]

    def test_list_without_lead_in_is_split(self):
        texts = _texts(_pages("• The system shall log in.\n• The system shall log out."))
        assert len(texts) == 2

    def test_docx_list_paragraphs_join_lead_in(self):
        texts = _texts(
            _paragraphs("FR-2: Reports shall be exported as:", "PDF", "CSV", list_items=(1, 2))
        )
        assert texts == ["FR-2: Reports shall be exported as:\nPDF\nCSV"]

    def test_headings_are_context_not_requirements(self):
        reqs = Segmenter().segment(
            _pages(
                "3.2 Functional Requirements\n\nThe system shall log in.\n\nSECURITY\n\n"
                "Passwords shall be hashed."
            )
        )
        assert [(r.section_heading, r.raw_text) for r in reqs] == [
            ("3.2 Functional Requirements", "The system shall log in."),
            ("SECURITY", "Passwords shall be hashed."),
        ]

    def test_numbered_heading_sharing_a_block_with_an_id(self):
        reqs = Segmenter().segment(_pages("2 Functional Requirements\nREQ-1: It shall work."))
        assert [(r.section_heading, r.raw_text) for r in reqs] == [
            ("2 Functional Requirements", "REQ-1: It shall work.")
        ]

    def test_toc_lines_excluded(self):
        result = Segmenter().run(
            _pages(
                "Contents\n\n1 Introduction 2\n\n2 Requirements 3",
                "Overview ......... 4\n\n2 Requirements\n\nThe system shall work.",
            )
        )
        assert [r.raw_text for r in result.requirements] == ["The system shall work."]
        assert [e.reason for e in result.excluded] == ["toc"] * 4


class TestClassification:
    """Sprint 1: deciding what is a requirement, and what needs review."""

    def test_id_less_paragraph_split_into_requirement_sentences(self):
        texts = _texts(
            _pages("The system shall support PDF, e.g. version 1.7. It shall reject others.")
        )
        assert texts == [
            "The system shall support PDF, e.g. version 1.7.",
            "It shall reject others.",
        ]

    def test_numbered_item_number_is_not_split_off(self):
        texts = _texts(_pages("1. The user shall log in.\n2. The user shall log out."))
        assert texts == ["1. The user shall log in.", "2. The user shall log out."]

    def test_context_sentence_stays_with_id_requirement(self):
        reqs = Segmenter().segment(
            _pages("REQ-3: Members must not borrow over five items. The limit applies everywhere.")
        )
        assert len(reqs) == 1
        assert not reqs[0].needs_review

    def test_several_shall_sentences_under_one_id_flagged(self):
        [req] = Segmenter().segment(
            _pages("REQ-9: The system shall log logins. The system shall email receipts.")
        )
        assert req.needs_review
        assert "more than one requirement" in req.review_reasons[0]

    def test_bare_id_without_text_flagged(self):
        [req] = Segmenter().segment(_pages("REQ-9:"))
        assert req.needs_review
        assert "no requirement text" in req.review_reasons[0]

    def test_weak_modal_flagged(self):
        [req] = Segmenter().segment(_pages("The interface will be easy to use."))
        assert req.needs_review
        assert "weaker modal" in req.review_reasons[0]

    def test_duplicate_ids_flagged(self):
        reqs = Segmenter().segment(_pages("REQ-1: It shall do X.\n\nREQ-1: It shall do Y."))
        assert all(r.needs_review for r in reqs)
        assert "appears 2 times" in reqs[0].review_reasons[-1]

    def test_narrative_in_intro_excluded_but_shall_in_intro_flagged(self):
        result = Segmenter().run(
            _pages("1.1 Purpose\n\nThis document describes the system.\n\nReaders must know UML.")
        )
        assert [e.text for e in result.excluded] == ["This document describes the system."]
        [req] = result.requirements
        assert req.raw_text == "Readers must know UML."
        assert "non-requirement section" in req.review_reasons[0]

    def test_short_fragments_excluded(self):
        result = Segmenter().run(_pages("ID | Requirement | Priority"))
        assert result.requirements == []
        assert result.excluded[0].reason == "fragment"

    def test_wording_is_preserved_verbatim(self):
        text = "The  system shall   keep spacing. It shall also keep CASE."
        reqs = Segmenter().segment(_pages(text))
        assert " ".join(r.raw_text for r in reqs) == text

    def test_order_index_is_sequential(self):
        reqs = Segmenter().segment(_pages("REQ-1: A shall work.\n\nREQ-2: B shall work."))
        assert [r.order_index for r in reqs] == [0, 1]


class TestReviewRegressions:
    """Bugs found while reviewing the Sprint 1 segmenter."""

    def test_list_at_page_end_does_not_swallow_next_page(self):
        texts = _texts(
            _pages("REQ-2: Channels shall include:\n- Email\n- SMS", "The system shall log out.")
        )
        assert texts == [
            "REQ-2: Channels shall include:\n- Email\n- SMS",
            "The system shall log out.",
        ]

    def test_requirement_right_after_toc_is_kept(self):
        texts = _texts(_pages("Contents\n\n1 Introduction 2\n\nREQ-1: The timeout shall be 30"))
        assert texts == ["REQ-1: The timeout shall be 30"]

    def test_figure_caption_is_not_a_heading(self):
        reqs = Segmenter().segment(
            _pages("2 Functional Requirements\n\nFigure 3 Login Flow\n\nThe system shall log in.")
        )
        assert reqs[-1].section_heading == "2 Functional Requirements"

    def test_requirement_list_item_is_not_absorbed_by_previous_list(self):
        texts = _texts(
            _paragraphs(
                "FR-2: Reports shall be exported as:",
                "PDF",
                "The system shall log every export.",
                list_items=(1, 2),
            )
        )
        assert texts == [
            "FR-2: Reports shall be exported as:\nPDF",
            "The system shall log every export.",
        ]


class TestPrintedIds:
    """FR-04: whatever ID the document prints is kept exactly as written."""

    def test_project_specific_prefixes_are_kept(self):
        reqs = Segmenter().segment(
            _pages(
                "UC-07: The customer shall reset a password.\n"
                "SEC-3: Sessions shall expire after 15 minutes.\n"
                "PERF_01: Search shall answer within 2 seconds."
            )
        )
        assert [r.source_req_id for r in reqs] == ["UC-07", "SEC-3", "PERF_01"]

    def test_multi_part_prefixes_are_kept_whole(self):
        reqs = Segmenter().segment(
            _pages("FR-AUTH-01: Users shall log in.\nREQ-SEC-001: Data shall be encrypted.")
        )
        assert [r.source_req_id for r in reqs] == ["FR-AUTH-01", "REQ-SEC-001"]

    def test_standard_and_encoding_names_are_not_ids(self):
        reqs = Segmenter().segment(
            _paragraphs(
                "ISO-27001 controls shall apply to all data stores.",
                "UTF-8 shall be used for every export.",
                "TLS-1.2 or later must protect all traffic.",
            )
        )
        assert [r.source_req_id for r in reqs] == [None, None, None]
        assert all(r.id.startswith("UNKNOWN-") for r in reqs)

    def test_a_word_glued_to_the_number_is_not_an_id(self):
        reqs = Segmenter().segment(_paragraphs("UC-1a covers the happy path and shall pass."))
        assert reqs[0].source_req_id is None

    def test_items_without_a_printed_id_are_stored_without_one(self):
        reqs = Segmenter().segment(_paragraphs("The system shall export reports as PDF."))
        assert reqs[0].source_req_id is None


class TestSections:
    """Headings and the verbatim text under them, for the project context (FR-104, FR-105)."""

    def test_each_heading_collects_the_text_under_it(self):
        result = Segmenter().run(
            _pages(
                "1.1 Purpose\n\nThis document describes the\nmobile banking app.\n\n"
                "It covers transfers.\n\n"
                "3 Functional Requirements\n\nREQ-001: The app shall allow login."
            )
        )
        assert [(s.heading, s.body) for s in result.sections] == [
            (
                "1.1 Purpose",
                "This document describes the\nmobile banking app.\n\nIt covers transfers.",
            ),
            ("3 Functional Requirements", "REQ-001: The app shall allow login."),
        ]
        assert [s.order_index for s in result.sections] == [0, 1]
        assert result.sections[0].location == "page 1"

    def test_prose_excluded_from_requirements_is_still_in_its_section(self):
        result = Segmenter().run(
            _paragraphs("Introduction", "The app helps retail customers bank on the move.")
        )
        assert result.requirements == []
        assert result.sections[0].heading == "Introduction"
        assert result.sections[0].body == "The app helps retail customers bank on the move."

    def test_styled_docx_headings_open_sections(self):
        segments = [
            RawSegment(
                text=text,
                source_document="srs.docx",
                page_or_paragraph=i + 1,
                location_type="paragraph",
                section_heading=heading,
                order_index=i,
            )
            for i, (heading, text) in enumerate(
                [
                    ("2.3 User Classes", "Customers and support agents."),
                    ("2.3 User Classes", "Fraud analysts review alerts."),
                    ("3 Requirements", "REQ-1: The app shall log in."),
                ]
            )
        ]
        sections = Segmenter().run(segments).sections
        assert [(s.heading, s.body) for s in sections] == [
            ("2.3 User Classes", "Customers and support agents.\n\nFraud analysts review alerts."),
            ("3 Requirements", "REQ-1: The app shall log in."),
        ]
        assert sections[1].location == "paragraph 3"

    def test_text_before_the_first_heading_has_no_heading(self):
        sections = Segmenter().run(_pages("REQ-1: The app shall log in.")).sections
        assert [(s.heading, s.body) for s in sections] == [(None, "REQ-1: The app shall log in.")]

    def test_toc_lines_and_empty_headings_are_not_sections(self):
        sections = (
            Segmenter()
            .run(
                _pages(
                    "Contents\n\n1 Introduction 2\n\n1 Introduction\n\n1.1 Scope\n\nBanking only."
                )
            )
            .sections
        )
        assert [(s.heading, s.body) for s in sections] == [("1.1 Scope", "Banking only.")]
