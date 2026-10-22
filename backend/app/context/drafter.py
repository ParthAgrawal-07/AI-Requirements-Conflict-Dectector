"""BriefDrafter: draft the project brief from an initial SRS (Bansil — FR-104, US-60).

Input is the document's sections (heading + verbatim body, from ingestion). Only the sections
that describe the product — introduction, purpose, scope, overall description, user classes,
environment, definitions, constraints, references — are used; specific requirements are not.

Two ways to draft, same output (:class:`app.context.brief.BriefValues`):

* **LLM** (the design): the selected sections go to the model inside a ``<document>`` block that
  the system prompt marks as data, and the reply must be JSON matching the brief schema. An
  invalid reply is retried once with the validation error; after that the drafter falls back.
* **Rules** (fallback): when no LLM is configured, or it fails, fields are filled from the
  sections whose headings match them ("1.2 Scope" → scope, "2.3 User Classes" → actors, …).

Either way every drafted field is stored as ``ai_drafted`` and the Project Manager must confirm
it (FR-104), so a weak draft costs a few edits, never a wrong brief.

The LLM is a plain ``(system, user) -> text`` callable so Keval's ``LLMClient`` adapter (budget,
retries, provider choice) plugs in without this module knowing the provider.
"""

import json
import logging
import re
from collections.abc import Callable, Iterable, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError

from app.context.brief import MAX_GLOSSARY, MAX_REFERENCES, BriefValues

logger = logging.getLogger(__name__)

DraftLLM = Callable[[str, str], str]  # (system prompt, user prompt) -> model reply

MAX_INPUT_CHARS = 24_000  # about 6k tokens of SRS text
_MAX_FIELD_CHARS = 2_000
_MAX_ACTORS = 15

_PROMPTS = Path(__file__).parent / "prompts"


class SectionLike(Protocol):
    """Anything with a heading and body: ingestion ``DocumentSection`` or the ORM row."""

    @property
    def heading(self) -> str | None: ...

    @property
    def body(self) -> str: ...


# Heading words per brief column. Checked in this order; a section feeds the first that matches.
_HEADING_RULES: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (column, re.compile(pattern, re.IGNORECASE))
    for column, pattern in (
        ("glossary", r"\b(?:glossary|definitions?|acronyms|abbreviations|terminology)\b"),
        ("references", r"\breferences?\b"),
        ("actors", r"\b(?:user\s+(?:classes|characteristics)|actors?|stakeholders?|personas?)\b"),
        ("environment", r"\b(?:operating\s+environment|environment|platforms?|domain)\b"),
        ("regulations", r"\b(?:regulat\w*|compliance|legal|standards)\b"),
        ("quality_goals", r"\b(?:quality|non-?functional)\b"),
        ("constraints", r"\b(?:constraints?|assumptions?|dependenc\w*|limitations?)\b"),
        ("scope_in", r"\bscope\b"),
        ("purpose", r"\b(?:purpose|problem|introduction|overview|product\s+perspective)\b"),
    )
)
# IEEE 830 / ISO 29148 put the brief material in chapters 1 and 2; chapter 3+ are requirements
# ("3.5 Design Constraints" is full of "shall" statements, not context).
_DESCRIPTIVE_CHAPTER = re.compile(r"^\s*[12](?:\.\d+)*\.?\s")
_LATER_CHAPTER = re.compile(r"^\s*(?:[3-9]|\d{2,})(?:\.\d+)*\.?\s")
_BACK_MATTER = re.compile(
    r"\b(?:glossary|definitions?|acronyms|abbreviations|terminology|references?)\b", re.IGNORECASE
)
_REQUIREMENTS_HEADING = re.compile(r"\brequirements?\b", re.IGNORECASE)
_OVERALL = re.compile(r"\b(?:overall|general)\s+description\b", re.IGNORECASE)

