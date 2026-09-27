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
                order_index=0,
            ),
            RawSegment(
                text="This is an intro paragraph.",
                source_document="test.pdf",
                page_or_paragraph=2,
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
                order_index=4,
            )
        ]

        segmenter = Segmenter()
        requirements = segmenter.segment(raw_segments)

        assert requirements[0].source_document == "my_srs.pdf"
        assert "5" in requirements[0].location

    def test_returns_requirement_type(self):
        """All items in the output must be Requirement instances."""
        raw_segments = [
            RawSegment(
                text="REQ-001: Test.",
                source_document="test.pdf",
                page_or_paragraph=1,
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
