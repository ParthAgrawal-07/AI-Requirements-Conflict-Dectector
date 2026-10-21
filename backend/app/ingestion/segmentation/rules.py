"""
Regex patterns used by the PDF parser and the segmenter.

Supported requirement ID formats (FR-04: the printed ID is kept exactly as written):
    REQ-01, REQ-001, REQ_0001
    FR-1, FR-1.2, FR-1.2.3
    NFR-01, NFR-1.2
    DR-01  (data requirements, as used in our own requirements-spec.md)
    SR-, UR-, BR-, SYS-  (system / user / business requirements)
    Any other upper-case prefix: UC-01, US-12, SEC-3, PERF-01, QR-2
    Multi-part prefixes: FR-AUTH-01, REQ-SEC-001
    One-letter suffixes: REQ-001a, REQ-001-A, UC-1a, FR-2.1b

A hyphen or underscore between the prefix and number is REQUIRED. Standard and
encoding names that look like IDs (ISO-9001, UTF-8, TLS-1.2, ...) are not IDs.

The ID must START the line (optionally after whitespace, a bullet or an
opening bracket). An ID mentioned mid-sentence is a cross-reference
("conflicts with FR-1"), not the requirement's own ID.
"""

import re

# Prefixes that start a line like an ID but name a standard, protocol or encoding.
NOT_ID_PREFIXES = (
    "AES|CVE|COVID|EN|HTTP|HTTPS|IEC|IEEE|IPV|ISBN|ISO|MD|PCI|RFC|SHA|SSL|TLS|UTF|WCAG"
)

# Match a leading requirement ID: upper-case prefix (optionally multi-part) + hyphen or
# underscore + digits + any sub-numbers + an optional one-letter suffix.
# Use .match() and read group("id").
# Examples: REQ-001, FR-1.2.3, UC-07, FR-AUTH-01, REQ-001-A, UC-1a, "• NFR-01", "[DR-03]"
REQUIREMENT_ID_PATTERN = re.compile(
    r"^[\s•*\-(\[]*"
    rf"(?!(?:{NOT_ID_PREFIXES})[-_])"
    r"(?P<id>[A-Z][A-Z0-9]{0,9}(?:[-_][A-Z][A-Z0-9]{0,9}){0,2}[-_]\d+(?:\.\d+)*"
    r"(?:[-_.]?[A-Za-z](?![A-Za-z0-9]))?)"
    r"(?![-_.]?[A-Za-z0-9])"  # a longer word glued on ("SEC-1st", "A-4.Paper") is not an ID
)

# Match numbered list items: "1.", "2.1.", "3.2.1." etc.
# Useful for detecting structured lists even without explicit IDs
NUMBERED_LIST_PATTERN = re.compile(r"^\s*\d+(?:\.\d+)*\.\s+")

# Bullets and lettered items: "• x", "- x", "* x", "a) x", "(b) x", "iv) x"
BULLET_PATTERN = re.compile(r"^\s*(?:[•●▪◦‣⁃–*-]|\(?[a-z]\)|\(?[ivx]+\))\s+")

# Section heading numbering: "3", "3.2", "3.2.1." followed by a title
NUMBERED_HEADING_PATTERN = re.compile(r"^\d+(?:\.\d+)*\.?\s+\S")

# Table-of-contents entry: title, dot/ellipsis leaders (or a tab), page number.
TOC_LINE_PATTERN = re.compile(r"(?:\.{3,}|…+|(?:\s\.){3,}|\t)\s*\d+\s*$")
TOC_TITLE_PATTERN = re.compile(r"^(?:table\s+of\s+)?contents$", re.IGNORECASE)

# A margin block that is only a page number: "3", "Page 3", "Page 3 of 10", "3/10", "- 3 -"
PAGE_NUMBER_PATTERN = re.compile(
    r"^(?:(?:page\s+)?\d+(?:\s*(?:of|/)\s*\d+)?|[-–]\s*\d+\s*[-–])$", re.IGNORECASE
)

# Modal verbs. "Strong" ones are the standard SRS requirement keywords (RFC 2119 / IEEE 830);
# "weak" ones often mark requirements in informal SRS text, but also appear in narrative.
STRONG_MODAL_PATTERN = re.compile(r"\b(?:shall|must|(?:is|are)\s+required\s+to)\b", re.IGNORECASE)
WEAK_MODAL_PATTERN = re.compile(
    r"\b(?:should|will|can|may|needs?\s+to|has\s+to|have\s+to)\b", re.IGNORECASE
)

# Headings of sections that are not requirements. Modal-less text found under them is
# excluded; anywhere else it is kept and flagged for review (better a false keep than a
# silently dropped requirement). Only the nearest heading is checked.
NON_REQUIREMENT_SECTION_PATTERN = re.compile(
    r"\b(?:introduction|purpose|scope|overview|audience|glossary|definitions?|acronyms"
    r"|abbreviations|references|revision|history|appendix|acknowledg\w*|conventions"
    r"|document\s+organi[sz]ation|index)\b",
    re.IGNORECASE,
)

# End of a sentence or a lead-in to a list.
TERMINAL_PUNCTUATION_PATTERN = re.compile(r"[.!?:;]$")
