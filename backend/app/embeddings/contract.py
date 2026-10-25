"""Live-analysis retrieval contract (Heet with Keval — agreed in Sprint 0, built in Sprint 3).

``IncrementalAnalyzer.analyse_text`` is what the composer's pre-flight check (US-51), a posted
requirement (US-31) and Madhav's impact engine (US-11) call to analyse **one** piece of text
against a project:

1. embed the text (``app.embeddings.model``);
2. retrieve the top-*k* requirements of the project above its ``similarity_threshold``
   (``app.embeddings.store.nearest_requirements``) — the agreed baseline only for posts (US-31);
3. classify each candidate pair, plus the text alone for Ambiguous/Incomplete (Keval);
4. return the results, most severe first. Nothing is stored: the caller decides (a post stores
   findings, a pre-flight check does not).

:class:`SimilarHint` is the cheap half (steps 1–2 only) behind the composer's "similar
requirements" panel; ``eval/latency/hints_bench.py`` measures it (target under 500 ms).

Until Sprint 3, :class:`FixtureAnalyzer` stands in: it returns what it was given, so consumers can
build against the contract (hand-off table: "Returns fixture findings").
"""

import uuid
from collections.abc import Sequence
from typing import Protocol

from pydantic import BaseModel, Field

from app.models.enums import FindingCategory


class SimilarHint(BaseModel):
    requirement_id: uuid.UUID
    label: str | None  # printed ID, e.g. "REQ-014"
    similarity: float = Field(ge=-1, le=1)


class ClassificationResult(BaseModel):
    """One finding about the analysed text. Not stored by the analyzer."""

    category: FindingCategory
    # The existing requirement it relates to; None for Ambiguous/Incomplete about the text itself.
    other_requirement_id: uuid.UUID | None
    confidence: float = Field(ge=0, le=1)
    rationale: str
    similarity: float | None = None  # retrieval score of the pair, when there is one
    evidence: list[str] = Field(default_factory=list)
    context_version: int | None = None  # the project context the classifier was given (FR-105)


class IncrementalAnalyzer(Protocol):
    def similar(self, project_id: uuid.UUID, text: str, *, k: int = 5) -> list[SimilarHint]: ...

    def analyse_text(
        self,
        project_id: uuid.UUID,
        text: str,
        *,
        exclude_requirement_id: uuid.UUID | None = None,
    ) -> list[ClassificationResult]: ...


class FixtureAnalyzer:
    """Returns canned results — the stub consumers use until the real analyzer lands (S3)."""

    def __init__(
        self,
        hints: Sequence[SimilarHint] = (),
        results: Sequence[ClassificationResult] = (),
    ) -> None:
        self._hints = list(hints)
        self._results = list(results)

    def similar(self, project_id: uuid.UUID, text: str, *, k: int = 5) -> list[SimilarHint]:
        return self._hints[:k]

    def analyse_text(
        self,
        project_id: uuid.UUID,
        text: str,
        *,
        exclude_requirement_id: uuid.UUID | None = None,
    ) -> list[ClassificationResult]:
        return list(self._results)
