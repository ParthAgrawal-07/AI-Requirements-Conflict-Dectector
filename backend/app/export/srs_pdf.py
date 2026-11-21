"""PDF rendering of an export (Bansil — US-41, FR-74, FR-107), with PyMuPDF's ``Story``.

The Markdown blocks become simple, escaped HTML that ``pymupdf.Story`` lays out on A4 pages
with page numbers in the footer — no extra dependency. Requirement statements (block quotes) keep
their text exactly as stored.
"""

import html
import io

import pymupdf

from app.export.markdown import Run, parse, runs

PAGE = pymupdf.paper_rect("a4")
MARGIN = 54  # 0.75 in
CSS = """
body { font-family: sans-serif; font-size: 10.5pt; line-height: 1.35; }
h1 { font-size: 18pt; margin-bottom: 6pt; }
h2 { font-size: 14pt; margin-top: 14pt; }
h3 { font-size: 12pt; margin-top: 10pt; }
h4 { font-size: 11pt; margin-top: 8pt; }
blockquote { margin-left: 12pt; padding-left: 8pt; border-left: 2pt solid #999999;
             white-space: pre-wrap; }
li { margin-bottom: 2pt; }
"""


def _inline(items: list[Run]) -> str:
    out = []
    for run in items:
        text = html.escape(run.text)
        if run.bold:
            text = f"<b>{text}</b>"
        if run.italic:
            text = f"<i>{text}</i>"
        out.append(text)
    return "".join(out)


def to_html(markdown: str) -> str:
    parts: list[str] = []
    for block in parse(markdown):
        if block.kind == "heading":
            parts.append(f"<h{block.level}>{html.escape(block.text)}</h{block.level}>")
        elif block.kind == "paragraph":
            parts.append(f"<p>{_inline(runs(block.text))}</p>")
        elif block.kind == "bullets":
            items = "".join(f"<li>{_inline(runs(item))}</li>" for item in block.items)
            parts.append(f"<ul>{items}</ul>")
        elif block.kind == "quote":
            parts.append(f"<blockquote>{html.escape(block.text)}</blockquote>")
        elif block.kind == "rule":
            parts.append("<hr/>")
    return "\n".join(parts)


def render(markdown: str, *, title: str) -> bytes:
    story = pymupdf.Story(html=to_html(markdown), user_css=CSS)
    buffer = io.BytesIO()
    writer = pymupdf.DocumentWriter(buffer)
    where = PAGE + (MARGIN, MARGIN, -MARGIN, -MARGIN - 18)
    more = True
    while more:
        device = writer.begin_page(PAGE)
        more, _ = story.place(where)
        story.draw(device)
        writer.end_page()
    writer.close()
    document = pymupdf.open(stream=buffer.getvalue(), filetype="pdf")
    document.set_metadata({"title": title, "creator": "AI Requirements Conflict Detector"})
    for number in range(document.page_count):
        page = document.load_page(number)
        page.insert_text(
            (MARGIN, PAGE.height - MARGIN / 2),
            f"{title} — page {number + 1} of {document.page_count}",
            fontsize=8,
        )
    return bytes(document.tobytes())
