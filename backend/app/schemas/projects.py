"""Project schemas (Parth — US-24, FR-47)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import Project
from app.models.enums import ProjectStatus


def _clean_name(value: str) -> str:
    """Trim, and refuse a blank name. Trimming here means create and update store the same form."""
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("Name must not be blank")
    return cleaned


class ProjectSettings(BaseModel):
    """The tunable settings of a project (FR-47). All optional; unset means "database default".

    Unknown fields are rejected (422), notably ``status``: a project becomes active by confirming
    its context (US-60), never by sending a flag, and a silently ignored field would hide that.
    """

    model_config = ConfigDict(extra="forbid")

    similarity_threshold: float | None = Field(default=None, ge=0, le=1)
    confidence_threshold: float | None = Field(default=None, ge=0, le=1)
    llm_budget_monthly_calls: int | None = Field(default=None, ge=0, le=1_000_000)
    required_approvals: int | None = Field(default=None, ge=1, le=3)
    chat_detection_enabled: bool | None = None


class ProjectCreate(ProjectSettings):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return _clean_name(value)


class ProjectUpdate(ProjectSettings):
    """Partial update: send only the fields to change. ``description: null`` clears it."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        return None if value is None else _clean_name(value)

    @model_validator(mode="after")
    def _no_nulls_except_description(self) -> "ProjectUpdate":
        for field in self.model_fields_set - {"description"}:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    description: str | None
    status: ProjectStatus
    context_version: int
    # False while the project is in Setup: no analysis, composer or change requests (FR-103).
    analysis_enabled: bool
    similarity_threshold: float
    confidence_threshold: float
    llm_budget_monthly_calls: int
    required_approvals: int
    chat_detection_enabled: bool
    created_at: datetime

    @classmethod
    def from_model(cls, project: Project) -> "ProjectRead":
        return cls(
            id=project.id,
            workspace_id=project.workspace_id,
            name=project.name,
            description=project.description,
            status=project.status,
            context_version=project.context_version,
            analysis_enabled=project.status is ProjectStatus.ACTIVE,
            similarity_threshold=project.similarity_threshold,
            confidence_threshold=project.confidence_threshold,
            llm_budget_monthly_calls=project.llm_budget_monthly_calls,
            required_approvals=project.required_approvals,
            chat_detection_enabled=project.chat_detection_enabled,
            created_at=project.created_at,
        )
