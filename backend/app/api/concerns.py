"""Raise a concern (Bansil — US-56, FR-97): ``POST /projects/{p}/concerns`` (``issue.open``).

Creates a person-sourced finding and its issue (``app.intake.concerns``); the answer carries both,
and whether the analysis had missed it.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import DbSession, requires
from app.core.errors import NotFoundError
from app.intake import concerns
from app.models import FindingCategory, Project, Severity
from app.schemas.common import ErrorResponse
from app.schemas.findings import FindingRead
from app.services import findings as finding_service
from app.services.access import AccessContext

router = APIRouter(tags=["findings"])


class ConcernCreate(BaseModel):
    # Stripped before the length checks, so ten spaces are not a ten-character explanation.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    category: FindingCategory
    requirement_ids: list[uuid.UUID] = Field(min_length=1, max_length=2)
    explanation: str = Field(min_length=10, max_length=4000)
    external_ref: str | None = Field(default=None, max_length=200)
    severity: Severity = Severity.MEDIUM


class ConcernRead(BaseModel):
    finding: FindingRead
    issue_id: uuid.UUID
    issue_key: str  # "ISS-4"
    ai_miss: bool  # neither the AI nor a rule had found it


@router.post(
    "/projects/{project_id}/concerns",
    response_model=ConcernRead,
    status_code=status.HTTP_201_CREATED,
    summary="Raise a concern: a finding by a person, with an issue to discuss it",
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
def raise_concern(
    project_id: uuid.UUID,
    body: ConcernCreate,
    ctx: Annotated[AccessContext, requires("issue.open")],
    db: DbSession,
) -> ConcernRead:
    project = db.get(Project, project_id)
    if project is None:  # cannot happen after require_permission; defensive
        raise NotFoundError("Project not found")
    concern = concerns.raise_concern(
        db,
        ctx,
        project,
        category=body.category,
        requirement_ids=body.requirement_ids,
        explanation=body.explanation,
        external_ref=body.external_ref,
        severity=body.severity,
    )
    view = finding_service.get_finding(db, concern.finding.id, ctx.user, ctx.workspace_id)
    return ConcernRead(
        finding=FindingRead.from_view(view),
        issue_id=concern.issue.id,
        issue_key=f"ISS-{concern.issue.number}",
        ai_miss=concern.finding.ai_miss,
    )
