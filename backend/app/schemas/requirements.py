"""Requirement detail and lifecycle schemas (Parth — US-37, US-10; the requirement drawer).

``GET /requirements/{id}`` returns :class:`RequirementDetail`: the list row plus what the drawer
needs — the composer fields, the moves the caller may make (buttons appear only for those) and,
for approval, what is still missing (:class:`ReadinessRead`).
"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import Requirement, RequirementState, RequirementTransition
from app.schemas.documents import RequirementRead
from app.services.lifecycle import Readiness


class ReadinessRead(BaseModel):
    """What stands between this requirement and approval (FR-98)."""

    analysis_current: bool
    open_high_findings: list[uuid.UUID]
    needs_signoff: bool


class TransitionRead(BaseModel):
    from_state: RequirementState
    to_state: RequirementState
    version: int
    actor_id: uuid.UUID
    reason: str | None
    accepted_risk: bool
    created_at: datetime

    @classmethod
    def from_model(cls, row: RequirementTransition) -> "TransitionRead":
        return cls(
            from_state=row.from_state,
            to_state=row.to_state,
            version=row.version,
            actor_id=row.actor_id,
            reason=row.reason,
            accepted_risk=row.accepted_risk,
            created_at=row.created_at,
        )


class RequirementDetail(RequirementRead):
    req_type: str | None
    priority: str | None
    rationale: str | None
    acceptance_criteria: list[dict[str, Any]]
    tags: list[str]
    origin_message_id: uuid.UUID | None
    signed_off_version: int | None
    allowed_transitions: list[RequirementState]
    readiness: ReadinessRead
    transitions: list[TransitionRead]

    @classmethod
    def build(
        cls,
        requirement: Requirement,
        *,
        allowed: list[RequirementState],
        readiness: Readiness,
        transitions: list[RequirementTransition],
    ) -> "RequirementDetail":
        fields: dict[str, Any] = requirement.composer_fields or {}
        return cls(
            **RequirementRead.from_model(requirement).model_dump(),
            req_type=requirement.req_type,
            priority=requirement.priority,
            rationale=fields.get("rationale"),
            acceptance_criteria=list(fields.get("acceptance_criteria") or []),
            tags=list(fields.get("tags") or []),
            origin_message_id=requirement.origin_message_id,
            signed_off_version=requirement.signed_off_version,
            allowed_transitions=allowed,
            readiness=ReadinessRead(
                analysis_current=readiness.analysis_current,
                open_high_findings=readiness.open_high_findings,
                needs_signoff=readiness.needs_signoff,
            ),
            transitions=[TransitionRead.from_model(t) for t in transitions],
        )


class RequirementUpdate(BaseModel):
    """``PATCH /requirements/{id}``: a lifecycle move and/or a new owner or stakeholder group
    (US-36). Text never changes here — that is a change request (US-33). Send only what changes;
    ``"stakeholder_group": null`` clears the group."""

    model_config = ConfigDict(extra="forbid")

    owner_id: uuid.UUID | None = None
    stakeholder_group: str | None = Field(default=None, max_length=120)
    state: RequirementState | None = None
    # The version the caller read and decided on (FR-98); required with ``state``.
    version: int | None = Field(default=None, ge=1)
    reason: str | None = Field(default=None, max_length=2000)
    # Approve although a High-severity finding is open; needs a ``reason``.
    accepted_risk: bool = False

    @model_validator(mode="after")
    def _version_with_state(self) -> "RequirementUpdate":
        if self.state is not None and self.version is None:
            raise ValueError("Give the version you reviewed with a state change")
        return self


class SignOffRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)


# ── Ownership requests (Bansil — US-36, FR-59) ──────────────────────────────────────────────
class OwnershipRequestCreate(BaseModel):
    """``POST /requirements/{id}/ownership-requests``: ask to own a requirement."""

    model_config = ConfigDict(extra="forbid")

    note: str | None = Field(default=None, max_length=2000)


class OwnershipDecision(BaseModel):
    """``POST /ownership-requests/{id}/decision``: the owner or a manager accepts or declines."""

    model_config = ConfigDict(extra="forbid")

    accept: bool


class OwnershipRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    requirement_id: uuid.UUID
    requester_id: uuid.UUID
    status: str
    note: str | None
    decided_by: uuid.UUID | None
    decided_at: datetime | None
    created_at: datetime
