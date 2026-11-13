"""Requirement drafts (Bansil — FR-81, interface design §5.2).

The composer autosaves into a draft every 5 s. Drafts are **private**: only the author sees them,
and only while they may still ``view`` the project — a removed member's drafts are 404 for them,
like everything else in that workspace, and so are drafts in a project whose project-level role
override (US-49) takes ``view`` away. Nothing in a draft is analysed or shared.

An autosave sends the whole field set (``PATCH`` replaces ``fields``), so the last save wins.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.intake.schemas import DraftFields
from app.models import Membership, Project, RequirementDraft, User
from app.services.access import Scope, build_access_context

MAX_DRAFTS_PER_PROJECT = 50


def _can_view(db: Session, user: User, project: Project) -> bool:
    """Whether the user may still see the project: a member whose role there grants ``view``.

    The project-level role override counts (US-49), exactly as for the project's own routes.
    """
    try:
        context = build_access_context(db, user, Scope(project.workspace_id, project.id))
    except NotFoundError:
        return False
    return context.can("view")


def _member_project(db: Session, user: User, project_id: uuid.UUID) -> Project:
    project = db.get(Project, project_id)
    if project is None or not _can_view(db, user, project):
        raise NotFoundError("Project not found")
    return project


def list_drafts(
    db: Session, user: User, *, project_id: uuid.UUID | None = None
) -> list[RequirementDraft]:
    """The caller's drafts, most recently saved first — only in workspaces they still belong to."""
    query = (
        select(RequirementDraft)
        .join(Project, Project.id == RequirementDraft.project_id)
        .join(
            Membership,
            (Membership.workspace_id == Project.workspace_id)
            & (Membership.user_id == user.id)
            & Membership.ended_at.is_(None),
        )
        .where(RequirementDraft.author_id == user.id)
        .order_by(RequirementDraft.updated_at.desc(), RequirementDraft.id)
    )
    if project_id is not None:
        query = query.where(RequirementDraft.project_id == project_id)
    drafts = list(db.scalars(query))
    # Membership is checked in SQL; a project role override without ``view`` needs the full
    # access check, once per project (a user has few drafts: at most 50 per project).
    visible: dict[uuid.UUID, bool] = {}
    for draft in drafts:
        if draft.project_id not in visible:
            project = db.get(Project, draft.project_id)
            visible[draft.project_id] = project is not None and _can_view(db, user, project)
    return [d for d in drafts if visible[d.project_id]]


def get_draft(db: Session, user: User, draft_id: uuid.UUID) -> RequirementDraft:
    draft = db.get(RequirementDraft, draft_id)
    if draft is None or draft.author_id != user.id:
        raise NotFoundError("Draft not found")
    try:
        _member_project(db, user, draft.project_id)
    except NotFoundError:
        raise NotFoundError("Draft not found") from None
    return draft


def create_draft(
    db: Session, user: User, *, project_id: uuid.UUID, fields: DraftFields
) -> RequirementDraft:
    _member_project(db, user, project_id)
    # Autosaves from several tabs can race; lock the author's row (held until commit/rollback)
    # so two creates cannot both pass the count below.
    db.execute(select(User.id).where(User.id == user.id).with_for_update())
    count = db.scalar(
        select(func.count())
        .select_from(RequirementDraft)
        .where(RequirementDraft.author_id == user.id, RequirementDraft.project_id == project_id)
    )
    if (count or 0) >= MAX_DRAFTS_PER_PROJECT:
        raise ConflictError(
            f"You already have {MAX_DRAFTS_PER_PROJECT} drafts in this project; post or delete one",
            code="too_many_drafts",
        )
    draft = RequirementDraft(
        author_id=user.id, project_id=project_id, fields=fields.model_dump(mode="json")
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return draft


def update_draft(db: Session, draft: RequirementDraft, fields: DraftFields) -> RequirementDraft:
    draft.fields = fields.model_dump(mode="json")
    draft.updated_at = func.clock_timestamp()  # autosaves within one transaction still order
    db.commit()
    db.refresh(draft)
    return draft


def delete_draft(db: Session, draft: RequirementDraft, *, commit: bool = True) -> None:
    db.delete(draft)
    if commit:
        db.commit()
    else:
        db.flush()
