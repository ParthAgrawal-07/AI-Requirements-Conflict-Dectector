"""Analysis run routes (Keval — US-31, FR-57; US-03).

``GET /analysis-runs/{id}`` (``view``) — one run: its scope and subject, status (``queued``,
``running``, ``waiting_budget``, ``done``), counts including failures (G1), timing, and its
findings as the finding card shows them. The result card in a requirement's thread reads it.
"""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import DbSession, requires
from app.models import AnalysisRun, AnalysisRunStatus, AnalysisScope, Project
from app.schemas.common import ErrorResponse
from app.schemas.findings import FindingRead
from app.services import findings as finding_service
from app.services.access import AccessContext, Scope, register_scope_resolver

router = APIRouter(tags=["analysis"])


class AnalysisRunRead(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    scope: AnalysisScope
    subject_id: uuid.UUID
    status: AnalysisRunStatus
    pairs_total: int
    pairs_done: int
    pairs_failed: int
    checks_total: int
    checks_done: int
    checks_failed: int
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    findings: list[FindingRead]


@router.get(
    "/analysis-runs/{analysis_run_id}",
    response_model=AnalysisRunRead,
    summary="One analysis run with its findings (the result card's data)",
    responses={404: {"model": ErrorResponse, "description": "Not a member, or no such run"}},
)
def get_run(
    analysis_run_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
) -> AnalysisRunRead:
    run, views = finding_service.run_findings(db, ctx, analysis_run_id)
    return AnalysisRunRead(
        id=run.id,
        project_id=run.project_id,
        scope=run.scope,
        subject_id=run.subject_id,
        status=run.status,
        pairs_total=run.pairs_total,
        pairs_done=run.pairs_done,
        pairs_failed=run.pairs_failed,
        checks_total=run.checks_total,
        checks_done=run.checks_done,
        checks_failed=run.checks_failed,
        error_message=run.error_message,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        findings=[FindingRead.from_view(view) for view in views],
    )


def _run_scope(db: Session, run_id: uuid.UUID) -> Scope | None:
    row = db.execute(
        select(Project.workspace_id, Project.id)
        .join(AnalysisRun, AnalysisRun.project_id == Project.id)
        .where(AnalysisRun.id == run_id)
    ).first()
    return None if row is None else Scope(row[0], row[1])


register_scope_resolver("analysis_run_id", _run_scope)
