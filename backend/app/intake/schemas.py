"""Composer field schema and the requirement draft (Bansil with Pranshu — FR-55, FR-81).

Sprint 0 contract. A composer post carries :class:`ComposerFields`; the private draft that
autosaves every 5 s (interface design §5.2) stores the same fields, all optional, as
``requirement_drafts.fields`` (jsonb, migration ``0006``, Sprint 2–3):

.. code-block:: json

    {
      "template": "event_driven",
      "slots": {"trigger": "the user is inactive for 5 minutes",
                "system": "mobile app", "response": "log the user out"},
      "type": "functional", "priority": "must",
      "stakeholder_group": "Security", "owner_id": null, "tags": ["session"],
      "rationale": "RBI guideline on idle sessions",
      "acceptance_criteria": [{"given": "a logged-in user", "when": "no input for 5 min",
                               "then": "the session ends and the login screen is shown"}],
      "channel_id": null
    }

The stored requirement ``body`` is :func:`app.intake.ears.render_statement` of the template and
slots — the preview the member saw — and is never rewritten afterwards (FR-04).
"""

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.intake.ears import EarsTemplate, MissingSlotsError, render_statement

MAX_SLOT_CHARS = 500
MAX_STATEMENT_CHARS = 4000


class RequirementType(StrEnum):
    FUNCTIONAL = "functional"
    NON_FUNCTIONAL = "non_functional"
    CONSTRAINT = "constraint"


class Priority(StrEnum):
    """MoSCoW (FR-55)."""

    MUST = "must"
    SHOULD = "should"
    COULD = "could"
    WONT = "wont"


class AcceptanceCriterion(BaseModel):
    """One Given/When/Then criterion (FR-81)."""

    model_config = ConfigDict(extra="forbid")

    given: str = Field(min_length=1, max_length=500)
    when: str = Field(min_length=1, max_length=500)
    then: str = Field(min_length=1, max_length=500)


class _FieldsBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slots: dict[str, str] = Field(default_factory=dict, max_length=6)
    stakeholder_group: str | None = Field(default=None, max_length=120)
    owner_id: uuid.UUID | None = None
    tags: list[str] = Field(default_factory=list, max_length=10)
    rationale: str | None = Field(default=None, max_length=2000)
    acceptance_criteria: list[AcceptanceCriterion] = Field(default_factory=list, max_length=10)
    # Where the requirement card is posted; null = the group's channel (interface design §5.2).
    channel_id: uuid.UUID | None = None

    @field_validator("slots")
    @classmethod
    def _slot_lengths(cls, slots: dict[str, str]) -> dict[str, str]:
        for key, value in slots.items():
            limit = MAX_STATEMENT_CHARS if key == "statement" else MAX_SLOT_CHARS
            if len(value) > limit:
                raise ValueError(f"Slot '{key}' is longer than {limit} characters")
        return slots

    @field_validator("tags")
    @classmethod
    def _tags(cls, tags: list[str]) -> list[str]:
        cleaned = []
        for tag in tags:
            tag = tag.strip()
            if not tag or len(tag) > 40:
                raise ValueError("Tags must be 1–40 characters")
            if tag not in cleaned:
                cleaned.append(tag)
        return cleaned


class ComposerFields(_FieldsBase):
    """What *Propose requirement* sends (FR-55, FR-81). Every required field is checked here."""

    template: EarsTemplate
    type: RequirementType
    priority: Priority

    @model_validator(mode="after")
    def _slots_complete(self) -> "ComposerFields":
        try:
            render_statement(self.template, self.slots)
        except MissingSlotsError as error:
            raise ValueError(str(error)) from None
        return self

    @property
    def statement(self) -> str:
        return render_statement(self.template, self.slots)


class DraftFields(_FieldsBase):
    """A draft autosaves whatever is filled in so far, so every field is optional."""

    template: EarsTemplate | None = None
    type: RequirementType | None = None
    priority: Priority | None = None


class RequirementDraftRead(BaseModel):
    """``GET /me/drafts`` item. Drafts are private to their author (FR-81)."""

    id: uuid.UUID
    project_id: uuid.UUID
    fields: DraftFields
    # Preview of the sentence, or null while slots are still empty.
    preview: str | None
    updated_at: datetime

    @classmethod
    def build(
        cls, *, id: uuid.UUID, project_id: uuid.UUID, fields: DraftFields, updated_at: datetime
    ) -> "RequirementDraftRead":
        preview = None
        if fields.template is not None:
            try:
                preview = render_statement(fields.template, fields.slots)
            except MissingSlotsError:
                preview = None
        return cls(
            id=id, project_id=project_id, fields=fields, preview=preview, updated_at=updated_at
        )
