"""Workspace schemas (Parth — US-24)."""

import uuid
from datetime import datetime

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
