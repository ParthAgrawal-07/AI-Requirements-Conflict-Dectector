"""Impact and consequence routes (Madhav — US-11, US-34, FR-24, FR-25, FR-64, FR-99).

* ``GET /requirements/{id}/impact`` (``view``) — who and what a change to the requirement would
  touch, before a request is written (the change editor's side panel). No LLM.
* ``GET /change-requests/{id}/checks`` (``view``) — the newest consequence report: ``pending``
  while none exists, ``stale`` when the requirement, the proposal or the baseline moved on since.
* ``POST /change-requests/{id}/checks/rerun`` (``rcr.review``) — queue the checks again, **202**.
"""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel

from app.api.change_requests import ERRORS, change_request_or_404
from app.api.deps import DbSession, requires
from app.consequences import tasks as consequence_tasks
from app.consequences.impact import ImpactAnalyzer, label
from app.core.errors import ConflictError, NotFoundError
from app.models import Project, Requirement
from app.models.change_request import ACTIVE
from app.services.access import AccessContext

router = APIRouter(tags=["change requests"])


class AffectedRead(BaseModel):
    requirement_id: uuid.UUID
    label: str
    depth: int
    relation: str
    reason: str
    status: Literal["confirmed", "potential"]
    owner_id: uuid.UUID | None
    stakeholder_group: str | None
    is_protected: bool
    finding_id: uuid.UUID | None
    path: list[str]


class ImpactRead(BaseModel):
    requirement_id: uuid.UUID
    label: str
    affected: list[AffectedRead]
    owners: list[uuid.UUID]
    stakeholder_groups: list[str]
    work_items: list[dict[str, Any]]  # US-48 is deferred: always empty


class CheckRead(BaseModel):
    key: str
    title: str
    status: Literal["pending", "pass", "warning", "fail", "info"]
    message: str
    details: dict[str, Any]


class ReportRead(BaseModel):
    id: uuid.UUID
    proposal_revision: int
    base_version: int
    baseline_revision: int
    risk_level: Literal["low", "medium", "high"] | None
    risk_reasons: list[str]
    affected: list[AffectedRead]
    checks: list[CheckRead]
    findings_delta: dict[str, list[dict[str, Any]]]
    narrative: dict[str, Any] | None
    is_stale: bool
    llm_calls: int
    created_at: datetime


class ChecksRead(BaseModel):
    state: Literal["pending", "done", "stale"]
    stale_reasons: list[str]
    report: ReportRead | None


@router.get(
    "/requirements/{requirement_id}/impact",
    response_model=ImpactRead,
    summary="What a change to this requirement would touch (no LLM)",
    responses=ERRORS,
)
def get_impact(
    requirement_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
    kind: Literal["modify", "deprecate"] = "modify",
) -> ImpactRead:
    requirement = db.get(Requirement, requirement_id)
    if requirement is None:  # cannot happen after require_permission; defensive
        raise NotFoundError("Requirement not found")
    impact = ImpactAnalyzer(db).analyse(requirement, kind=kind)
    return ImpactRead(
        requirement_id=requirement.id,
        label=label(requirement),
        affected=[AffectedRead.model_validate(a.as_json()) for a in impact.affected],
        owners=impact.owners,
        stakeholder_groups=impact.stakeholder_groups,
        work_items=impact.work_items,
    )


@router.get(
    "/change-requests/{change_request_id}/checks",
    response_model=ChecksRead,
    summary="The change request's consequence report: checks, findings delta, risk",
    responses=ERRORS,
)
def get_checks(
    change_request_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
) -> ChecksRead:
    change_request = change_request_or_404(db, change_request_id)
    report = consequence_tasks.latest_report(db, change_request.id)
    if report is None:
        return ChecksRead(state="pending", stale_reasons=[], report=None)
    requirement = db.get(Requirement, change_request.requirement_id)
    project = db.get(Project, change_request.project_id)
    reasons = (
        consequence_tasks.stale_reasons(report, change_request, requirement, project)
        if requirement is not None and project is not None
        else []
    )
    stale = consequence_tasks.refresh_staleness(db, report, change_request)
    return ChecksRead(
        state="stale" if stale else "done",
        stale_reasons=reasons,
        report=ReportRead.model_validate(report, from_attributes=True),
    )


@router.post(
    "/change-requests/{change_request_id}/checks/rerun",
    status_code=202,
    summary="Run the change request's checks again (queued)",
    responses=ERRORS,
)
def rerun_checks(
    change_request_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("rcr.review")],
    db: DbSession,
) -> Response:
    change_request = change_request_or_404(db, change_request_id)
    if change_request.status not in ACTIVE:
        raise ConflictError("This change request is already decided", code="decided")
    consequence_tasks.queue_checks(change_request.id)
    return Response(status_code=202)
