"""
Requirement segmenter (US-02, FR-03, FR-04).

Turns parser output (RawSegments) into individual Requirement objects in two passes.

1. Grouping: lines are grouped into candidate units.
   - A line starting with a requirement ID always starts a new unit.
   - A wrapped line continues the current unit; a new paragraph starts a new one,
     unless the current unit is still "open": it ends with ":" (a list follows),
     it is a bare ID (ID and text in separate cells/blocks), or it runs on across
     a page break mid-sentence.
   - Bullet / numbered items following a lead-in ("...the following formats:")
     are kept with it as sub-items; otherwise each item is its own unit.
   - Headings are not units; they become the section_heading of what follows.
   - Table-of-contents lines are excluded.

2. Classification: each unit becomes zero or more Requirements.
   - A unit with an ID is one requirement; its original ID is preserved (DR-03).
   - A unit without an ID is split into sentences with spaCy, and each sentence
     with a modal verb (shall/must/should/will...) starts a new requirement.
   - Text without ID or modal verb is excluded if it is a short fragment (title,
     label, table header) or sits in a clearly non-requirement section
     (Introduction, Glossary...). Otherwise it is kept and flagged for review.
   - Anything uncertain is kept with needs_review=True and a reason (US-02), never
     silently dropped. Excluded text is returned in SegmentationResult.excluded.

Requirements without a source ID get a deterministic fallback ID:
UNKNOWN-{page_or_paragraph}-{n}, n counting from 0 within that page/paragraph.

Alongside the requirements, every heading and the verbatim text under it is
returned as a DocumentSection (SegmentationResult.sections), for the project
context: the brief drafter and the context pack read them (FR-104, FR-105).
"""

import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache

import spacy
from spacy.language import Language

from app.ingestion.models import (
    DocumentSection,
    ExcludedText,
    RawSegment,
    Requirement,
    SegmentationResult,
)
from app.ingestion.segmentation.rules import (
    BULLET_PATTERN,
    NON_REQUIREMENT_SECTION_PATTERN,
    NUMBERED_HEADING_PATTERN,
    NUMBERED_LIST_PATTERN,
    REQUIREMENT_ID_PATTERN,
    STRONG_MODAL_PATTERN,
    TERMINAL_PUNCTUATION_PATTERN,
    TOC_LINE_PATTERN,
    TOC_TITLE_PATTERN,
    WEAK_MODAL_PATTERN,
)

logger = logging.getLogger(__name__)

_MAX_HEADING_WORDS = 10
_MAX_UNNUMBERED_HEADING_WORDS = 6
_MIN_STATEMENT_WORDS = 4  # shorter modal-less text without punctuation is a fragment
_LONG_REQUIREMENT_CHARS = 1000
_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")
_TRAILING_PAGE_NUMBER = re.compile(r"\s\d+$")
_WORD = re.compile(r"\w+")
_CAPTION = re.compile(r"^(?:figure|fig\.|table)\s*\d", re.IGNORECASE)
# Small words allowed in lower case inside a Title Case heading.
_TITLE_SMALL_WORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "by",
    "for",
    "in",
    "of",
    "on",
    "or",
    "the",
    "to",
}


@lru_cache(maxsize=1)
def _sentencizer() -> Language:
    """Rule-based spaCy sentence splitter: no model download, so Docker/CI stay light."""
    nlp = spacy.blank("en")
    nlp.add_pipe("sentencizer")
    return nlp


def _is_list_item(line: str) -> bool:
    return bool(BULLET_PATTERN.match(line) or NUMBERED_LIST_PATTERN.match(line))


def _has_modal(text: str) -> bool:
    return bool(STRONG_MODAL_PATTERN.search(text) or WEAK_MODAL_PATTERN.search(text))


