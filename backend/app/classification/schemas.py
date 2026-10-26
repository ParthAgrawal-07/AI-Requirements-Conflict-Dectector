"""schemas — Role 3: LLM Classification Pipeline"""

from enum import StrEnum

from pydantic import BaseModel, Field

# ── Shared input ──────────────────────────────────────────────────────────────


class RequirementInput(BaseModel):
    """A single requirement as the classifier sees it."""

    id: str = Field(description="Printed requirement ID or short stand-in.")
    text: str = Field(description="Full body text of the requirement.")


# ── Pair classification ──────────────────────────────────────────────────────


class PairCategory(StrEnum):
    conflicting = "Conflicting"
    duplicate = "Duplicate"
    dependent = "Dependent"
    none = "None"


class DependencyDirection(StrEnum):
    a_depends_on_b = "A_depends_on_B"
    b_depends_on_a = "B_depends_on_A"


class PairClassificationOutput(BaseModel):
    """Structured output returned by the pair-classification prompt."""

    category: PairCategory
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    evidence: list[str] = Field(default_factory=list, max_length=4)
    dependency_direction: DependencyDirection | None = None

    @property
    def is_issue(self) -> bool:
        """True when the model found a real issue (not ``None``)."""
        return self.category is not PairCategory.none


# ── Single-requirement classification ────────────────────────────────────────


class SingleCategory(StrEnum):
    ambiguous = "Ambiguous"
    incomplete = "Incomplete"
    none = "None"


class SingleClassificationOutput(BaseModel):
    """Structured output returned by the single-requirement prompt."""

    category: SingleCategory
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    vague_terms: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
