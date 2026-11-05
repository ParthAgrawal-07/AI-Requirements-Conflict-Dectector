"""Workspace schemas (Parth — US-24)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.auth import RoleRef


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def _clean(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Name must not be blank")
        return cleaned


class WorkspaceUpdate(WorkspaceCreate):
    pass


class WorkspaceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    created_at: datetime


class WorkspaceMembershipRead(WorkspaceRead):
    """A workspace as listed for its member: includes the caller's role there."""

    role: RoleRef
    joined_at: datetime


class RoleRead(RoleRef):
    """A role the workspace can assign, with the permissions it holds (FR-48)."""

    description: str | None
    permissions: list[str]
    # False for Owner, Admin and any role holding their permissions (FR-44, SX-14).
    grantable_by_join_code: bool


class MemberUser(BaseModel):
    id: uuid.UUID
    full_name: str
    email: str


class MemberRead(BaseModel):
    """One row of the Members table (interface design §4.3)."""

    user: MemberUser
    role: RoleRef
    stakeholder_group: str | None
    joined_at: datetime


class MemberRoleUpdate(BaseModel):
    role_id: uuid.UUID


class ReassignmentRead(BaseModel):
    """Something a former member still owns (SX-11): an admin assigns it to someone else."""

    kind: Literal["requirement"]  # change requests and approvals join in Sprint 4
    id: uuid.UUID
    project_id: uuid.UUID
    label: str | None
    former_owner_id: uuid.UUID
    former_owner_name: str  # shown as "Riya (former member)"
