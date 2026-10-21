"""The project brief schema (Bansil — FR-103, US-60; Sprint 0 contract with Keval).

A brief has nine *fields*. Four are required before a project can leave Setup; five are optional.
Each field maps to one or two columns of ``project_contexts`` (design update §12.1):

==================  ==============================  ==========  ===========================
Field               Label                           Required    Columns
==================  ==============================  ==========  ===========================
``purpose``         Purpose and problem             yes         ``purpose``
``scope``           Scope (in and out)              yes         ``scope_in``, ``scope_out``
``actors``          User classes and actors         yes         ``actors`` (list of names)
``environment``     Operating environment, domain   yes         ``environment``
``glossary``        Glossary                        no          ``glossary`` [{term, meaning}]
``constraints``     Constraints and assumptions     no          ``constraints``
``quality_goals``   Quality goals                   no          ``quality_goals``
``regulations``     Applicable regulations          no          ``regulations``
``references``      Reference links                 no          ``references`` [{title, url}]
==================  ==============================  ==========  ===========================

Every filled field has a status, ``ai_drafted`` (drafted from the initial SRS, FR-104) or
``confirmed`` (written or accepted by a person). The project becomes Active only when all four
required fields are filled **and** confirmed.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator

MAX_TEXT_CHARS = 4000
MAX_ACTORS = 30
MAX_GLOSSARY = 200
MAX_REFERENCES = 50


class BriefField(StrEnum):
    PURPOSE = "purpose"
    SCOPE = "scope"
    ACTORS = "actors"
    ENVIRONMENT = "environment"
    GLOSSARY = "glossary"
    CONSTRAINTS = "constraints"
    QUALITY_GOALS = "quality_goals"
    REGULATIONS = "regulations"
    REFERENCES = "references"


class FieldStatus(StrEnum):
    AI_DRAFTED = "ai_drafted"
    CONFIRMED = "confirmed"


@dataclass(frozen=True)
class BriefFieldSpec:
    field: BriefField
    label: str
    required: bool
    columns: tuple[str, ...]


BRIEF_FIELDS: tuple[BriefFieldSpec, ...] = (
    BriefFieldSpec(BriefField.PURPOSE, "Purpose and problem", True, ("purpose",)),
    BriefFieldSpec(BriefField.SCOPE, "Scope (in and out)", True, ("scope_in", "scope_out")),
    BriefFieldSpec(BriefField.ACTORS, "User classes and actors", True, ("actors",)),
    BriefFieldSpec(
        BriefField.ENVIRONMENT, "Operating environment and domain", True, ("environment",)
    ),
    BriefFieldSpec(BriefField.GLOSSARY, "Glossary", False, ("glossary",)),
    BriefFieldSpec(BriefField.CONSTRAINTS, "Constraints and assumptions", False, ("constraints",)),
    BriefFieldSpec(BriefField.QUALITY_GOALS, "Quality goals", False, ("quality_goals",)),
    BriefFieldSpec(BriefField.REGULATIONS, "Applicable regulations", False, ("regulations",)),
    BriefFieldSpec(BriefField.REFERENCES, "Reference links", False, ("references",)),
)
SPECS: Mapping[BriefField, BriefFieldSpec] = {spec.field: spec for spec in BRIEF_FIELDS}
REQUIRED_FIELDS: tuple[BriefField, ...] = tuple(s.field for s in BRIEF_FIELDS if s.required)
COLUMN_TO_FIELD: Mapping[str, BriefField] = {
    column: spec.field for spec in BRIEF_FIELDS for column in spec.columns
}
COLUMNS: tuple[str, ...] = tuple(COLUMN_TO_FIELD)


class GlossaryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    term: str = Field(min_length=1, max_length=80)
    meaning: str = Field(min_length=1, max_length=500)


class ReferenceLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    url: AnyHttpUrl | None = None


class BriefValues(BaseModel):
    """Brief content by column. ``None`` means "not given"; blank text counts as empty."""

    model_config = ConfigDict(extra="forbid")

    purpose: str | None = Field(default=None, max_length=MAX_TEXT_CHARS)
    scope_in: str | None = Field(default=None, max_length=MAX_TEXT_CHARS)
    scope_out: str | None = Field(default=None, max_length=MAX_TEXT_CHARS)
    actors: list[str] | None = Field(default=None, max_length=MAX_ACTORS)
    environment: str | None = Field(default=None, max_length=MAX_TEXT_CHARS)
    glossary: list[GlossaryEntry] | None = Field(default=None, max_length=MAX_GLOSSARY)
    constraints: str | None = Field(default=None, max_length=MAX_TEXT_CHARS)
    quality_goals: str | None = Field(default=None, max_length=MAX_TEXT_CHARS)
    regulations: str | None = Field(default=None, max_length=MAX_TEXT_CHARS)
    references: list[ReferenceLink] | None = Field(default=None, max_length=MAX_REFERENCES)

    @field_validator(
        "purpose", "scope_in", "scope_out", "environment", "constraints", "quality_goals",
        "regulations",
    )  # fmt: skip
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        return None if value is None else value.strip() or None

    @field_validator("actors")
    @classmethod
    def _actors(cls, actors: list[str] | None) -> list[str] | None:
        if actors is None:
            return None
        cleaned: list[str] = []
        for actor in actors:
            actor = " ".join(actor.split())
            if len(actor) > 120:
                raise ValueError("An actor name must be at most 120 characters")
            if actor and actor.casefold() not in {a.casefold() for a in cleaned}:
                cleaned.append(actor)
        return cleaned

    def to_columns(self) -> dict[str, Any]:
        """JSON-ready column values (what ``project_contexts`` stores)."""
        return self.model_dump(mode="json")


def is_filled(field: BriefField, values: BriefValues) -> bool:
    """Whether ``field`` has content. Scope needs both what is in and what is out (FR-103)."""
    return all(bool(getattr(values, column)) for column in SPECS[field].columns)


def missing_required(values: BriefValues, status: Mapping[str, str]) -> list[BriefField]:
    """Required fields that are empty or not yet confirmed, in display order."""
    return [
        field
        for field in REQUIRED_FIELDS
        if not is_filled(field, values) or status.get(field.value) != FieldStatus.CONFIRMED
    ]


def labels(fields: list[BriefField]) -> list[str]:
    return [SPECS[field].label for field in fields]
