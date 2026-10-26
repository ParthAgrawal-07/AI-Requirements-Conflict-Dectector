"""Classifier skeleton (Keval — US-05 groundwork, Sprint 1).

Takes a candidate pair (or one requirement), builds the prompt with the project context pack,
calls :class:`~app.classification.llm_client.LLMClient` and returns the validated output — one of
the five categories or ``None`` (no issue). Storing findings, the per-category prompts and the
explanations of US-07 come in Sprint 2; this is the part every one of those builds on.

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
from app.models import Requirement

EMPTY_PACK = ContextPack(context_version=None, text="")


def as_input(requirement: Requirement) -> RequirementInput:
    """The requirement as the model sees it: its printed ID, or a short stable stand-in."""
    label = requirement.source_req_id or f"item-{str(requirement.id)[:8]}"
    return RequirementInput(id=label, text=requirement.body)


class Classifier:
    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

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
            system, user, PairClassificationOutput, project_id=project_id
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
            system, user, SingleClassificationOutput, project_id=project_id
        )
