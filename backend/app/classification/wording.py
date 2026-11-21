"""Improve wording (AI) (Keval — US-51, FR-93, DR-18; interface design §5.2).

The composer's *Improve wording* button sends the draft here; the LLM proposes an EARS rewrite
(``prompts/wording_v1_*.md``) that the composer shows **as a diff, labelled AI**. Nothing is
applied or stored: the member accepts the rewrite into their draft, or not.

Every reply passes a deterministic guard before it is shown (re-asked once with the reasons):

* it is one requirement — at most one "shall";
* it invents no numbers: every number in the rewrite is in the draft or the project context;
* every ``[TBD — confirm]`` slot in the text is listed in ``tbd_slots``, and the other way round.

Over budget, no model, or a reply that still breaks a rule: no suggestion (the API says why).
"""

import logging
import re
import uuid
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.classification.context_pack import ContextPack
from app.classification.llm_client import LLMClient, LLMError
from app.classification.prompting import _as_data, _pack, _schema_json, load_prompt
from app.lint.engine import lint

logger = logging.getLogger(__name__)

WORDING_VERSION = "wording-v1"
TBD = "[TBD — confirm]"
ATTEMPTS = 2
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
_SHALL = re.compile(r"\bshall\b", re.IGNORECASE)

Template = Literal["ubiquitous", "event", "state", "unwanted", "optional", "complex"]


class WordingOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    rewrite: str = Field(min_length=10, max_length=2000, description="The improved requirement")
    template: Template = Field(description="The EARS template the rewrite follows")
    changes: list[str] = Field(
        default_factory=list, max_length=5, description="What was changed and why, briefly"
    )
    tbd_slots: list[str] = Field(
        default_factory=list,
        max_length=6,
        description=f"What each {TBD} placeholder stands for, in order",
    )


@dataclass
class WordingSuggestion:
    original: str
    proposed: str
    template: str
    changes: list[str]
    tbd_slots: list[str]
    model: str
    label: str = "AI"
    prompt_version: str = WORDING_VERSION
    lint_before: int = 0  # lint scores, so the composer can say "quality: fair → good"
    lint_after: int = 0


def problems(output: WordingOutput, original: str, context: str = "") -> list[str]:
    """Why ``output`` cannot be shown (empty when it can)."""
    found: list[str] = []
    if len(_SHALL.findall(output.rewrite)) > 1:
        found.append('holds more than one "shall"')
    allowed = set(_NUMBER.findall(original)) | set(_NUMBER.findall(context))
    invented = sorted(set(_NUMBER.findall(output.rewrite)) - allowed)
    if invented:
        found.append(
            f"invents numbers the writer did not give ({', '.join(invented)}); use {TBD} instead"
        )
    slots = output.rewrite.count(TBD)
    if slots != len(output.tbd_slots):
        found.append(
            f"has {slots} {TBD} placeholder(s) but lists {len(output.tbd_slots)} in tbd_slots"
        )
    return found


def build_messages(text: str, *, pack: ContextPack) -> tuple[str, str]:
    system = load_prompt("wording_system", "v1").substitute(schema=_schema_json(WordingOutput))
    issues = lint(text).issues
    lint_block = ""
    if issues:
        lines = "\n".join(
            f'"{_as_data(issue.match)}" — {_as_data(issue.message)}' for issue in issues[:8]
        )
        lint_block = f"<lint>\n{lines}\n</lint>\n\n"
    user = load_prompt("wording_user", "v1").substitute(
        context_pack=_pack(pack.text), lint=lint_block, text=_as_data(text)
    )
    return system, user


def improve(
    text: str, *, llm: LLMClient, pack: ContextPack, project_id: uuid.UUID | None
) -> tuple[WordingSuggestion | None, int]:
    """The suggested rewrite (or ``None``) and the LLM calls it took. ``BudgetExceededError``
    propagates so the API can say the month's budget is spent."""
    system, user = build_messages(text, pack=pack)
    calls = 0
    for _ in range(ATTEMPTS):
        before = llm.calls
        try:
            output = llm.complete_json(system, user, WordingOutput, project_id=project_id)
        except LLMError as error:
            calls += llm.calls - before
            logger.info("No wording suggestion: %s", type(error).__name__)
            return None, calls
        calls += llm.calls - before
        found = problems(output, text, pack.text)
        if not found:
            return (
                WordingSuggestion(
                    original=text,
                    proposed=output.rewrite,
                    template=output.template,
                    changes=output.changes,
                    tbd_slots=output.tbd_slots,
                    model=llm.model,
                    lint_before=lint(text).score,
                    lint_after=lint(output.rewrite).score,
                ),
                calls,
            )
        logger.info("Wording suggestion rejected: %s", "; ".join(found))
        user += (
            "\n\nYour previous answer was rejected because it "
            + "; it ".join(found)
            + ". Answer again, following every rule."
        )
    return None, calls
