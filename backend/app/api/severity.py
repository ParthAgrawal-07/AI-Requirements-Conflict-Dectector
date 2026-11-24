"""Severity override route (Keval — US-08, FR-42).

``PATCH /findings/{finding_id}/severity`` (``finding.review``) — set Low, Medium or High with a
reason. The system's proposal stays on the finding (``severity_proposed``) and the change is
audited. A finding about a **protected** requirement is changed only by a compliance reviewer —
the same guard as every other review action (US-10, CR-19).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import DbSession, requires
from app.classification import severity as severity_rules
from app.core.errors import ForbiddenError, NotFoundError
from app.models import Finding, Severity
from app.schemas.common import ErrorResponse
from app.schemas.findings import FindingRead
from app.services import findings as finding_service
from app.services.access import AccessContext
from app.services.review_state import involved_requirements, may_review

router = APIRouter(tags=["findings"])


class SeverityUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: Severity
    reason: str = Field(min_length=1, max_length=severity_rules.MAX_REASON)


@router.patch(
    "/findings/{finding_id}/severity",
    response_model=FindingRead,
    summary="Override a finding's severity with a reason (the proposal is kept)",
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse, "description": "Protected: compliance reviewers only"},
        404: {"model": ErrorResponse},
    },
)
def set_severity(
    finding_id: uuid.UUID,
    body: SeverityUpdate,
    ctx: Annotated[AccessContext, requires("finding.review", allow_protected_only=True)],
    db: DbSession,
) -> FindingRead:
    finding = db.get(Finding, finding_id)
    if finding is None:  # defensive: the access layer resolved it
        raise NotFoundError("Finding not found")
    protected = any(r.is_protected for r in involved_requirements(db, finding))
    if not may_review(ctx, protected=protected):
        raise ForbiddenError(
            "A finding about a protected requirement needs a compliance reviewer"
            if protected
            else "You may not review findings"
        )
    severity_rules.override(db, finding, ctx.user, body.severity, body.reason)
    return FindingRead.from_view(
        finding_service.get_finding(db, finding_id, ctx.user, ctx.workspace_id)
    )
