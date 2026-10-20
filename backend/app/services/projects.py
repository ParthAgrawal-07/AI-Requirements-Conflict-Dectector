"""Project service (Parth — US-24, FR-47, FR-103, ADR-14).

A project starts in ``setup``. It becomes ``active`` only when its context is confirmed
(``app/context``, Bansil — US-60); until then **no analysis may run** (the *ContextGate*).
Everything that would start analysis calls :func:`ensure_project_active` first:

* the analysis orchestrator (Sprint 2),
* the composer / requirement posts (Sprint 3),
* change requests and their consequence checks (Sprint 4).

Uploading a document and extracting its requirements are **not** analysis: the initial SRS is
uploaded while the project is still in setup (design update §12.2).
"""

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError
from app.models import AuditAction, AuditLog, Project, ProjectMember, ProjectStatus, User

# Fields a manager may change with PATCH /projects/{p}. ``status`` is deliberately absent: a
# project is activated by confirming its context, never by editing a flag.
UPDATABLE_FIELDS = (
    "name",
    "description",
    "similarity_threshold",
    "confidence_threshold",
    "llm_budget_monthly_calls",
    "required_approvals",
    "chat_detection_enabled",
)


class ProjectInSetupError(ConflictError):
    """Analysis was requested for a project whose context is not confirmed yet (FR-103)."""

    code = "project_in_setup"

    def __init__(self, missing_fields: Sequence[str] = ()) -> None:
        message = (
            "This project is in Setup: analysis, the composer and change requests are disabled "
            "until the project context is confirmed."
        )
        if missing_fields:
            message += " Missing: " + ", ".join(missing_fields) + "."
        super().__init__(message)
        self.missing_fields = list(missing_fields)


def ensure_project_active(project: Project, *, missing_fields: Sequence[str] = ()) -> None:
    """The ContextGate. Raises :class:`ProjectInSetupError` (409) unless the project is active.

    ``missing_fields`` lets the context service (Bansil) name what is still unconfirmed so the
    message can say exactly what the Project Manager has to do (FR-103).
    """
    if project.status is not ProjectStatus.ACTIVE:
        raise ProjectInSetupError(missing_fields)


def is_analysis_enabled(project: Project) -> bool:
    return project.status is ProjectStatus.ACTIVE


def create_project(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    creator: User,
    name: str,
    description: str | None = None,
    settings: dict[str, Any] | None = None,
) -> Project:
    """Create a project in ``setup`` and put its creator on the project team.

    ``settings`` may carry any of the optional tuning fields of :data:`UPDATABLE_FIELDS`;
    unset ones take the database defaults. Raises :class:`ConflictError` if the workspace already
    has a project with this name.
    """
    values = {key: value for key, value in (settings or {}).items() if value is not None}
    project = Project(
        workspace_id=workspace_id,
        name=name.strip(),
        description=description,
        status=ProjectStatus.SETUP,
        created_by=creator.id,
        **values,
    )
    try:
        with db.begin_nested():
            db.add(project)
            db.flush()
    except IntegrityError:
        raise ConflictError("This workspace already has a project with this name") from None

    db.add(ProjectMember(project_id=project.id, user_id=creator.id))
    db.add(
        AuditLog(
            workspace_id=workspace_id,
            actor_id=creator.id,
            action=AuditAction.PROJECT_CREATED,
            details={"project_id": str(project.id)},
        )
    )
    db.commit()
    return project


def get_project(db: Session, project_id: uuid.UUID) -> Project | None:
    return db.get(Project, project_id)


def list_projects(
    db: Session,
    workspace_id: uuid.UUID,
    *,
    include_archived: bool = False,
    limit: int,
    offset: int,
) -> tuple[list[Project], int]:
    conditions = [Project.workspace_id == workspace_id]
    if not include_archived:
        conditions.append(Project.status != ProjectStatus.ARCHIVED)
    total = db.scalar(select(func.count(Project.id)).where(*conditions)) or 0
    rows = db.scalars(
        select(Project)
        .where(*conditions)
        .order_by(Project.created_at, Project.name, Project.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return list(rows), total


def update_project(
    db: Session, *, project: Project, actor: User, changes: dict[str, Any]
) -> Project:
    """Apply a partial update. Only fields in :data:`UPDATABLE_FIELDS` are accepted."""
    unknown = set(changes) - set(UPDATABLE_FIELDS)
    if unknown:
        raise ValueError(f"Not updatable: {sorted(unknown)}")  # a route bug, not a client error
    if isinstance(changes.get("name"), str):
        changes = {**changes, "name": changes["name"].strip()}  # same form create_project stores
    changed = [key for key, value in changes.items() if getattr(project, key) != value]
    if not changed:
        return project
    for key in changed:
        setattr(project, key, changes[key])
    db.add(
        AuditLog(
            workspace_id=project.workspace_id,
            actor_id=actor.id,
            action=AuditAction.PROJECT_UPDATED,
            details={"project_id": str(project.id), "changed": sorted(changed)},
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ConflictError("This workspace already has a project with this name") from None
    return project