_OUT_OF_SCOPE = re.compile(
    r"\b(?:out\s+of\s+scope|not\s+in\s+scope|outside\s+(?:the\s+)?scope|excluded|"
    r"will\s+not|does\s+not|is\s+not|are\s+not)\b",
    re.IGNORECASE,
)
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_BULLET = re.compile(r"^\s*(?:[•●▪◦‣⁃–*-]|\d+[.)]|\(?[a-z]\))\s+")
_TERM_SPLIT = re.compile(r"\s*(?:\||:|\s[–—-]\s)\s*")
_URL = re.compile(r"https?://[^\s)>\]]+")
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$")


@lru_cache(maxsize=1)
def system_prompt() -> str:
    return (_PROMPTS / "brief_v1_system.md").read_text(encoding="utf-8")


def select_sections(sections: Iterable[SectionLike]) -> list[SectionLike]:
    """The sections that describe the product rather than specify it."""
    chosen = []
    for section in sections:
        heading = section.heading or ""
        if not section.body.strip():
            continue
        if _REQUIREMENTS_HEADING.search(heading) and not _OVERALL.search(heading):
            continue  # "3 Specific Requirements", "Functional Requirements"
        if _LATER_CHAPTER.match(heading) and not _BACK_MATTER.search(heading):
            continue  # a glossary or reference list at the end still counts
        if (
            _DESCRIPTIVE_CHAPTER.match(heading)
            or _OVERALL.search(heading)
            or any(rule.search(heading) for _, rule in _HEADING_RULES)
        ):
            chosen.append(section)
    return chosen


def document_block(sections: Sequence[SectionLike], max_chars: int = MAX_INPUT_CHARS) -> str:
    """The sections as one delimited block for the prompt, cut at ``max_chars``."""
    parts: list[str] = []
    used = 0
    for section in sections:
        part = f"## {section.heading or '(untitled)'}\n{section.body.strip()}"
        if used + len(part) > max_chars:
            part = part[: max(0, max_chars - used)]
        if not part:
            break
        parts.append(part)
        used += len(part) + 2
    # The model must never see a closing tag it could mistake for the end of the data.
    text = "\n\n".join(parts).replace("</document>", "</ document>")
    return f"<document>\n{text}\n</document>"


class BriefDrafter:
    def __init__(self, llm: DraftLLM | None = None) -> None:
        self.llm = llm

    def draft(self, sections: Sequence[SectionLike]) -> BriefValues:
        """Draft brief values from a document's sections. Never raises on bad model output."""
        chosen = select_sections(sections)
        if not chosen:
            return BriefValues()
        if self.llm is not None:
            drafted = self._draft_with_llm(self.llm, chosen)
            if drafted is not None:
                return drafted
        return draft_by_rules(chosen)

    @staticmethod
    def _draft_with_llm(llm: DraftLLM, sections: Sequence[SectionLike]) -> BriefValues | None:
        user = document_block(sections)
        error: str | None = None
        for attempt in (1, 2):
            prompt = user
            if error:
                prompt += (
                    f"\n\nYour previous reply was not valid: {error}\n"
                    "Reply again with only the JSON object."
                )
            try:
                reply = llm(system_prompt(), prompt)
            except Exception:
                logger.exception("Brief drafting: LLM call failed (attempt %d)", attempt)
                return None
            try:
                return parse_reply(reply)
            except (ValueError, ValidationError) as exc:
                error = _short_error(exc)
                logger.warning("Brief drafting: invalid reply (attempt %d): %s", attempt, error)
        return None


def parse_reply(reply: str) -> BriefValues:
    """Parse the model's JSON. Unknown keys are dropped; values must match the schema."""
    data = json.loads(_FENCE.sub("", reply.strip()))
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")
    # Cut long text before validating: an over-long purpose should be shortened, not cost the
    # whole draft (the schema's 4,000-character limit would reject it).
    known = {
        key: value[:_MAX_FIELD_CHARS] if isinstance(value, str) else value
        for key, value in data.items()
        if key in BriefValues.model_fields
    }
    if isinstance(known.get("actors"), list):
        known["actors"] = known["actors"][:_MAX_ACTORS]
    return BriefValues.model_validate(known)


