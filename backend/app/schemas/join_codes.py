"""Pydantic schemas for Join Codes and Join Requests (Role 4 / Role 5 — US-25)."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import JoinCodeStatus, JoinRequestStatus, Role


class RedemptionStatus(StrEnum):
    """Outcome status returned when a join code is redeemed."""

    JOINED = "joined"
    PENDING_APPROVAL = "pending_approval"


class JoinRedemptionResult(BaseModel):
    """Structured result returned by JoinCodeService.redeem for API routes and auth handoff."""

    model_config = ConfigDict(from_attributes=True, extra="forbid", str_strip_whitespace=True)

    status: RedemptionStatus = Field(
        description="Whether the user immediately joined or awaits approval"
    )
    workspace_id: uuid.UUID = Field(description="UUID of the workspace joined or requested")
    workspace_name: str | None = Field(
        default=None, description="Human-readable workspace name if available"
    )
    assigned_role: Role = Field(description="Role assigned or requested via the join code")
    user_id: uuid.UUID = Field(description="UUID of the user redeeming the code")
    join_request_id: uuid.UUID | None = Field(
        default=None, description="UUID of pending JoinRequest if approval is required"
    )
    message: str = Field(default="", description="Descriptive outcome message")


class JoinCodeCreate(BaseModel):
    """Payload to create a new workspace join code."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    role: Role = Field(
        default=Role.ANALYST,
        description="Role assigned to users redeeming this code (must not be admin)",
    )
    expires_at: datetime | None = Field(
        default=None, description="Optional future UTC timestamp when code expires"
    )
    max_uses: int | None = Field(
        default=None, gt=0, description="Optional maximum allowed redemptions (null = unlimited)"
    )
    requires_approval: bool = Field(
        default=False,
        description="If True, redemptions create pending requests rather than immediate membership",
    )

    @model_validator(mode="after")
    def _validate_role_safety(self) -> Self:
        # Inviolable security invariant: a join code must never grant admin privileges
        if self.role == Role.ADMIN or str(self.role).lower() in ("admin", "owner"):
            raise ValueError("Join codes cannot grant administrator or owner privileges")
        return self


class JoinCodeCreateResponse(BaseModel):
    """Response returned upon creation, containing the plaintext code disclosed ONCE."""

    model_config = ConfigDict(from_attributes=True, extra="forbid", str_strip_whitespace=True)

    id: uuid.UUID
    code: str = Field(
        description="The 8-character plaintext code formatted as XXXX-XXXX (disclosed once)"
    )
    workspace_id: uuid.UUID
    role: Role
    expires_at: datetime | None
    max_uses: int | None
    use_count: int
    status: JoinCodeStatus
    requires_approval: bool
    created_at: datetime


class JoinCodeRead(BaseModel):
    """Safe view of a join code for admin listings. Plaintext code is never included."""

    model_config = ConfigDict(from_attributes=True, extra="forbid", str_strip_whitespace=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    role: Role
    masked_code: str = Field(description="Masked code identifier (e.g. K9Q2****)")
    max_uses: int | None
    use_count: int
    expires_at: datetime | None
    status: JoinCodeStatus
    requires_approval: bool
    created_at: datetime


class JoinRequestRead(BaseModel):
    """Details of a pending or decided join request."""

    model_config = ConfigDict(from_attributes=True, extra="forbid", str_strip_whitespace=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    user_email: str | None = None
    user_full_name: str | None = None
    join_code_id: uuid.UUID
    status: JoinRequestStatus
    assigned_role: Role
    reviewed_by: uuid.UUID | None = None
    reviewed_at: datetime | None = None
    rejection_reason: str | None = None
    created_at: datetime


class JoinRedeemRequest(BaseModel):
    """Payload to redeem a join code."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    code: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Raw join code string submitted by user (e.g. K9Q2-7NWA)",
    )


class JoinRequestDecision(BaseModel):
    """Payload to approve or reject a pending join request."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    decision: Literal["approve", "reject"] = Field(
        ..., description="Decision action: 'approve' or 'reject'"
    )
    reason: str | None = Field(
        default=None, max_length=1000, description="Optional rejection reason"
    )
