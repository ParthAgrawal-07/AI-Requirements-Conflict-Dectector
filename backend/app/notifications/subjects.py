"""What a notification links to (Madhav — US-38): keys, titles and client routes, never text.

Routes are the web client's (``frontend/src/app/routes.tsx``): every item opens its subject.
"""

import uuid

from sqlalchemy.orm import Session

from app.models import ChangeRequest, Finding, Issue, Project, Requirement
from app.notifications.service import Subject


def _base(project: Project) -> str:
    return f"/w/{project.workspace_id}/p/{project.id}"


def requirement_label(requirement: Requirement | None) -> str:
    if requirement is None:
        return "a requirement"
    return requirement.source_req_id or f"requirement {str(requirement.id)[:8]}"


def change_request(db: Session, row: ChangeRequest, title: str) -> Subject:
    """``title`` with ``{key}`` and ``{requirement}`` filled in, e.g. "Review requested: {key}
    on {requirement}"."""
    project = db.get(Project, row.project_id)
    requirement = db.get(Requirement, row.requirement_id)
    key = f"RCR-{row.number}"
    return Subject(
        type="change_request",
        id=row.id,
        key=key,
        title=title.format(key=key, requirement=requirement_label(requirement)),
        url=f"{_base(project)}/changes/{row.id}" if project else "/",
    )


def issue(db: Session, row: Issue, title: str) -> Subject:
    project = db.get(Project, row.project_id)
    key = f"ISS-{row.number}"
    return Subject(
        type="issue",
        id=row.id,
        key=key,
        title=title.format(key=key),
        url=f"{_base(project)}/issues/{row.id}" if project else "/",
    )


def finding(db: Session, row: Finding, labels: list[str], title: str) -> Subject:
    project = db.get(Project, row.project_id)
    key = " & ".join(labels) or "a finding"
    return Subject(
        type="finding",
        id=row.id,
        key=key,
        title=title.format(key=key, category=row.category.value),
        url=f"{_base(project)}/findings?finding={row.id}" if project else "/",
    )


def message(project: Project, channel_id: uuid.UUID, message_id: uuid.UUID, title: str) -> Subject:
    return Subject(
        type="message",
        id=message_id,
        key="message",
        title=title,
        url=f"{_base(project)}/channels/{channel_id}?message={message_id}",
    )


def join_request(workspace_id: uuid.UUID, request_id: uuid.UUID, title: str) -> Subject:
    return Subject(
        type="join_request",
        id=request_id,
        key="join request",
        title=title,
        url=f"/w/{workspace_id}/members?tab=requests",
    )
