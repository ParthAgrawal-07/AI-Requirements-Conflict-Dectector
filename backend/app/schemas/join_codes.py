"""Join-code and join-request schemas (Madhav — US-25)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models import JoinCode, JoinCodeStatus, JoinRequest, JoinRequestStatus
from app.schemas.auth import RoleRef
from app.services.join_codes import effective_status


class JoinCodeCreate(BaseModel):
    role_id: uuid.UUID
    # Omit for a workspace-wide code; set to add the person to one project's team as well.
    project_id: uuid.UUID | None = None
    expires_in_days: Literal[1, 7, 30] = 7
    max_uses: int | None = Field(default=None, ge=1, le=10_000)
    requires_approval: bool = False


class JoinCodeRead(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    project_id: uuid.UUID | None
    code_hint: str  # last four characters, shown as "…4XPA"
    role: RoleRef
    expires_at: datetime
    max_uses: int | None
    uses: int
    requires_approval: bool
    status: JoinCodeStatus  # effective: an active code past its expiry reads "expired"
    created_by: uuid.UUID
    created_at: datetime
    revoked_at: datetime | None

    @classmethod
    def from_model(cls, code: JoinCode) -> "JoinCodeRead":
        return cls(
            id=code.id,
            workspace_id=code.workspace_id,
            project_id=code.project_id,
            code_hint=code.code_hint,
            role=RoleRef(id=code.role.id, name=code.role.name, is_default=code.role.is_default),
            expires_at=code.expires_at,
            max_uses=code.max_uses,
            uses=code.uses,
            requires_approval=code.requires_approval,
            status=effective_status(code),
            created_by=code.created_by,
            created_at=code.created_at,
            revoked_at=code.revoked_at,
        )


class JoinCodeCreated(JoinCodeRead):
    """Returned once, by ``POST``: the only time the full code is ever shown."""

    code: str


class JoinRequestBody(BaseModel):
    code: str = Field(min_length=1, max_length=32)


class JoinResult(BaseModel):
    status: Literal["joined", "pending_approval"]
    workspace_id: uuid.UUID
    project_id: uuid.UUID | None
    join_request_id: uuid.UUID | None = None


class JoinRequestUser(BaseModel):
    id: uuid.UUID
    full_name: str
    email: str


class JoinRequestRead(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    project_id: uuid.UUID | None
    join_code_id: uuid.UUID
    user: JoinRequestUser
    role: RoleRef
    status: JoinRequestStatus
    created_at: datetime
    decided_by: uuid.UUID | None
    decided_at: datetime | None

    @classmethod
    def from_model(cls, request: JoinRequest) -> "JoinRequestRead":
        return cls(
            id=request.id,
            workspace_id=request.workspace_id,
            project_id=request.project_id,
            join_code_id=request.join_code_id,
            user=JoinRequestUser(
                id=request.user.id, full_name=request.user.full_name, email=request.user.email
            ),
            role=RoleRef(
                id=request.role.id, name=request.role.name, is_default=request.role.is_default
            ),
            status=request.status,
            created_at=request.created_at,
            decided_by=request.decided_by,
            decided_at=request.decided_at,
        )


class JoinDecision(BaseModel):
    approve: bool
    # Approve with a different role than the code's (never Owner or Admin).
    role_id: uuid.UUID | None = None
