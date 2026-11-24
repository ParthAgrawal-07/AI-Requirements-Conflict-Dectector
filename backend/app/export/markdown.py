"""The small Markdown subset the exports use, parsed into blocks (Bansil — US-41).

Every export is written as Markdown first; DOCX and PDF render these blocks, so the three formats
say the same thing. Supported: ``#``–``####`` headings, paragraphs, ``-`` bullet lists, ``>``
block quotes, ``---`` rules and ``**bold**`` / ``_italic_`` inline.

**Block quotes are verbatim.** Requirement statements are written as quotes and rendered exactly
as stored — no inline formatting is interpreted inside them — so a requirement containing ``*``
or ``_`` reads the same in every format (DR-25).
"""

import re
from dataclasses import dataclass, field
from typing import Literal

BlockKind = Literal["heading", "paragraph", "bullets", "quote", "rule"]
_HEADING = re.compile(r"^(#{1,4})\s+(.*)$")
_BULLET = re.compile(r"^\s*[-*]\s+(.*)$")
_INLINE = re.compile(r"\*\*(.+?)\*\*|(?<![\w])_(.+?)_(?![\w])")


@dataclass
class Block:
    kind: BlockKind
    text: str = ""
    level: int = 0  # headings
    items: list[str] = field(default_factory=list)  # bullets


@dataclass(frozen=True)
class Run:
    text: str
    bold: bool = False
    italic: bool = False


def parse(markdown: str) -> list[Block]:
    blocks: list[Block] = []
    paragraph: list[str] = []
    quote: list[str] = []
    bullets: list[str] = []

    def flush() -> None:
        if paragraph:
            blocks.append(Block("paragraph", " ".join(s.strip() for s in paragraph)))
            paragraph.clear()
        if quote:
            blocks.append(Block("quote", "\n".join(quote)))
            quote.clear()
        if bullets:
            blocks.append(Block("bullets", items=list(bullets)))
            bullets.clear()

    for line in markdown.splitlines():
        stripped = line.strip()
        if line.startswith(">"):
            if paragraph or bullets:
                flush()
            quote.append(line[2:] if line.startswith("> ") else line[1:])
            continue
        if quote:
            flush()
        if not stripped:
            flush()
            continue
        heading = _HEADING.match(stripped)
        if heading:
            flush()
            blocks.append(Block("heading", heading.group(2).strip(), level=len(heading.group(1))))
            continue
        if stripped in ("---", "***"):
            flush()
            blocks.append(Block("rule"))
            continue
        bullet = _BULLET.match(line)
        if bullet:
            if paragraph:
                flush()
            bullets.append(bullet.group(1).strip())
            continue
        if bullets:  # a continuation line of the last bullet
            bullets[-1] += " " + stripped
            continue
        paragraph.append(stripped)
    flush()
    return blocks


def runs(text: str) -> list[Run]:
    """Inline ``**bold**`` and ``_italic_`` as runs (never used inside quotes)."""
    result: list[Run] = []
    position = 0
    for match in _INLINE.finditer(text):
        if match.start() > position:
            result.append(Run(text[position : match.start()]))
        if match.group(1) is not None:
            result.append(Run(match.group(1), bold=True))
        else:
            result.append(Run(match.group(2), italic=True))
        position = match.end()
    if position < len(text):
        result.append(Run(text[position:]))
    return result or [Run("")]


def quote_lines(text: str) -> str:
    """Write ``text`` as a Markdown block quote, line by line (verbatim)."""
    return "\n".join(f"> {line}" if line else ">" for line in text.splitlines() or [""])
