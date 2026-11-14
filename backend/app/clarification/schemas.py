"""What the model must return for a clarification question (Madhav — US-09, FR-22).

The JSON Schema of :class:`ClarificationOutput` is embedded in ``prompts/clarify_v1_system.md``,
so the prompt and the validator cannot drift apart; anything that does not validate is re-asked
and never stored (FR-15).
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ClarificationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question: str = Field(
        min_length=15,
        max_length=300,
        description="One specific question naming the requirements by ID, ending with '?'",
    )
    addressed_to: Literal["owner", "stakeholders"] = Field(
        description="Who can answer: the requirement's owner, or the wider stakeholders"
    )
    requirement_ids: list[str] = Field(
        min_length=1, max_length=4, description="Every requirement ID the question names"
    )
