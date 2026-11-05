"""Project routes (Parth — US-24, FR-47, FR-103).

A new project starts in ``setup``; ``analysis_enabled`` is false until its context is confirmed
(US-60, Bansil). ``PATCH`` edits settings only — the status is not editable here.
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query, Response

from app.api.deps import DbSession, requires
from app.core.errors import NotFoundError
from app.models import ProjectMember
from app.schemas.auth import RoleRef
from app.schemas.common import ErrorResponse, Page
from app.schemas.projects import (
    ProjectCreate,
    ProjectMemberRead,
    ProjectMemberUpdate,
    ProjectRead,
    ProjectUpdate,
)
from app.services import membership as membership_service
from app.services import projects as project_service
from app.services.access import AccessContext

router = APIRouter(tags=["projects"])

_NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Not a member, or no such resource"}
}


@router.post(
    "/workspaces/{workspace_id}/projects",
    status_code=201,
    response_model=ProjectRead,
    summary="Create a project (starts in Setup)",
    responses={**_NOT_FOUND, 403: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def create_project(
    workspace_id: uuid.UUID,
    body: ProjectCreate,
    response: Response,
    ctx: Annotated[AccessContext, requires("project.manage")],
    db: DbSession,
) -> ProjectRead:
    settings = body.model_dump(exclude={"name", "description"})
    project = project_service.create_project(
        db,
        workspace_id=ctx.workspace_id,
        creator=ctx.user,
        name=body.name,
        description=body.description,
        settings=settings,
    )
    response.headers["Location"] = f"/api/v1/projects/{project.id}"
    return ProjectRead.from_model(project)


@router.get(
    "/workspaces/{workspace_id}/projects",
    response_model=Page[ProjectRead],
    summary="List the workspace's projects",
    responses=_NOT_FOUND,
)
def list_projects(
    workspace_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
    include_archived: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[ProjectRead]:
    projects, total = project_service.list_projects(
        db, ctx.workspace_id, include_archived=include_archived, limit=limit, offset=offset
    )
    return Page[ProjectRead](
        items=[ProjectRead.from_model(project) for project in projects],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/projects/{project_id}",
    response_model=ProjectRead,
    summary="Get a project",
    responses=_NOT_FOUND,
)
def get_project(
    project_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
) -> ProjectRead:
    project = project_service.get_project(db, project_id)
    if project is None:  # cannot happen after require_permission; defensive
        raise NotFoundError("Project not found")
    return ProjectRead.from_model(project)


@router.patch(
    "/projects/{project_id}",
    response_model=ProjectRead,
    summary="Edit a project's name, description or settings",
    responses={**_NOT_FOUND, 403: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def update_project(
    project_id: uuid.UUID,
    body: ProjectUpdate,
    ctx: Annotated[AccessContext, requires("project.manage")],
    db: DbSession,
) -> ProjectRead:
    project = project_service.get_project(db, project_id)
    if project is None:
        raise NotFoundError("Project not found")
    project = project_service.update_project(
        db, project=project, actor=ctx.user, changes=body.model_dump(exclude_unset=True)
    )
    return ProjectRead.from_model(project)


# ── Project team and project-level roles (US-49, FR-79) ─────────────────────────────────────
def _team_read(member: ProjectMember) -> ProjectMemberRead:
    override = member.role_override
    return ProjectMemberRead(
        user_id=member.user_id,
        full_name=member.user.full_name,
        role_override=(
            RoleRef(id=override.id, name=override.name, is_default=override.is_default)
            if override
            else None
        ),
        added_at=member.added_at,
    )


@router.get(
    "/projects/{project_id}/members",
    response_model=list[ProjectMemberRead],
    summary="The project team, with any project-level roles",
    responses=_NOT_FOUND,
)
def list_project_members(
    project_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
) -> list[ProjectMemberRead]:
    project = project_service.get_project(db, project_id)
    if project is None:
        raise NotFoundError("Project not found")
    return [_team_read(m) for m in membership_service.list_project_members(db, project)]


@router.put(
    "/projects/{project_id}/members/{user_id}",
    response_model=ProjectMemberRead,
    summary="Add a workspace member to the team, optionally with a project-level role",
    responses={
        **_NOT_FOUND,
        403: {"model": ErrorResponse, "description": "The role holds more than you may give"},
        409: {"model": ErrorResponse},
    },
)
def set_project_member(
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    body: ProjectMemberUpdate,
    ctx: Annotated[AccessContext, requires("members.manage")],
    db: DbSession,
) -> ProjectMemberRead:
    project = project_service.get_project(db, project_id)
    if project is None:
        raise NotFoundError("Project not found")
    member = membership_service.set_project_role(
        db, ctx=ctx, project=project, user_id=user_id, role_id=body.role_override_id
    )
    return _team_read(member)
