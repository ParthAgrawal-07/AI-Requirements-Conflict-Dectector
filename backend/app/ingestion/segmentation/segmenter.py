"""
Sprint 0 requirement segmenter.

Takes a list of RawSegment objects and produces Requirement objects by
scanning each line for known requirement ID patterns.

FALLBACK BEHAVIOR:
    Lines without a recognizable requirement ID are assigned a deterministic
    fallback ID in the format: UNKNOWN-{page_or_paragraph}-{line_index}
    This ensures every non-empty line produces a Requirement, so the
    downstream pipeline always has something to work with.

    This behavior is intentionally naive for Sprint 0 and will be replaced
    with production-quality rule-based segmentation in Sprint 1.
"""

import logging

from app.ingestion.models import RawSegment, Requirement
from app.ingestion.segmentation.rules import REQUIREMENT_ID_PATTERN

logger = logging.getLogger(__name__)


class Segmenter:
    """
    Split RawSegments into individual Requirement objects.

    Sprint 0 implementation: line-by-line regex matching only.
    """

    def segment(self, raw_segments: list[RawSegment]) -> list[Requirement]:
        """
        Segment raw text chunks into individual requirements.

        Args:
            raw_segments: Ordered list of RawSegment objects from a parser.

        Returns:
            List of Requirement objects with extracted or fallback IDs.
        """
        requirements: list[Requirement] = []

        for segment in raw_segments:
            lines = segment.text.split("\n")
            for line_idx, line in enumerate(lines):
                line = line.strip()
                if not line:
                    continue

                match = REQUIREMENT_ID_PATTERN.search(line)
                if match:
                    req_id = match.group(0)
                else:
                    # Deterministic fallback — preserves traceability
                    req_id = f"UNKNOWN-{segment.page_or_paragraph}-{line_idx}"
                    logger.debug(
                        "No requirement ID found in line %d of segment %d, "
                        "assigned fallback ID: %s",
                        line_idx,
                        segment.page_or_paragraph,
                        req_id,
                    )

                requirements.append(
                    Requirement(
                        id=req_id,
                        raw_text=line,
                        source_document=segment.source_document,
                        location=f"page/para {segment.page_or_paragraph}",
                    )
                )

        return requirements
