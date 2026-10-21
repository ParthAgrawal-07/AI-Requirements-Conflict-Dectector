"""Project routes (Parth — US-24, FR-47, FR-103).

A new project starts in ``setup``; ``analysis_enabled`` is false until its context is confirmed
(US-60, Bansil). ``PATCH`` edits settings only — the status is not editable here.
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query, Response

from app.api.deps import DbSession, requires
from app.core.errors import NotFoundError
from app.schemas.common import ErrorResponse, Page
from app.schemas.projects import ProjectCreate, ProjectRead, ProjectUpdate
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
