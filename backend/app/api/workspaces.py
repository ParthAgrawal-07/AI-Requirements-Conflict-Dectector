"""Workspace routes (Parth — US-24, FR-43, FR-46).

Who may create a workspace: platform admins, or any signed-in user when the deployment sets
``ALLOW_USER_WORKSPACE_CREATION`` (FR-43). The creator becomes the workspace's Owner.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter

from app.api.deps import Authenticated, DbSession, requires
from app.core.config import get_settings
from app.core.errors import ForbiddenError, NotFoundError
from app.schemas.auth import RoleRef
from app.schemas.common import ErrorResponse
from app.schemas.workspaces import (
    WorkspaceCreate,
    WorkspaceMembershipRead,
    WorkspaceRead,
    WorkspaceUpdate,
)
from app.services import workspaces as workspace_service
from app.services.access import AccessContext
from app.services.membership import list_active_memberships

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.post(
    "",
    status_code=201,
    response_model=WorkspaceRead,
    summary="Create a workspace (you become its Owner)",
    responses={
        403: {"model": ErrorResponse, "description": "Workspace creation is not allowed for you"},
    },
)
def create_workspace(body: WorkspaceCreate, user: Authenticated, db: DbSession) -> WorkspaceRead:
    if not (user.is_platform_admin or get_settings().allow_user_workspace_creation):
        raise ForbiddenError("Only platform administrators can create workspaces")
    workspace = workspace_service.create_workspace(db, owner=user, name=body.name)
    return WorkspaceRead.model_validate(workspace)


@router.get(
    "",
    response_model=list[WorkspaceMembershipRead],
    summary="The workspaces the caller belongs to, with their role in each",
)
def list_my_workspaces(user: Authenticated, db: DbSession) -> list[WorkspaceMembershipRead]:
    return [
        WorkspaceMembershipRead(
            id=m.workspace.id,
            name=m.workspace.name,
            created_at=m.workspace.created_at,
            role=RoleRef(id=m.role.id, name=m.role.name, is_default=m.role.is_default),
            joined_at=m.joined_at,
        )
        for m in list_active_memberships(db, user.id)
    ]


@router.get(
    "/{workspace_id}",
    response_model=WorkspaceRead,
    summary="Get a workspace",
    responses={404: {"model": ErrorResponse}},
)
def get_workspace(
    workspace_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
) -> WorkspaceRead:
    workspace = workspace_service.get_workspace(db, workspace_id)
    if workspace is None:  # cannot happen after require_permission; defensive
        raise NotFoundError("Workspace not found")
    return WorkspaceRead.model_validate(workspace)


@router.patch(
    "/{workspace_id}",
    response_model=WorkspaceRead,
    summary="Rename a workspace",
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
def update_workspace(
    workspace_id: uuid.UUID,
    body: WorkspaceUpdate,
    ctx: Annotated[AccessContext, requires("workspace.manage")],
    db: DbSession,
) -> WorkspaceRead:
    workspace = workspace_service.get_workspace(db, workspace_id)
    if workspace is None:
        raise NotFoundError("Workspace not found")
    workspace = workspace_service.rename_workspace(
        db, workspace=workspace, actor=ctx.user, name=body.name
    )
    return WorkspaceRead.model_validate(workspace)
