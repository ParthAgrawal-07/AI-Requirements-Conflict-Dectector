"""
Reading order for PDF pages, rebuilt from line positions (US-02, FR-03). Owner: Bansil.

PyMuPDF's text blocks suit flowing text but not borderless tables: cells come out column
by column, wrapped cell text ("NU-" / "NFR-" / "01") is split from its row, and a row's
label and value can be fused into one line. Some PDF writers also put every wrapped line
of a paragraph in a block of its own. This module works from lines and their positions:

- Lines whose vertical extents touch form a band. A band whose lines fall into two or
  more side-by-side columns, each a gap-free stack of lines, is a table row and becomes
  one line, ``cell | cell | ...``, which the segmenter reads as a table row.
- A band whose columns have gaps in them (a two-column page layout) is read column by
  column, as flowing text.
- Cell text that wrapped below a loosely spaced row is put back in its cell, and a line
  in which the writer fused two cells is cut at the cell edges of the rows around it.
- Flowing text keeps PyMuPDF's block boundaries as paragraph breaks, except that a line
  that fills the text width without ending a sentence runs on into the next block.
  Wrapped large-font paragraphs (headings) are joined onto one line.
"""

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, replace
from typing import Any

import pymupdf

from app.ingestion.segmentation.rules import (
    BULLET_PATTERN,
    NUMBERED_LIST_PATTERN,
    REQUIREMENT_ID_PATTERN,
    TERMINAL_PUNCTUATION_PATTERN,
)

# Lines closer than this fraction of the font size touch: same cell or same table row.
# Cell lines sit ~0.1pt apart, table rows ~3pt (at 12pt), prose lines more.
_TOUCH = 0.15
# A wrapped line ends within this fraction of the text width from the right edge.
_FULL_LINE = 0.15
# Most a wrapped line may sit below the previous one, as a fraction of the font size.
_MAX_WRAP_GAP = 0.8
# A paragraph this much larger than the body font is a heading; it is joined onto one line.
_HEADING_SIZE_STEP = 1.5
_MAX_HEADING_LINES = 3
# How close (pt) a word or cell must start to a column edge to count as on it.
_ANCHOR_TOLERANCE = 1.5


@dataclass(frozen=True)
class Word:
    """A word and the spaces after it; a line's text is its words joined."""

    x0: float
    x1: float
    text: str


@dataclass(frozen=True)
class Line:
    x0: float
    y0: float
    x1: float
    y1: float
    size: float
    block: int
    words: tuple[Word, ...]

    @property
    def text(self) -> str:
        return "".join(w.text for w in self.words).strip()


@dataclass(frozen=True)
class Block:
    """A paragraph or table row in reading order, with its vertical extent."""

    text: str
    y0: float
    y1: float


@dataclass(frozen=True)
class _Band:
    lines: list[Line]
    columns: list[list[Line]]
    is_row: bool


def _band(lines: list[Line]) -> _Band:
    columns = _columns(lines)
    return _Band(lines, columns, len(columns) > 1 and all(_gap_free(c) for c in columns))


def page_lines(page: pymupdf.Page) -> list[Line]:
    """Non-empty text lines of a page, with word positions (for splitting fused cells)."""
    lines: list[Line] = []
    for block_no, block in enumerate(page.get_text("rawdict")["blocks"]):
        if block["type"] != 0:
            continue
        for raw in block["lines"]:
            chars = [c for span in raw["spans"] for c in span["chars"]]
            sizes = [s["size"] for s in raw["spans"] if any(c["c"].strip() for c in s["chars"])]
            if not sizes:
                continue
            x0, y0, x1, y1 = raw["bbox"]
            lines.append(Line(x0, y0, x1, y1, round(max(sizes), 1), block_no, _words(chars)))
    return lines


def _words(chars: list[dict[str, Any]]) -> tuple[Word, ...]:
    words: list[Word] = []
    text, start, end = "", 0.0, 0.0
    for char in chars:
        c, (cx0, _, cx1, _) = char["c"], char["bbox"]
        if c.strip() and text and not text[-1].strip():  # a word starts after a space
            words.append(Word(start, end, text))
            text = ""
        if not text:
            start = cx0
        if c.strip():
            end = cx1
        text += c
    if text.strip():
        words.append(Word(start, end, text))
    return tuple(words)


def body_font_size(pages: Iterable[list[Line]]) -> float:
    """The font size that most of the document's text is set in."""
    counts: Counter[float] = Counter()
    for lines in pages:
        for line in lines:
            counts[line.size] += len(line.text)
    return counts.most_common(1)[0][0] if counts else 0.0


