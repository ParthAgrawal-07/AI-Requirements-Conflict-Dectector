"""Shared thread target lookup for clarification delivery (US-09, US-31)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AnalysisRun, AnalysisScope, Finding, Requirement


def posted_subject(db: Session, finding: Finding) -> Requirement | None:
    run = db.scalar(
        select(AnalysisRun).where(
            AnalysisRun.id == finding.analysis_run_id,
            AnalysisRun.project_id == finding.project_id,
            AnalysisRun.scope == AnalysisScope.REQUIREMENT,
        )
    )
    if run is None:
        return None
    return db.scalar(
        select(Requirement).where(
            Requirement.id == run.subject_id,
            Requirement.project_id == finding.project_id,
            Requirement.origin_message_id.is_not(None),
        )
    )
