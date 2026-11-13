"""Classifier (Keval — US-05, US-07).

Takes a candidate pair (or one requirement), builds the prompt with the project context pack and
the per-category sections (``prompts/<category>_v1.txt``), calls
:class:`~app.classification.llm_client.LLMClient` and returns the validated output — one of the
five categories or ``None`` (no issue). An invalid reply is re-asked up to ``LLM_OUTPUT_RETRIES``
times (3) before :class:`~app.classification.llm_client.LLMOutputError`.

The same two calls serve a whole document (``app.classification.tasks``) and, from Sprint 3, one
requirement against the baseline (US-31) and a proposed change (US-34): only the candidates differ.

Pure with respect to the database: callers load the requirements and the pack and decide what to
store (``app.classification.tasks`` for document analysis; the live analyzer in Sprint 3).
"""

import uuid

from app.classification.context_pack import ContextPack
from app.classification.llm_client import LLMClient
from app.classification.prompting import build_pair_messages, build_single_messages
from app.classification.schemas import (
    PairClassificationOutput,
    RequirementInput,
    SingleClassificationOutput,
)
from app.core.config import get_settings
from app.models import Requirement

EMPTY_PACK = ContextPack(context_version=None, text="")


def as_input(requirement: Requirement) -> RequirementInput:
    """The requirement as the model sees it: its printed ID, or a short stable stand-in."""
    label = requirement.source_req_id or f"item-{str(requirement.id)[:8]}"
    return RequirementInput(id=label, text=requirement.body)


class Classifier:
    def __init__(self, llm: LLMClient, *, retries: int | None = None) -> None:
        self._llm = llm
        self._retries = get_settings().llm_output_retries if retries is None else retries

    def classify_pair(
        self,
        a: RequirementInput,
        b: RequirementInput,
        *,
        pack: ContextPack = EMPTY_PACK,
        project_id: uuid.UUID | None = None,
    ) -> PairClassificationOutput:
        system, user = build_pair_messages(a, b, context_pack=pack.text)
        return self._llm.complete_json(
            system, user, PairClassificationOutput, project_id=project_id, retries=self._retries
        )

    def classify_single(
        self,
        requirement: RequirementInput,
        *,
        pack: ContextPack = EMPTY_PACK,
        project_id: uuid.UUID | None = None,
    ) -> SingleClassificationOutput:
        system, user = build_single_messages(requirement, context_pack=pack.text)
        return self._llm.complete_json(
            system, user, SingleClassificationOutput, project_id=project_id, retries=self._retries
        )
