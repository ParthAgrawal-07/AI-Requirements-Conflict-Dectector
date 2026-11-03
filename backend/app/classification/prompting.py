"""Load the versioned classification prompts and fill them in (Role 3).

Prompt text lives in ``prompts/<kind>_<version>_{system,user}.md`` rather than in Python
strings, so a prompt change shows up as a clean diff and old versions stay reproducible
for benchmark runs. Templates use ``string.Template`` (``$name``) instead of ``str.format``
because the embedded JSON Schema is full of ``{`` and ``}``.

Every message builder returns ``(system_prompt, user_prompt)``; actually calling the LLM is
the classifier's job (Sprint 2).
"""

import html
import json
import re
from functools import cache
from pathlib import Path
from string import Template

from pydantic import BaseModel

from app.classification.schemas import (
    PairClassificationOutput,
    RequirementInput,
    SingleClassificationOutput,
)

PROMPTS_DIR = Path(__file__).parent / "prompts"
PROMPT_VERSION = "v2"

# Sprint 2 (US-05): one section per category in prompts/<category>_v1.txt, composed into the v2
# system prompts — the pair prompt holds the three pair categories, the single prompt the two
# single-requirement ones. v1 prompts stay unchanged so earlier benchmark runs are reproducible.
PAIR_SECTIONS = ("conflict", "duplicate", "dependent")
SINGLE_SECTIONS = ("ambiguous", "incomplete")
SECTION_VERSION = "v1"
LINT_CATALOGUE = Path(__file__).parents[1] / "lint" / "catalogue.json"
MAX_PATTERN_MATCHES = 8


@cache
def load_prompt(name: str, version: str = PROMPT_VERSION) -> Template:
    """Read ``prompts/<name>_<version>.md``, e.g. ``load_prompt("pair_system")``."""
    kind, _, part = name.rpartition("_")
    path = PROMPTS_DIR / f"{kind}_{version}_{part}.md"
    if not path.is_file():
        raise FileNotFoundError(f"No prompt {name!r} for version {version!r} (looked for {path})")
    return Template(path.read_text(encoding="utf-8"))


@cache
def category_guidance(sections: tuple[str, ...], version: str = SECTION_VERSION) -> str:
    """The category sections of a system prompt, in order (``prompts/<name>_<version>.txt``)."""
    parts = []
    for name in sections:
        path = PROMPTS_DIR / f"{name}_{version}.txt"
        if not path.is_file():
            raise FileNotFoundError(f"No category prompt {name!r} for version {version!r}")
        parts.append(path.read_text(encoding="utf-8").strip())
    return "# Categories\n\n" + "\n\n".join(parts)


@cache
def _lint_patterns() -> tuple[tuple[re.Pattern[str], str], ...]:
    entries = json.loads(LINT_CATALOGUE.read_text(encoding="utf-8"))["entries"]
    return tuple(
        (re.compile(entry["pattern"], re.IGNORECASE), entry["message"])
        for entry in entries
        if entry.get("category") == "vague"
    )


def pattern_matches(text: str) -> list[tuple[str, str]]:
    """Wording that matched the lint catalogue's vague-word patterns (DR-07), as
    ``(term as written, why it is flagged)``. A hint for the model, never a verdict."""
    found: list[tuple[str, str]] = []
    for pattern, message in _lint_patterns():
        for match in pattern.finditer(text):
            if all(match.group(0).lower() != term.lower() for term, _ in found):
                found.append((match.group(0), message))
    return found[:MAX_PATTERN_MATCHES]


def _pattern_block(text: str) -> str:
    matches = pattern_matches(text)
    if not matches:
        return ""
    lines = "\n".join(f'"{_as_data(term)}" — {_as_data(message)}' for term, message in matches)
    return f"<pattern_matches>\n{lines}\n</pattern_matches>\n\n"


def _schema_json(model: type[BaseModel]) -> str:
    return json.dumps(model.model_json_schema(), indent=2)


def _as_data(value: str) -> str:
    """Escape requirement text so it can't close the ``<requirement>`` tag it sits in.

    Without this, a requirement containing ``</requirement>`` followed by instructions
    could break out of the data section of the prompt (prompt injection).
    """
    return html.escape(value, quote=True)


def _pack(context_pack: str) -> str:
    # Already escaped by ContextPackBuilder; a blank line separates it from the task line.
    return f"{context_pack}\n\n" if context_pack else ""


def build_pair_messages(
    a: RequirementInput,
    b: RequirementInput,
    version: str = PROMPT_VERSION,
    *,
    context_pack: str = "",
) -> tuple[str, str]:
    """``context_pack`` is the rendered ``<project_context>`` block (``ContextPack.text``), or ""."""
    system = load_prompt("pair_system", version).substitute(
        output_schema=_schema_json(PairClassificationOutput),
        category_guidance=category_guidance(PAIR_SECTIONS),
    )
    user = load_prompt("pair_user", version).substitute(
        context_pack=_pack(context_pack),
        a_id=_as_data(a.id),
        a_text=_as_data(a.text),
        b_id=_as_data(b.id),
        b_text=_as_data(b.text),
    )
    return system, user


def build_single_messages(
    requirement: RequirementInput,
    version: str = PROMPT_VERSION,
    *,
    context_pack: str = "",
) -> tuple[str, str]:
    system = load_prompt("single_system", version).substitute(
        output_schema=_schema_json(SingleClassificationOutput),
        category_guidance=category_guidance(SINGLE_SECTIONS),
    )
    user = load_prompt("single_user", version).substitute(
        context_pack=_pack(context_pack),
        pattern_matches=_pattern_block(requirement.text),
        req_id=_as_data(requirement.id),
        req_text=_as_data(requirement.text),
    )
    return system, user
