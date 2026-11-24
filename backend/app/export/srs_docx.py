"""DOCX rendering of an export (Bansil — US-41, FR-74, FR-107), with python-docx.

Headings become Word headings (so the navigation pane shows the outline), bullet lists use the
List Bullet style, block quotes — requirement statements — use the Quote style with their text
exactly as stored.
"""

import io

from docx import Document
from docx.shared import Pt

from app.export.markdown import parse, runs


def render(markdown: str, *, title: str) -> bytes:
    document = Document()
    document.core_properties.title = title
    normal = document.styles["Normal"]
    normal.font.size = Pt(11)
    for block in parse(markdown):
        if block.kind == "heading":
            document.add_heading(
                block.text, level=min(block.level - 1, 4) if block.level > 1 else 0
            )
        elif block.kind == "paragraph":
            paragraph = document.add_paragraph()
            for run in runs(block.text):
                piece = paragraph.add_run(run.text)
                piece.bold, piece.italic = run.bold, run.italic
        elif block.kind == "bullets":
            for item in block.items:
                paragraph = document.add_paragraph(style="List Bullet")
                for run in runs(item):
                    piece = paragraph.add_run(run.text)
                    piece.bold, piece.italic = run.bold, run.italic
        elif block.kind == "quote":
            document.add_paragraph(block.text, style="Quote")
        elif block.kind == "rule":
            document.add_paragraph("")
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()
