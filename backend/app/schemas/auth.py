"""Auth request/response schemas (Role 5)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import Membership
from app.models.enums import PlatformRole


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 — OAuth2 scheme name, not a secret
    expires_in: int  # seconds until the token expires


class UserRead(BaseModel):
    """Public view of a user. Never includes the password hash."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    platform_role: PlatformRole | None
    is_active: bool
    created_at: datetime


class RoleRef(BaseModel):
    id: uuid.UUID
    name: str
    is_default: bool


class MembershipRead(BaseModel):
    """One workspace the user belongs to, with their role there (FR-46)."""

    workspace_id: uuid.UUID
    workspace_name: str
    role: RoleRef
    joined_at: datetime

    @classmethod
    def from_model(cls, membership: Membership) -> "MembershipRead":
        return cls(
            workspace_id=membership.workspace_id,
            workspace_name=membership.workspace.name,
            role=RoleRef(
                id=membership.role.id,
                name=membership.role.name,
                is_default=membership.role.is_default,
            ),
            joined_at=membership.joined_at,
        )


class MeRead(UserRead):
    """``GET /auth/me``: the user plus every workspace they belong to (for the switcher)."""

    memberships: list[MembershipRead]


class SignupRequest(BaseModel):
    """There is no open sign-up: a valid join code is part of the request (SX-02, US-19)."""

    email: EmailStr
    password: str = Field(min_length=1, max_length=256)  # policy is checked by the service
    full_name: str = Field(min_length=1, max_length=200)
    code: str = Field(min_length=1, max_length=64, description="Join code or invite-link token")


class SignupResponse(TokenResponse):
    user: UserRead
    # joined: a membership was created now. pending_approval: a manager must approve the join
    # request first (FR-77); the account exists and can sign in, but has no workspace yet.
    join_status: Literal["joined", "pending_approval"]
    workspace_id: uuid.UUID | None = None
