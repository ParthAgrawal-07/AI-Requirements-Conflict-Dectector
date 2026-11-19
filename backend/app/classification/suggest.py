"""AI resolution suggestions (Keval — US-51, US-45, FR-68; ADR-31)."""

import logging
import uuid
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from app.classification.budget import BudgetExceededError
from app.classification.context_pack import ContextPack
from app.classification.llm_client import LLMClient, LLMError, LLMOutputError
from app.classification.prompting import _schema_json, load_prompt
from app.classification.schemas import RequirementInput

logger = logging.getLogger(__name__)

SUGGEST_VERSION = "suggest-v1"
TBD = "[TBD"
ATTEMPTS = 2


@dataclass(frozen=True)
class Example:
    category: str
    action: str
    text: str


class SuggestOption(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    text: str = Field(min_length=1, description="The proposed rewritten or compromise wording")
    target: str | None = Field(
        default=None, description="The ID of the requirement replaced, e.g. REQ-012"
    )
    trade_off: str = Field(min_length=1, description="What is gained and lost by this option")
    confidence: float = Field(
        ge=0.0, le=1.0, description="Confidence in this resolution option, 0 to 1"
    )
    tbd_slots: list[str] = Field(
        default_factory=list, description="Placeholders that need human completion"
    )


class SuggestOutput(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    options: list[SuggestOption] = Field(
        min_length=1, max_length=3, description="Up to 3 resolution options"
    )


def propose(
    category: str,
    requirements: list[RequirementInput],
    explanation: str,
    *,
    llm: LLMClient,
    pack: ContextPack | None = None,
    project_id: uuid.UUID | None = None,
    instruction: str | None = None,
    examples: list[Example] | None = None,
) -> tuple[SuggestOutput | None, int]:
    """Ask the LLM for up to three resolution options for the finding."""
    system = load_prompt("suggest_system", "v1").substitute(schema=_schema_json(SuggestOutput))

    reqs_text = "\n".join(f"- {r.id}: {r.text}" for r in requirements)
    context_text = pack.text if pack and pack.text else ""
    examples_text = ""
    if examples:
        examples_text = "Past Project Decisions:\n" + "\n".join(
            f"- [{e.action}] {e.text}" for e in examples
        )
    instruction_text = f"Additional instruction: {instruction}" if instruction else ""

    user = load_prompt("suggest_user", "v1").substitute(
        category=category,
        explanation=explanation,
        requirements=reqs_text,
        context=context_text,
        examples=examples_text,
        instruction=instruction_text,
    )

    calls = 0
    for _ in range(ATTEMPTS):
        before = llm.calls
        try:
            output = llm.complete_json(
                system, user, SuggestOutput, project_id=project_id, retries=0
            )
        except BudgetExceededError:
            calls += llm.calls - before
            raise
        except LLMOutputError:
            calls += llm.calls - before
            continue
        except LLMError as error:
            calls += llm.calls - before
            logger.info("Suggestion generation failed: %s", type(error).__name__)
            return None, calls
        calls += llm.calls - before
        return output, calls

    return None, calls
