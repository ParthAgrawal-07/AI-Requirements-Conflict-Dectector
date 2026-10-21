"""Project context schemas (Bansil — US-60; design update §12.5)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.context.brief import (
    BRIEF_FIELDS,
    BriefField,
    BriefValues,
    FieldStatus,
    is_filled,
    labels,
    missing_required,
)
from app.context.service import values_of
from app.models import ProjectContext, ProjectStatus


class BriefFieldState(BaseModel):
    """One row of the setup wizard's context step (interface design §8c)."""

    field: BriefField
    label: str
    required: bool
    filled: bool
    # null when the field is empty; ``ai_drafted`` until a person confirms or edits it.
    status: FieldStatus | None


class ContextVersionRead(BaseModel):
    version: int
    values: BriefValues
    field_status: dict[str, FieldStatus]
    summary: str | None
    source_document_id: uuid.UUID | None
    created_by: uuid.UUID | None
    reason: str | None
    created_at: datetime

    @classmethod
    def from_model(cls, context: ProjectContext) -> "ContextVersionRead":
        return cls(
            version=context.version,
            values=values_of(context),
            field_status={k: FieldStatus(v) for k, v in context.field_status.items()},
            summary=context.summary,
            source_document_id=context.source_document_id,
            created_by=context.created_by,
            reason=context.reason,
            created_at=context.created_at,
        )


class ProjectContextRead(BaseModel):
    """``GET /projects/{p}/context``: the newest version and what Setup still needs."""

    project_id: uuid.UUID
    project_status: ProjectStatus
    # The version analysis uses (``projects.context_version``); 0 while in Setup.
    context_version: int
    # The newest version, confirmed or not; null before anything was saved or drafted.
    latest: ContextVersionRead | None
    fields: list[BriefFieldState]
    # Labels of the required fields still empty or unconfirmed — the Setup banner's message.
    missing_fields: list[str]
    required_confirmed: int
    required_total: int

    @classmethod
    def build(
        cls,
        *,
        project_id: uuid.UUID,
        project_status: ProjectStatus,
        context_version: int,
        latest: ProjectContext | None,
    ) -> "ProjectContextRead":
        latest_read = ContextVersionRead.from_model(latest) if latest is not None else None
        values = latest_read.values if latest_read else BriefValues()
        status = latest_read.field_status if latest_read else {}
        states = [
            BriefFieldState(
                field=spec.field,
                label=spec.label,
                required=spec.required,
                filled=is_filled(spec.field, values),
                status=status.get(spec.field.value),
            )
            for spec in BRIEF_FIELDS
        ]
        missing = missing_required(values, status)
        required_total = sum(spec.required for spec in BRIEF_FIELDS)
        return cls(
            project_id=project_id,
            project_status=project_status,
            context_version=context_version,
            latest=latest_read,
            fields=states,
            missing_fields=labels(missing),
            required_confirmed=required_total - len(missing),
            required_total=required_total,
        )


class ContextUpdate(BaseModel):
    """``PUT /projects/{p}/context``.

    ``fields`` holds only the columns to change (``null`` clears one); editing a field confirms
    it. ``confirm`` accepts AI-drafted fields as they are. ``reason`` is required once the
    project is active.
    """

    model_config = ConfigDict(extra="forbid")

    fields: BriefValues = Field(default_factory=BriefValues)
    confirm: list[BriefField] = Field(default_factory=list, max_length=len(BriefField))
    reason: str | None = Field(default=None, max_length=500)


class ContextSaveResult(BaseModel):
    context: ProjectContextRead
    # False when the request changed nothing (no new version).
    created: bool
    # True when this save confirmed the last required field and the project became Active.
    activated: bool
    # After an edit of an active project's context: open findings that could be re-run with
    # the new context (the UI offers "Re-run analysis of N open findings?"). 0 in Setup.
    open_findings_to_rerun: int


class ContextDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: uuid.UUID


class ContextDraftResult(BaseModel):
    context: ProjectContextRead
    # False when the document added nothing to fields nobody has confirmed.
    drafted: bool
