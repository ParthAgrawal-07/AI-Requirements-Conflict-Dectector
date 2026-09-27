"""
Regex patterns for identifying requirement IDs in SRS documents.

These rules are intentionally simple for Sprint 0. They will be
expanded with more sophisticated patterns in Sprint 1 (e.g.,
multi-line requirements, heading-based detection).

Supported ID formats (Sprint 0):
    REQ-01, REQ-001, REQ-0001
    FR-1, FR-1.2, FR-12.3
    NFR-01, NFR-1.2

The hyphen between the prefix and number is REQUIRED.
"""

import re

# Match common requirement IDs: prefix + hyphen + digits + optional sub-number
# Examples: REQ-001, FR-1.2, NFR-01
REQUIREMENT_ID_PATTERN = re.compile(
    r'\b(?:REQ|FR|NFR)-\d+(?:\.\d+)?\b'
)

# Match numbered list items: "1.", "2.1.", "3.2.1." etc.
# Useful for detecting structured lists even without explicit IDs
NUMBERED_LIST_PATTERN = re.compile(
    r'^\s*\d+(?:\.\d+)*\.\s+'
)
