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
PROMPT_VERSION = "v1"


@cache
def load_prompt(name: str, version: str = PROMPT_VERSION) -> Template:
    """Read ``prompts/<name>_<version>.md``, e.g. ``load_prompt("pair_system")``."""
    kind, _, part = name.rpartition("_")
    path = PROMPTS_DIR / f"{kind}_{version}_{part}.md"
    if not path.is_file():
        raise FileNotFoundError(f"No prompt {name!r} for version {version!r} (looked for {path})")
    return Template(path.read_text(encoding="utf-8"))


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
        output_schema=_schema_json(PairClassificationOutput)
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
        output_schema=_schema_json(SingleClassificationOutput)
    )
    user = load_prompt("single_user", version).substitute(
        context_pack=_pack(context_pack),
        req_id=_as_data(requirement.id),
        req_text=_as_data(requirement.text),
    )
    return system, user
