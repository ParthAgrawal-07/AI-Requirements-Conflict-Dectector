"""Suggestion API schemas (Madhav — US-45; contract ``{options:[{text, trade_off, confidence,
tbd_slots}]}`` agreed with Keval, Abhijeet and Bansil)."""

import uuid
from datetime import datetime
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from app.models import User
from app.models.suggestion import Suggestion, SuggestionFeedback

Status = Literal["pending", "waiting_budget", "ready", "failed", "superseded"]
Action = Literal[
    "accepted",
    "accepted_edited",
    "rejected_meaning",
    "rejected_infeasible",
    "rejected_missing_context",
    "deferred",
    "regenerate",
    "prefer",
    "rate_up",
    "rate_down",
]


class OptionRead(BaseModel):
    text: str
    target: str | None  # printed ID of the requirement the wording replaces
    target_requirement_id: uuid.UUID | None
    trade_off: str
    confidence: float
    tbd_slots: list[str]


class Preference(BaseModel):
    user_id: uuid.UUID
    full_name: str
    option_index: int


class SuggestionRead(BaseModel):
    id: uuid.UUID
    finding_id: uuid.UUID
    category: str
    status: Status
    label: str = "AI"
    options: list[OptionRead]
    instruction: str | None
    prompt_version: str | None
    model: str | None
    error: str | None
    preferences: list[Preference]
    my_outcome: str | None  # the caller's latest of the six outcomes, if any
    created_at: datetime
    ready_at: datetime | None

    @classmethod
    def build(
        cls,
        row: Suggestion,
        preferences: list[tuple[User, int]],
        my_outcome: str | None,
    ) -> "SuggestionRead":
        return cls(
            id=row.id,
            finding_id=row.finding_id,
            category=row.category,
            status=cast(Status, row.status),  # CHECK-constrained column
            options=[OptionRead.model_validate(option) for option in row.options],
            instruction=row.instruction,
            prompt_version=row.prompt_version,
            model=row.model,
            error=row.error,
            preferences=[
                Preference(user_id=u.id, full_name=u.full_name, option_index=i)
                for u, i in preferences
            ],
            my_outcome=my_outcome,
            created_at=row.created_at,
            ready_at=row.ready_at,
        )


class FeedbackCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Action
    option_index: int | None = Field(default=None, ge=0, le=2)
    final_text: str | None = Field(default=None, max_length=4000)
    reason: str | None = Field(default=None, max_length=1000)
    instruction: str | None = Field(default=None, max_length=500)


class RegenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instruction: str = Field(min_length=3, max_length=500)


class RatingCreate(BaseModel):
    """An analyst's correctness rating of one option (the CP2 study, NFR-36)."""

    model_config = ConfigDict(extra="forbid")

    option_index: int = Field(ge=0, le=2)
    rating: int = Field(ge=1, le=5)
    note: str | None = Field(default=None, max_length=1000)


class FeedbackRead(BaseModel):
    id: uuid.UUID
    suggestion_id: uuid.UUID
    action: str
    option_index: int | None
    created_at: datetime

    @classmethod
    def build(cls, row: SuggestionFeedback) -> "FeedbackRead":
        return cls(
            id=row.id,
            suggestion_id=row.suggestion_id,
            action=row.action,
            option_index=row.option_index,
            created_at=row.created_at,
        )


class PrefillRead(BaseModel):
    kind: Literal["change_request", "post"]
    requirement_id: uuid.UUID
    proposed_body: str
    source_suggestion_id: uuid.UUID
    finding_id: uuid.UUID
    issue_id: uuid.UUID | None
    issue_number: int | None
    tbd_slots: list[str]


class FeedbackResponse(BaseModel):
    feedback: FeedbackRead
    prefill: PrefillRead | None = None  # after an acceptance: what the change editor opens with
    suggestion: SuggestionRead | None = None  # after a regeneration: the new, pending one


class CategoryStats(BaseModel):
    category: str
    outcomes: dict[str, int]
    expert_ratings: int
    expert_mean: float | None


class SuggestionStats(BaseModel):
    suggestions: int
    by_status: dict[str, int]
    regenerations: int
    outcomes_total: int
    acceptance_rate: float | None
    categories: list[CategoryStats]
    expert_ratings: int
    expert_correct_share: float | None
    latency_p90_seconds: float | None
    deferred: int