def _is_heading(line: str) -> bool:
    """Heuristic heading test for a line that forms a paragraph on its own."""
    if (
        "|" in line  # table row
        or _CAPTION.match(line)
        or BULLET_PATTERN.match(line)
        or REQUIREMENT_ID_PATTERN.match(line)
        or _has_modal(line)
        or TERMINAL_PUNCTUATION_PATTERN.search(line)
    ):
        return False
    words = line.split()
    if NUMBERED_HEADING_PATTERN.match(line):
        return 2 <= len(words) <= _MAX_HEADING_WORDS and words[1][:1].isupper()
    if len(words) > _MAX_UNNUMBERED_HEADING_WORDS:
        return False
    return line.isupper() or all(
        w[:1].isupper() or w[:1].isdigit() or w.lower() in _TITLE_SMALL_WORDS for w in words
    )


@dataclass
class _Unit:
    """Lines belonging to one candidate requirement, before classification."""

    segment: RawSegment  # where the unit starts
    heading: str | None
    source_req_id: str | None
    lines: list[str] = field(default_factory=list)
    in_list: bool = False

    @property
    def text(self) -> str:
        return "\n".join(self.lines)

    @property
    def location(self) -> str:
        return f"{self.segment.location_type} {self.segment.page_or_paragraph}"

    @property
    def is_bare_id(self) -> bool:
        if not self.source_req_id:
            return False
        rest = self.text.split(self.source_req_id, 1)[-1]
        return not rest.strip(" \t\n:.-–|)]")

    def add(self, line: str, *, list_item: bool = False) -> None:
        if not self.lines or list_item:
            self.lines.append(line)
            self.in_list = self.in_list or (list_item and len(self.lines) > 1)
        elif self.lines[-1].endswith("-") and line[:1].islower():
            self.lines[-1] += line  # word hyphenated across a line break: "real-" + "time"
        else:
            self.lines[-1] += " " + line

    def accepts_list_item(self, line: str) -> bool:
        if STRONG_MODAL_PATTERN.search(line):  # "- The system shall ..." stands alone
            return self.text.endswith(":") and not self.in_list
        return self.in_list or self.text.endswith(":")

    def accepts_next_paragraph(self, line: str, *, page_break: bool) -> bool:
        if self.is_bare_id or self.text.endswith(":"):
            return True
        # A sentence cut off by a page break continues on the next page. Lists end
        # without punctuation too, so they never continue this way.
        if not page_break or self.in_list:
            return False
        return line[:1].islower() or not (
            TERMINAL_PUNCTUATION_PATTERN.search(self.text) or STRONG_MODAL_PATTERN.search(line)
        )


@dataclass
class _Section:
    """A heading and the paragraphs under it, collected while grouping."""

    heading: str | None
    location: str
    paragraphs: list[list[str]] = field(default_factory=list)

    def add(self, line: str, *, new_paragraph: bool) -> None:
        if new_paragraph or not self.paragraphs:
            self.paragraphs.append([])
        self.paragraphs[-1].append(line)

    def build(self, order_index: int) -> DocumentSection:
        body = "\n\n".join("\n".join(lines) for lines in self.paragraphs)
        return DocumentSection(
            heading=self.heading, body=body, location=self.location, order_index=order_index
        )


