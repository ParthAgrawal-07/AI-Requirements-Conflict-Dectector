"""Pydantic schemas for the LLM classification pipeline (Role 3).

The classifier makes two kinds of LLM call, mirroring the two kinds of ``Finding``
(see ``app/models/analysis.py``):

* **Pairwise** — a candidate pair from the embedding pre-filter is classified as
  Conflicting / Duplicate / Dependent, or ``None`` (no issue).
* **Single** — one requirement on its own is classified as Ambiguous / Incomplete,
  or ``None``.

The ``*Output`` models are the contract for what the LLM must return. Their JSON Schema is
embedded in the prompts (see ``prompting.py``), so the prompt and the validator can never
drift apart. Anything that doesn't validate is rejected rather than stored (FR-15).

Category strings match ``FindingCategory`` values and the labels in
``sample_docs/planted_conflicts/srs_v1_labels.json`` exactly, including ``"None"``.
"""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import FindingCategory

PairCategory = Literal["Conflicting", "Duplicate", "Dependent", "None"]
SingleCategory = Literal["Ambiguous", "Incomplete", "None"]

# "None" means "no issue found" — it never becomes a Finding row.
NO_ISSUE = "None"


class RequirementInput(BaseModel):
    """One requirement as it is sent to the LLM."""

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    id: str = Field(
        min_length=1, description="Requirement ID from the source document, e.g. REQ-001"
    )
    text: str = Field(min_length=1, description="The requirement text, verbatim")


class _ClassificationOutput(BaseModel):
    """Fields shared by both kinds of LLM output."""

    # extra="forbid": an LLM that invents fields is not following the schema, and we'd
    # rather retry than silently drop data we didn't ask for.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    category: str  # narrowed to a Literal by each subclass
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="How confident you are that the chosen category is correct, from 0 to 1",
    )
    rationale: str = Field(
        min_length=1,
        max_length=1000,
        description=(
            "1-3 plain-language sentences explaining the decision to a business analyst. "
            "Refer to requirements by their IDs."
        ),
    )

    @property
    def is_issue(self) -> bool:
        return self.category != NO_ISSUE

    @property
    def finding_category(self) -> FindingCategory | None:
        """The category to store on a ``Finding``, or ``None`` if no issue was found."""
        return FindingCategory(self.category) if self.is_issue else None


class PairClassificationOutput(_ClassificationOutput):
    """What the LLM returns for a candidate pair (requirements A and B)."""

    category: PairCategory = Field(description="The relationship between requirement A and B")
    dependency_direction: Literal["A_depends_on_B", "B_depends_on_A"] | None = Field(
        default=None,
        description="Required when category is Dependent, otherwise null",
    )
    evidence: list[str] = Field(
        default_factory=list,
        max_length=4,
        description="Short verbatim quotes from A and/or B that support the decision",
    )

    @model_validator(mode="after")
    def _direction_only_for_dependent(self) -> Self:
        if self.category == "Dependent" and self.dependency_direction is None:
            raise ValueError("dependency_direction is required when category is Dependent")
        if self.category != "Dependent" and self.dependency_direction is not None:
            raise ValueError("dependency_direction must be null unless category is Dependent")
        return self


class SingleClassificationOutput(_ClassificationOutput):
    """What the LLM returns for a single requirement."""

    category: SingleCategory = Field(description="The issue with this requirement, if any")
    vague_terms: list[str] = Field(
        default_factory=list,
        description="Ambiguous only: the exact vague words or phrases, quoted verbatim",
    )
    missing_information: list[str] = Field(
        default_factory=list,
        description="Incomplete only: each fact a developer or tester would need but is missing",
    )

    @model_validator(mode="after")
    def _details_match_category(self) -> Self:
        # DR-07: an Ambiguous flag must point at concrete wording, not a general feeling.
        if self.category == "Ambiguous" and not self.vague_terms:
            raise ValueError("vague_terms must list at least one term when category is Ambiguous")
        if self.category == "Incomplete" and not self.missing_information:
            raise ValueError(
                "missing_information must list at least one item when category is Incomplete"
            )
        return self