def _short_error(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        first = exc.errors()[0]
        return f"{'.'.join(str(p) for p in first['loc'])}: {first['msg']}"
    return str(exc)[:200]


# ── Rules fallback ─────────────────────────────────────────────────────────────


def _column_for(heading: str | None) -> str | None:
    for column, rule in _HEADING_RULES:
        if heading and rule.search(heading):
            return column
    return None


def _lines(body: str) -> list[str]:
    return [_BULLET.sub("", line).strip() for line in body.splitlines() if line.strip()]


def _first_paragraph(body: str) -> str:
    return body.strip().split("\n\n", 1)[0].replace("\n", " ")


def _actor_names(body: str) -> list[str]:
    names = []
    for line in _lines(body):
        name = _TERM_SPLIT.split(line, maxsplit=1)[0].strip(" .,;")
        # A sentence is a description, not a name ("The system has three user classes.").
        if name and len(name.split()) <= 5 and not name.endswith(":"):
            names.append(name)
    return names


def _glossary(body: str) -> list[dict[str, str]]:
    entries = []
    for line in _lines(body):
        parts = _TERM_SPLIT.split(line, maxsplit=1)
        if len(parts) == 2 and parts[0] and parts[1] and len(parts[0]) <= 80:
            entries.append({"term": parts[0].strip(), "meaning": parts[1].strip()[:500]})
    return entries


def _references(body: str) -> list[dict[str, str | None]]:
    refs: list[dict[str, str | None]] = []
    for line in _lines(body):
        url = _URL.search(line)
        title = _URL.sub("", line).strip(" .,;:-–[]()") or (url.group(0) if url else "")
        if title:
            refs.append({"title": title[:200], "url": url.group(0) if url else None})
    return refs


def _split_scope(body: str) -> tuple[str | None, str | None]:
    text = " ".join(body.split())
    inside: list[str] = []
    outside: list[str] = []
    for sentence in _SENTENCE.split(text):
        (outside if _OUT_OF_SCOPE.search(sentence) else inside).append(sentence)
    return " ".join(inside) or None, " ".join(outside) or None


def draft_by_rules(sections: Sequence[SectionLike]) -> BriefValues:
    """Fill brief columns from the sections whose headings name them. First match wins."""
    values: dict[str, object] = {}
    texts: dict[str, list[str]] = {}
    glossary: list[dict[str, str]] = []
    references: list[dict[str, str | None]] = []
    for section in sections:
        column = _column_for(section.heading)
        # A section chosen only for its chapter number or "Overall Description" has no column.
        if column is None or column == "purpose":
            values.setdefault("purpose", _first_paragraph(section.body))
        elif column == "scope_in":
            scope_in, scope_out = _split_scope(section.body)
            values.setdefault("scope_in", scope_in)
            values.setdefault("scope_out", scope_out)
        elif column == "actors":
            values.setdefault("actors", _actor_names(section.body)[:_MAX_ACTORS])
        elif column == "glossary":
            glossary.extend(_glossary(section.body))
        elif column == "references":
            references.extend(_references(section.body))
        else:
            texts.setdefault(column, []).append(" ".join(section.body.split()))
    for column, parts in texts.items():
        values[column] = "\n\n".join(parts)
    values["glossary"] = glossary[:MAX_GLOSSARY] or None
    values["references"] = references[:MAX_REFERENCES] or None
    values = {
        key: value[:_MAX_FIELD_CHARS] if isinstance(value, str) else value
        for key, value in values.items()
    }
    try:
        return BriefValues.model_validate(values)
    except ValidationError:
        logger.exception("Brief drafting by rules produced invalid values")
        return BriefValues()


def get_brief_drafter() -> BriefDrafter:
    """The drafter the worker uses.

    No LLM is wired yet: Keval's ``LLMClient`` adapter (with the budget guard) is the one place
    that calls the provider. Until it lands this returns the rules drafter; afterwards it passes
    ``LLMClient(...).complete`` here. Tests replace this function.
    """
    return BriefDrafter(llm=None)