class Segmenter:
    """Split RawSegments into individual Requirement objects."""

    def segment(self, raw_segments: list[RawSegment]) -> list[Requirement]:
        """Segment raw text chunks into requirements (see run() for excluded text too)."""
        return self.run(raw_segments).requirements

    def run(self, raw_segments: list[RawSegment]) -> SegmentationResult:
        excluded: list[ExcludedText] = []
        sections: list[_Section] = []
        units = self._group(raw_segments, excluded, sections)
        requirements = self._flag_duplicate_ids(self._classify(units, excluded))
        logger.info(
            "Segmented %d units into %d requirements (%d need review, %d excluded)",
            len(units),
            len(requirements),
            sum(r.needs_review for r in requirements),
            len(excluded),
        )
        built = [section for section in sections if section.paragraphs]
        return SegmentationResult(
            requirements=requirements,
            excluded=excluded,
            sections=[section.build(index) for index, section in enumerate(built)],
        )

    # ── Pass 1: grouping ─────────────────────────────────────────────────────
    def _group(
        self,
        raw_segments: list[RawSegment],
        excluded: list[ExcludedText],
        sections: list[_Section],
    ) -> list[_Unit]:
        """Group lines into units; also fill ``sections`` with every heading's text."""
        units: list[_Unit] = []
        current: _Unit | None = None
        heading: str | None = None
        parser_heading: str | None = None
        in_toc = False

        def close() -> None:
            nonlocal current
            if current is not None:
                units.append(current)
                current = None

        def open_section(title: str | None, location: str) -> None:
            sections.append(_Section(title, location))

        for seg in raw_segments:
            location = f"{seg.location_type} {seg.page_or_paragraph}"
            # A new styled (DOCX) heading wins; otherwise keep any heading we detected
            # from the text since then.
            if seg.section_heading != parser_heading:
                heading = parser_heading = seg.section_heading
                open_section(heading, location)
            elif not sections:
                open_section(heading, location)
            for para_idx, para in enumerate(_PARAGRAPH_BREAK.split(seg.text)):
                lines = [line.strip() for line in para.split("\n") if line.strip()]
                for line_idx, line in enumerate(lines):
                    if TOC_TITLE_PATTERN.match(line):
                        in_toc = True
                        close()
                        excluded.append(ExcludedText(text=line, location=location, reason="toc"))
                        continue
                    if TOC_LINE_PATTERN.search(line) or (
                        in_toc
                        and _TRAILING_PAGE_NUMBER.search(line)
                        and not REQUIREMENT_ID_PATTERN.match(line)
                        and not _has_modal(line)
                    ):
                        excluded.append(ExcludedText(text=line, location=location, reason="toc"))
                        continue
                    in_toc = False

                    id_match = REQUIREMENT_ID_PATTERN.match(line)
                    if id_match:
                        sections[-1].add(line, new_paragraph=line_idx == 0)
                        close()
                        current = _Unit(seg, heading, id_match.group("id"))
                        current.add(line)
                        continue

                    # The first item after a lead-in ("...channels:") is a list item even
                    # when it is short enough to look like a heading ("Email").
                    after_lead_in = current is not None and current.text.endswith(":")
                    # A numbered heading may share a PDF block with the requirement under it.
                    heading_above_id = (
                        line_idx == 0
                        and len(lines) > 1
                        and bool(NUMBERED_HEADING_PATTERN.match(line))
                        and bool(REQUIREMENT_ID_PATTERN.match(lines[1]))
                    )
                    if (
                        (len(lines) == 1 or heading_above_id)
                        and not after_lead_in
                        and not seg.is_list_item
                        and _is_heading(line)
                    ):
                        close()
                        heading = line
                        open_section(heading, location)
                        continue

                    # The section keeps the text verbatim, requirements and prose alike.
                    # A DOCX segment is one paragraph; in a PDF a blank line separates them.
                    sections[-1].add(line, new_paragraph=line_idx == 0)

                    is_list = seg.is_list_item or _is_list_item(line)
                    if current is not None:
                        if line_idx > 0:  # inside the same paragraph
                            if not is_list or current.accepts_list_item(line):
                                current.add(line, list_item=is_list)
                                continue
                        else:  # first line of a new paragraph (or page)
                            page_break = para_idx == 0 and seg.location_type == "page"
                            accepts = (
                                current.accepts_list_item(line)
                                if is_list
                                else current.accepts_next_paragraph(line, page_break=page_break)
                            )
                            if accepts:
                                current.add(line, list_item=is_list)
                                continue
                        close()
                    current = _Unit(seg, heading, None)
                    current.add(line)
        close()
        return units

    # ── Pass 2: classification ───────────────────────────────────────────────
    def _classify(self, units: list[_Unit], excluded: list[ExcludedText]) -> list[Requirement]:
        requirements: list[Requirement] = []
        fallback_counter: Counter[tuple[str, int]] = Counter()

        def emit(unit: _Unit, text: str, reasons: list[str]) -> None:
            source_id = unit.source_req_id
            if source_id is None:
                key = (unit.segment.source_document, unit.segment.page_or_paragraph)
                req_id = f"UNKNOWN-{unit.segment.page_or_paragraph}-{fallback_counter[key]}"
                fallback_counter[key] += 1
            else:
                req_id = source_id
            requirements.append(
                Requirement(
                    id=req_id,
                    source_req_id=source_id,
                    raw_text=text,
                    source_document=unit.segment.source_document,
                    location=unit.location,
                    section_heading=unit.heading,
                    order_index=len(requirements),
                    needs_review=bool(reasons),
                    review_reasons=tuple(reasons),
                )
            )

        for unit in units:
            text = unit.text
            if unit.source_req_id:
                emit(unit, text, self._id_unit_reasons(unit))
                continue

            for chunk in self._split_on_modal_sentences(text):
                verdict = self._judge_unlabelled(chunk, unit.heading)
                if verdict is None:
                    continue
                if isinstance(verdict, str):
                    excluded.append(
                        ExcludedText(text=chunk, location=unit.location, reason=verdict)
                    )
                else:
                    emit(unit, chunk, verdict)

        return requirements

    def _id_unit_reasons(self, unit: _Unit) -> list[str]:
        if unit.is_bare_id:
            return [f"Requirement ID {unit.source_req_id} has no requirement text"]
        reasons = []
        sentences = [s.text for s in _sentencizer()(unit.text).sents]
        if sum(bool(STRONG_MODAL_PATTERN.search(s)) for s in sentences) > 1:
            reasons.append("May contain more than one requirement (several 'shall/must' sentences)")
        if len(unit.text) > _LONG_REQUIREMENT_CHARS:
            reasons.append("Unusually long; check that it was not merged with following text")
        return reasons

    @staticmethod
    def _split_on_modal_sentences(text: str) -> list[str]:
        """Each sentence with a modal verb starts a new chunk; other sentences stay attached.

        Chunks are slices of the original text, so wording is preserved verbatim (FR-04).
        """
        sentences = list(_sentencizer()(text).sents)
        bounds = [0]
        for sent in sentences[1:]:
            # Don't split off a chunk with no words, e.g. the "1." of "1. The user shall..."
            if _has_modal(sent.text) and re.search(r"[^\W\d_]", text[bounds[-1] : sent.start_char]):
                bounds.append(sent.start_char)
        bounds.append(len(text))
        return [text[a:b].strip() for a, b in zip(bounds, bounds[1:], strict=False)]

    @staticmethod
    def _judge_unlabelled(text: str, heading: str | None) -> list[str] | str | None:
        """For text without a requirement ID, return review reasons (keep it) or an
        exclusion reason (str)."""
        if not text:
            return None
        non_req_section = bool(heading and NON_REQUIREMENT_SECTION_PATTERN.search(heading))
        if STRONG_MODAL_PATTERN.search(text):
            if non_req_section:
                return [f"Found in a non-requirement section ('{heading}')"]
            return []
        if non_req_section:
            return "non_requirement_section"
        words = len(_WORD.findall(text))  # ignores table "|" separators and bullets
        if words < _MIN_STATEMENT_WORDS and not TERMINAL_PUNCTUATION_PATTERN.search(text):
            return "fragment"
        if WEAK_MODAL_PATTERN.search(text):
            return ["No requirement ID, and no 'shall'/'must': uses a weaker modal verb"]
        return ["No requirement ID or modal verb; may not be a requirement"]

    @staticmethod
    def _flag_duplicate_ids(requirements: list[Requirement]) -> list[Requirement]:
        counts = Counter(r.source_req_id for r in requirements if r.source_req_id)
        flagged = []
        for r in requirements:
            n = counts.get(r.source_req_id or "", 0)
            if n > 1:
                reason = f"Duplicate requirement ID {r.source_req_id} (appears {n} times)"
                r = r.model_copy(
                    update={"needs_review": True, "review_reasons": (*r.review_reasons, reason)}
                )
            flagged.append(r)
        return flagged
