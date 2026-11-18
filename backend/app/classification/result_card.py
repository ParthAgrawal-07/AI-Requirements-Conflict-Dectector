"""Analysis result cards for posted requirements (US-31, US-09; NFR-17)."""

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    AnalysisRun,
    AnalysisRunStatus,
    AnalysisScope,
    Channel,
    Finding,
    Message,
    MessageKind,
    Requirement,
)
from app.services import messages


def publish_card(db: Session, run: AnalysisRun) -> Message | None:
    """Refresh the run's system reply, including any clarification questions."""
    if run.scope is not AnalysisScope.REQUIREMENT:
        return None
    # Serialize deliveries before looking for an existing card.
    requirement = db.scalar(
        select(Requirement).where(Requirement.id == run.subject_id).with_for_update()
    )
    if requirement is None or requirement.origin_message_id is None:
        return None
    db.refresh(run)
    root = db.get(Message, requirement.origin_message_id)
    channel = db.get(Channel, root.channel_id) if root is not None else None
    if root is None or channel is None:
        return None
    findings = list(
        db.scalars(
            select(Finding)
            .where(Finding.analysis_run_id == run.id)
            .options(selectinload(Finding.clarification))
            .execution_options(populate_existing=True)
        )
    )
    if run.status is AnalysisRunStatus.WAITING_BUDGET:
        body = "AI analysis is waiting for budget."
    elif run.error_message:
        body = f"AI analysis could not finish: {run.error_message}"
    elif findings:
        body = "AI analysis findings:"
        notice = "\nMore entries are available in the findings view."
        omitted = False
        for finding in findings:
            entry = f"\n{finding.category.value}: {finding.explanation or finding.rationale}"
            if finding.clarification:
                entry += f"\nClarification: {finding.clarification.question}"
            if len(body) + len(entry) + len(notice) > messages.MAX_MESSAGE_CHARS:
                omitted = True
                continue
            body += entry
        if omitted:
            body += notice
    else:
        body = "No issues detected by analysis — analysis can miss conflicts."
    payload = {"analysis_run_id": str(run.id), "status": run.status.value}
    existing = db.scalar(
        select(Message).where(
            Message.parent_id == root.id,
            Message.kind == MessageKind.ANALYSIS_CARD,
            Message.payload["analysis_run_id"].astext == str(run.id),
        )
    )
    if existing is not None:
        return messages.update_system_message(db, message=existing, body=body, payload=payload)
    return messages.post_system_message(
        db,
        channel=channel,
        body=body,
        kind=MessageKind.ANALYSIS_CARD,
        parent_id=root.id,
        payload=payload,
    )