def read_page(lines: list[Line], body_size: float) -> list[Block]:
    """Paragraphs and table rows of one page, in reading order."""
    bands = [b for band in _bands(lines) for b in _split_on_ids(band)]
    bands = [_split_fused_cells(band, _row_edges(bands, i)) for i, band in enumerate(bands)]
    bands = _merge_wrapped_cells(bands)

    flow = [ln for b in bands if not b.is_row for ln in b.lines]
    left = min((ln.x0 for ln in flow), default=0.0)
    right = max((ln.x1 for ln in flow), default=0.0)

    blocks: list[Block] = []
    paragraph: list[Line] = []

    def flush() -> None:
        if paragraph:
            blocks.append(_paragraph_block(paragraph, body_size))
            paragraph.clear()

    for band in bands:
        if band.is_row:
            flush()
            cells = [_join_wrapped([ln.text for ln in col]) for col in band.columns]
            blocks.append(
                Block(
                    " | ".join(cells),
                    min(ln.y0 for ln in band.lines),
                    max(ln.y1 for ln in band.lines),
                )
            )
            continue
        for column in band.columns:
            for line in column:
                if paragraph and not _same_paragraph(paragraph[-1], line, left, right):
                    flush()
                paragraph.append(line)
    flush()
    return blocks


def _bands(lines: list[Line]) -> list[_Band]:
    groups: list[list[Line]] = []
    bottom = float("-inf")
    for line in sorted(lines, key=lambda ln: (ln.y0, ln.x0)):
        if groups and line.y0 <= bottom + _TOUCH * line.size:
            groups[-1].append(line)
            bottom = max(bottom, line.y1)
        else:
            groups.append([line])
            bottom = line.y1
    return [_band(group) for group in groups]


def _columns(lines: list[Line]) -> list[list[Line]]:
    """Group lines into side-by-side columns: lines whose x-ranges overlap share one."""
    groups: list[list[Line]] = []
    right = float("-inf")
    for line in sorted(lines, key=lambda ln: ln.x0):
        if groups and line.x0 <= right + 1:
            groups[-1].append(line)
            right = max(right, line.x1)
        else:
            groups.append([line])
            right = line.x1
    columns = [sorted(g, key=lambda ln: (ln.y0, ln.x0)) for g in groups]
    # A bullet or list number set apart from its text is not a cell of its own.
    merged: list[list[Line]] = []
    for col in columns:
        if merged and len(merged[-1]) == 1 and _is_marker(merged[-1][0].text):
            merged[-1] = sorted(merged[-1] + col, key=lambda ln: (ln.y0, ln.x0))
        else:
            merged.append(col)
    return merged


def _is_marker(text: str) -> bool:
    """A bullet or list number on its own; it belongs to the cell on its right."""
    return bool(BULLET_PATTERN.fullmatch(text + " ") or NUMBERED_LIST_PATTERN.fullmatch(text + " "))


def _gap_free(column: list[Line]) -> bool:
    return all(b.y0 - a.y1 <= _TOUCH * b.size for a, b in zip(column, column[1:], strict=False))


def _split_on_ids(band: _Band) -> list[_Band]:
    """Tightly spaced table rows touch; a new requirement ID in the first column
    starts a new row."""
    if not band.is_row:
        return [band]
    starts = [ln.y0 for ln in band.columns[0] if REQUIREMENT_ID_PATTERN.match(ln.text)][1:]
    if not starts:
        return [band]
    parts: list[list[Line]] = [[] for _ in range(len(starts) + 1)]
    for line in band.lines:
        parts[sum(line.y0 >= s - 0.5 for s in starts)].append(line)
    return [_band(p) for p in parts if p]


def _left(column: list[Line]) -> float:
    return min(ln.x0 for ln in column)


def _aligned(x: float, edges: Iterable[float]) -> bool:
    return any(abs(x - edge) <= _ANCHOR_TOLERANCE for edge in edges)


def _row_edges(bands: list[_Band], i: int) -> list[tuple[list[float], float]]:
    """Cell edges and font size of the table rows on both sides of band i. A fused line
    sits inside a table; text just above or below one is left alone."""
    around = [bands[j] for j in (i - 1, i + 1) if 0 <= j < len(bands)]
    if len(around) < 2 or not all(b.is_row for b in around):
        return []
    return [([_left(col) for col in b.columns], b.lines[0].size) for b in around]


