"""The project context pack sent with every LLM prompt (Keval — US-60, FR-105, NFR-39).

What goes in, in this order, until the budget of :data:`MAX_PACK_TOKENS` is reached:

1. the brief summary (≤ 300 words, built by Bansil's service from *confirmed* fields only);
2. the user classes and actors;
3. glossary entries whose term appears in the text being analysed;
4. up to three sections of the project's documents closest to that text (section embeddings,
   Heet), or the first three when no query vector is given.

Only ``confirmed_context(db, project)`` and ``confirmed_values(...)`` are read — never the raw
columns — so AI-drafted fields reach the model only after the Project Manager confirms them. A
project in Setup has no confirmed context and gets an empty pack (it cannot be analysed anyway).

Everything is HTML-escaped and wrapped in ``<project_context>``: the prompts tell the model this
block is data, like requirement text (prompt injection through a brief is no different).

Tokens are estimated at four characters per token, which over-counts English slightly, so the
real size stays under the 1,500-token limit without a provider call per prompt.
"""

import html
import re
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.context import service as context_service
from app.context.brief import GlossaryEntry
from app.embeddings.store import nearest_sections
from app.models import DocumentSection, Project

MAX_PACK_TOKENS = 1500
CHARS_PER_TOKEN = 4
MAX_SECTIONS = 3
MAX_SECTION_CHARS = 1200  # one long section must not crowd out the other two


@dataclass(frozen=True)
class ContextPack:
    context_version: int | None  # stored on findings (FR-105); None in Setup
    text: str  # the rendered block, or "" when there is no confirmed context

    @property
    def estimated_tokens(self) -> int:
        return estimate_tokens(self.text)


def estimate_tokens(text: str) -> int:
    return -(-len(text) // CHARS_PER_TOKEN)  # ceiling division


def _esc(value: str) -> str:
    return html.escape(value, quote=True)


def matched_glossary(glossary: list[GlossaryEntry], text: str) -> list[GlossaryEntry]:
    """Entries whose term occurs in ``text`` as a whole word or phrase (case-insensitive)."""
    return [
        entry
        for entry in glossary
        if re.search(rf"(?<!\w){re.escape(entry.term)}(?!\w)", text, re.IGNORECASE)
    ]


class ContextPackBuilder:
    def __init__(self, db: Session, max_tokens: int = MAX_PACK_TOKENS) -> None:
        self._db = db
        self._max_chars = max_tokens * CHARS_PER_TOKEN

    def build(
        self,
        project: Project,
        *,
        query_text: str = "",
        query_vector: list[float] | None = None,
    ) -> ContextPack:
        context = context_service.confirmed_context(self._db, project)
        if context is None:
            return ContextPack(context_version=None, text="")
        values = context_service.confirmed_values(context)

        opening = f'<project_context version="{context.version}">'
        closing = "</project_context>"
        budget = self._max_chars - len(opening) - len(closing) - 2
        parts: list[str] = []

        def add(part: str) -> bool:
            nonlocal budget
            if len(part) + 1 > budget:
                return False
            parts.append(part)
            budget -= len(part) + 1
            return True

        summary = context.summary or context_service.build_summary(values)
        if summary:
            add(f"Summary: {_esc(summary)}")
        if values.actors:
            add("Actors: " + ", ".join(_esc(actor) for actor in values.actors))
        terms = matched_glossary(values.glossary or [], query_text)
        if terms:
            lines = ["Glossary:"] + [
                f"- {_esc(entry.term)}: {_esc(entry.meaning)}" for entry in terms
            ]
            if not add("\n".join(lines)) and add("Glossary:"):
                for line in lines[1:]:  # keep as many terms as fit
                    if not add(line):
                        break
        for section in self._sections(project.id, query_vector):
            heading = _esc(section.heading or "")
            body = _esc(section.body[:MAX_SECTION_CHARS])
            add(f'<section heading="{heading}">\n{body}\n</section>')

        return ContextPack(
            context_version=context.version,
            text="\n".join([opening, *parts, closing]),
        )

    def _sections(
        self, project_id: uuid.UUID, query_vector: list[float] | None
    ) -> list[DocumentSection]:
        if query_vector is not None:
            return nearest_sections(self._db, project_id, query_vector, k=MAX_SECTIONS)
        return list(
            self._db.scalars(
                select(DocumentSection)
                .where(DocumentSection.project_id == project_id)
                .order_by(DocumentSection.order_index)
                .limit(MAX_SECTIONS)
            )
        )
