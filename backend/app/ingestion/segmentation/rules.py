"""
Regex patterns for identifying requirement IDs in SRS documents.

These rules are intentionally simple for Sprint 0. They will be
expanded with more sophisticated patterns in Sprint 1 (e.g.,
multi-line requirements, heading-based detection).

Supported ID formats (Sprint 0):
    REQ-01, REQ-001, REQ-0001
    FR-1, FR-1.2, FR-1.2.3
    NFR-01, NFR-1.2
    DR-01  (data requirements, as used in our own requirements-spec.md)

The hyphen between the prefix and number is REQUIRED.

The ID must START the line (optionally after whitespace, a bullet or an
opening bracket). An ID mentioned mid-sentence is a cross-reference
("conflicts with FR-1"), not the requirement's own ID.
"""

import re

# Match a leading requirement ID: prefix + hyphen + digits + any sub-numbers.
# Use .match() and read group("id"). Examples: REQ-001, FR-1.2.3, "• NFR-01", "[DR-03]"
REQUIREMENT_ID_PATTERN = re.compile(r"^[\s\u2022*\-(\[]*(?P<id>(?:REQ|FR|NFR|DR)-\d+(?:\.\d+)*)\b")

# Match numbered list items: "1.", "2.1.", "3.2.1." etc.
# Useful for detecting structured lists even without explicit IDs
NUMBERED_LIST_PATTERN = re.compile(r"^\s*\d+(?:\.\d+)*\.\s+")