def _split_fused_cells(band: _Band, rows: list[tuple[list[float], float]]) -> _Band:
    """Split a line where a word starts on a cell edge of the rows around it: the PDF
    writer fused two cells ("Input Dispatch, note") into one line."""
    lines: list[Line] = []
    for line in band.lines:
        pieces = (_cut_at(line, edges) for edges, size in rows if abs(line.size - size) <= 0.5)
        lines.extend(next(filter(None, pieces), [line]))
    return band if len(lines) == len(band.lines) else _band(lines)


def _cut_at(line: Line, edges: list[float]) -> list[Line] | None:
    """The cells of ``line`` cut at a row's cell edges, or None unless every piece starts
    on an edge and ends before the next one: centred text, or prose that merely starts at
    the table's left margin, is not a row."""
    edges = sorted(edges)
    if not _aligned(line.x0, edges):
        return None
    cuts = [i for i, word in enumerate(line.words) if i and _aligned(word.x0, edges)]
    if not cuts:
        return None
    pieces: list[Line] = []
    for a, b in zip([0, *cuts], [*cuts, len(line.words)], strict=False):
        words = line.words[a:b]
        later = [e for e in edges if e > words[0].x0 + _ANCHOR_TOLERANCE]
        if later and words[-1].x1 > later[0]:
            return None
        pieces.append(replace(line, x0=words[0].x0, x1=words[-1].x1, words=words))
    return pieces


def _merge_wrapped_cells(bands: list[_Band]) -> list[_Band]:
    """Rejoin cell text that wrapped below its row. When a table's line spacing is loose,
    the wrapped lines of a cell ("drafts," / "owners, change-request intake") do not
    touch the row. They fill fewer cells than a row, each starting on a cell edge."""
    merged: list[_Band] = []
    for band in bands:
        row = merged[-1] if merged else None
        if row is None or not row.is_row or not _wraps_into(band, row):
            merged.append(band)
            continue
        columns = [list(col) for col in row.columns]
        for col in band.columns:
            target = next(c for c in columns if _aligned(_left(col), [_left(c)]))
            target.extend(col)
        merged[-1] = _Band(row.lines + band.lines, columns, True)
    return merged


def _wraps_into(band: _Band, row: _Band) -> bool:
    edges = [_left(col) for col in row.columns]
    gap = min(ln.y0 for ln in band.lines) - max(ln.y1 for ln in row.lines)
    return (
        len(band.columns) < len(row.columns)
        and 0 <= gap <= _MAX_WRAP_GAP * band.lines[0].size
        and all(_aligned(_left(col), edges) for col in band.columns)
        # A requirement ID (possibly wrapped: "NU-" / "NFR-" / "11") starts a new row.
        and not any(
            REQUIREMENT_ID_PATTERN.match(_join_wrapped([ln.text for ln in col]))
            for col in band.columns
        )
    )


def _same_paragraph(prev: Line, line: Line, left: float, right: float) -> bool:
    if prev.block == line.block:
        return True
    # Some writers put each wrapped line in its own block: rejoin a line that fills the
    # text width, does not end a sentence, and is followed closely by same-size text.
    return (
        abs(prev.size - line.size) <= 0.5
        and 0 <= line.y0 - prev.y1 <= _MAX_WRAP_GAP * prev.size
        and prev.x1 >= right - _FULL_LINE * (right - left)
        and not TERMINAL_PUNCTUATION_PATTERN.search(prev.text)
        and not (
            REQUIREMENT_ID_PATTERN.match(line.text)
            or BULLET_PATTERN.match(line.text)
            or NUMBERED_LIST_PATTERN.match(line.text)
        )
    )


def _paragraph_block(lines: list[Line], body_size: float) -> Block:
    texts = [ln.text for ln in lines]
    size = max(ln.size for ln in lines)
    if size >= body_size + _HEADING_SIZE_STEP and len(lines) <= _MAX_HEADING_LINES:
        text = _join_wrapped(texts)  # a wrapped heading is still one heading
    else:
        text = "\n".join(texts)
    return Block(text, min(ln.y0 for ln in lines), max(ln.y1 for ln in lines))


def _join_wrapped(texts: list[str]) -> str:
    """Join wrapped lines; a line ending in a hyphen ("NU-", "self-") runs on unspaced."""
    out = ""
    for text in texts:
        if not out:
            out = text
        elif out.endswith("-") and len(out) > 1 and out[-2] != " ":
            out += text
        else:
            out += " " + text
    return out
