"""The optional AI paragraph of a change-log summary (Keval — US-55, FR-96; ADR-31).

``app.graph.changelog.summary`` computes the counts and picks the important changes from the
stored change log. This module asks the LLM for **one paragraph about that result only** — the
counts and the template sentences, which name requirements by key and people by name; never
requirement text. It is shown labelled *AI*, under the exact numbers.

**It cites only listed events.** Every reply passes :func:`problems` before it is kept:

* every key it names (REQ-…, ISS-…, RCR-…) and every key it says it cites is in the summary;
* every number it writes is one of the counts.

A reply that breaks a rule is re-asked once with the reasons. If it still does, or the model is
unavailable or over budget, there is simply no paragraph: the summary stands on its own (the
counts and the list are the source of truth either way).
"""

import json
import logging
import re
import uuid
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.classification.budget import BudgetExceededError
from app.classification.llm_client import LLMClient, LLMError
from app.classification.prompting import _as_data, _schema_json, load_prompt
from app.graph import changelog

logger = logging.getLogger(__name__)

PROMPT_VERSION = "change-summary-v1"
ATTEMPTS = 2
_NUMBER = re.compile(r"(?<![\w.-])\d+(?![\w.-])")
_KEY = re.compile(r"\b[A-Z][A-Z0-9]*-\d+(?:\.\d+)*\b")


class SummaryParagraph(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    paragraph: str = Field(min_length=10, max_length=900, description="Two to four sentences")
    cited_keys: list[str] = Field(
        default_factory=list, description="Every REQ-/ISS-/RCR- key the paragraph names"
    )


@dataclass(frozen=True)
class Narrative:
    text: str
    cited_keys: list[str]
    provider: str | None
    model: str | None
    prompt_version: str = PROMPT_VERSION


def facts(summary: changelog.Summary) -> dict[str, Any]:
    """What the model sees: the counts and the important changes, as computed."""
    return {
        "since": summary.since_label,
        "counts": {k: v for k, v in summary.counts.items() if v},
        "total_changes_logged": summary.total_events,
        "important_changes": [{"kind": e.kind, "sentence": e.sentence} for e in summary.highlights],
    }


def problems(output: SummaryParagraph, summary: changelog.Summary) -> list[str]:
    """Why ``output`` is not supported by ``summary`` (empty when it is)."""
    found: list[str] = []
    allowed_keys = set(summary.keys)
    unknown = sorted({*_KEY.findall(output.paragraph), *output.cited_keys} - allowed_keys)
    if unknown:
        found.append(f"names keys that are not in the changes: {', '.join(unknown)}")
    allowed_numbers = {str(v) for v in summary.counts.values() if v} | {str(summary.total_events)}
    stray = sorted(set(_NUMBER.findall(output.paragraph)) - allowed_numbers)
    if stray:
        found.append(f"writes numbers that are not among the counts: {', '.join(stray)}")
    return found


def write(summary: changelog.Summary, *, llm: LLMClient, project_id: uuid.UUID) -> Narrative | None:
    """One checked paragraph about ``summary``, or ``None``."""
    system = load_prompt("change_summary_system", "v1").substitute(
        schema=_schema_json(SummaryParagraph)
    )
    user = load_prompt("change_summary_user", "v1").substitute(
        since_label=_as_data(summary.since_label),
        changes=_as_data(json.dumps(facts(summary), indent=2)),
    )
    for _ in range(ATTEMPTS):
        try:
            output = llm.complete_json(system, user, SummaryParagraph, project_id=project_id)
        except (BudgetExceededError, LLMError) as error:
            logger.info("No change summary paragraph: %s", type(error).__name__)
            return None
        reasons = problems(output, summary)
        if not reasons:
            provider, _, model = llm.model.partition("/")
            return Narrative(
                text=output.paragraph,
                cited_keys=sorted(set(output.cited_keys) | set(_KEY.findall(output.paragraph))),
                provider=provider or None,
                model=model or None,
            )
        logger.info("Change summary paragraph rejected: %s", "; ".join(reasons))
        user += (
            "\n\nYour previous answer was rejected because it "
            + "; it ".join(reasons)
            + ". Answer again, following every rule."
        )
    return None
