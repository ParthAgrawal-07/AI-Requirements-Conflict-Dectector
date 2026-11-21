"""Resolution suggestion prompts (Keval — US-45 prompts, FR-68, NFR-36, DR-04, DR-20).

Madhav's ``SuggestionService`` asks for up to three options per finding through
:func:`propose`; this module owns the prompt (``prompts/suggest_v1_*.md`` plus the per-category
guidance in ``prompts/suggest_v1.txt``), the output schema agreed in Sprint 0 —
``{options: [{text, target, trade_off, confidence, tbd_slots}]}`` — and the guard every reply
passes before anyone sees it (re-asked once with the reasons):

* ``target`` names one of the requirements given (or is null, for a Dependent link only);
* options are different from each other;
* no invented numbers: every number in an option is in the requirements, the finding, the
  project context or the member's instruction — anything else must be ``[TBD — confirm]``;
* the ``[TBD — confirm]`` slots in the text and ``tbd_slots`` agree.

Examples from earlier feedback (``examples``) are passed only when the project has switched the
experiment on (``projects.use_feedback_examples``, SX-30); the caller selects them from the same
project only (SX-23). The prompt never claims the model "learns" from them.
"""

import logging
import re
import uuid
from dataclasses import dataclass
from functools import cache
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.classification.context_pack import ContextPack
from app.classification.llm_client import LLMClient, LLMError
from app.classification.prompting import PROMPTS_DIR, _as_data, _pack, _schema_json, load_prompt
from app.classification.schemas import RequirementInput

logger = logging.getLogger(__name__)

SUGGEST_VERSION = "suggest-v1"
TBD = "[TBD — confirm]"
ATTEMPTS = 2
MAX_OPTIONS = 3
_ID = re.compile(r"\b[A-Z]{2,6}-\d+\b")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


class SuggestionOption(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    text: str = Field(min_length=10, max_length=2000, description="The proposed wording")
    target: str | None = Field(
        description="ID of the requirement this wording replaces; null if none changes"
    )
    trade_off: str = Field(min_length=5, max_length=400, description="What this option gives up")
    confidence: float = Field(ge=0, le=1)
    tbd_slots: list[str] = Field(
        default_factory=list, max_length=6, description=f"What each {TBD} stands for, in order"
    )


class SuggestionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    options: list[SuggestionOption] = Field(min_length=1, max_length=MAX_OPTIONS)

    @model_validator(mode="after")
    def _distinct(self) -> Self:
        seen = {" ".join(option.text.lower().split()) for option in self.options}
        if len(seen) != len(self.options):
            raise ValueError("options must be different from each other")
        return self


@dataclass(frozen=True)
class Example:
    """A past decision on a suggestion in the same project (the opt-in experiment)."""

    category: str
    outcome: str  # accepted, accepted_edited, rejected_meaning…
    text: str  # the final text people adopted, or the rejected option


@cache
def guidance(category: str) -> str:
    """The ``## <category>`` block of ``prompts/suggest_v1.txt``."""
    text = (PROMPTS_DIR / "suggest_v1.txt").read_text(encoding="utf-8")
    for block in text.split("## ")[1:]:
        heading, _, body = block.partition("\n")
        if heading.strip() == category:
            return f"# How to resolve a {category} finding\n\n{body.strip()}"
    raise KeyError(f"No suggestion guidance for category {category!r}")


def build_messages(
    category: str,
    requirements: list[RequirementInput],
    rationale: str,
    *,
    pack: ContextPack,
    instruction: str | None = None,
    examples: list[Example] | None = None,
) -> tuple[str, str]:
    system = load_prompt("suggest_system", "v1").substitute(
        guidance=guidance(category), schema=_schema_json(SuggestionOutput)
    )
    blocks = "\n".join(
        f'<requirement id="{_as_data(r.id)}">\n{_as_data(r.text)}\n</requirement>'
        for r in requirements
    )
    example_block = ""
    if examples:
        lines = "\n".join(
            f"- {_as_data(e.outcome)}: {_as_data(e.text)}"
            for e in examples
            if e.category == category
        )
        if lines:
            example_block = (
                "<examples>\nHow this team decided on earlier suggestions for this category:\n"
                f"{lines}\n</examples>\n\n"
            )
    instruction_block = (
        f"<instruction>\n{_as_data(instruction)}\n</instruction>\n\n" if instruction else ""
    )
    user = load_prompt("suggest_user", "v1").substitute(
        context_pack=_pack(pack.text),
        examples=example_block,
        category=_as_data(category),
        rationale=_as_data(rationale),
        requirements=blocks,
        instruction=instruction_block,
    )
    return system, user


def _numbers(text: str) -> set[str]:
    return set(_NUMBER.findall(_ID.sub(" ", text)))


def problems(
    output: SuggestionOutput,
    category: str,
    requirements: list[RequirementInput],
    *,
    known_text: str,
) -> list[str]:
    """Why ``output`` cannot be shown (empty when it can). ``known_text`` is everything the model
    was given: the finding, the context pack and the instruction."""
    found: list[str] = []
    ids = {r.id for r in requirements}
    allowed = _numbers(known_text) | set().union(*(_numbers(r.text) for r in requirements))
    for number, option in enumerate(output.options, start=1):
        if option.target is None and category != "Dependent":
            found.append(f"option {number} has no target requirement")
        elif option.target is not None and option.target not in ids:
            found.append(f"option {number} targets {option.target}, which was not given")
        invented = sorted(_numbers(option.text) - allowed)
        if invented:
            found.append(
                f"option {number} invents numbers ({', '.join(invented)}); use {TBD} instead"
            )
        if option.text.count(TBD) != len(option.tbd_slots):
            found.append(
                f"option {number} lists {len(option.tbd_slots)} tbd_slots for "
                f"{option.text.count(TBD)} {TBD} placeholder(s)"
            )
    return found


def propose(
    category: str,
    requirements: list[RequirementInput],
    rationale: str,
    *,
    llm: LLMClient,
    pack: ContextPack,
    project_id: uuid.UUID | None,
    instruction: str | None = None,
    examples: list[Example] | None = None,
) -> tuple[SuggestionOutput | None, int]:
    """The validated options (or ``None``) and the LLM calls it took.

    ``BudgetExceededError`` propagates: the caller parks the suggestion as waiting."""
    system, user = build_messages(
        category, requirements, rationale, pack=pack, instruction=instruction, examples=examples
    )
    known = " ".join([rationale, pack.text, instruction or ""])
    calls = 0
    for _ in range(ATTEMPTS):
        before = llm.calls
        try:
            output = llm.complete_json(system, user, SuggestionOutput, project_id=project_id)
        except LLMError as error:
            calls += llm.calls - before
            logger.info("No suggestions: %s", type(error).__name__)
            return None, calls
        calls += llm.calls - before
        found = problems(output, category, requirements, known_text=known)
        if not found:
            return output, calls
        logger.info("Suggestions rejected: %s", "; ".join(found))
        user += (
            "\n\nYour previous answer was rejected because "
            + "; ".join(found)
            + ". Answer again, following every rule."
        )
    return None, calls
