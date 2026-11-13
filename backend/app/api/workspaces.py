"""Workspace and member routes (Parth — US-24, US-26, FR-43, FR-45, FR-46, FR-49).

Who may create a workspace: platform admins, or any signed-in user when the deployment sets
``ALLOW_USER_WORKSPACE_CREATION`` (FR-43). The creator becomes the workspace's Owner.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Response

from app.api.deps import Authenticated, DbSession, requires
from app.core.config import get_settings
from app.core.errors import ForbiddenError, NotFoundError
from app.models import Membership
from app.schemas.auth import RoleRef
from app.schemas.common import ErrorResponse
from app.schemas.workspaces import (
    MemberRead,
    MemberRoleUpdate,
    MemberUser,
    ReassignmentRead,
    WorkspaceCreate,
    WorkspaceMembershipRead,
    WorkspaceRead,
    WorkspaceUpdate,
)
from app.services import membership as membership_service
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


# ── Members (US-26, FR-45, FR-49) ───────────────────────────────────────────────────────────
def _member_read(membership: Membership) -> MemberRead:
    return MemberRead(
        user=MemberUser(
            id=membership.user.id,
            full_name=membership.user.full_name,
            email=membership.user.email,
        ),
        role=RoleRef(
            id=membership.role.id, name=membership.role.name, is_default=membership.role.is_default
        ),
        stakeholder_group=membership.stakeholder_group,
        joined_at=membership.joined_at,
    )


@router.get(
    "/{workspace_id}/members",
    response_model=list[MemberRead],
    summary="The workspace's active members and their roles",
    responses={404: {"model": ErrorResponse}},
)
def list_members(
    workspace_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
) -> list[MemberRead]:
    return [_member_read(m) for m in membership_service.list_members(db, workspace_id)]


@router.patch(
    "/{workspace_id}/members/{user_id}",
    response_model=MemberRead,
    summary="Change a member's workspace role (applies on their next request)",
    responses={
        403: {"model": ErrorResponse, "description": "You may not give out or take away that role"},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse, "description": "The last Owner keeps the Owner role"},
    },
)
def change_member_role(
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    body: MemberRoleUpdate,
    ctx: Annotated[AccessContext, requires("members.manage")],
    db: DbSession,
) -> MemberRead:
    membership = membership_service.change_role(db, ctx=ctx, user_id=user_id, role_id=body.role_id)
    return _member_read(membership)


@router.delete(
    "/{workspace_id}/members/{user_id}",
    status_code=204,
    summary="Remove a member: access ends at once and their sockets close",
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse, "description": "Yourself (leave instead) or the last Owner"},
    },
)
def remove_member(
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("members.manage")],
    db: DbSession,
) -> Response:
    membership_service.remove_member(db, ctx=ctx, user_id=user_id)
    return Response(status_code=204)


@router.post(
    "/{workspace_id}/leave",
    status_code=204,
    summary="Leave the workspace (the last Owner must transfer ownership first)",
    responses={
        404: {"model": ErrorResponse, "description": "Not a member"},
        409: {"model": ErrorResponse, "description": "The last Owner cannot leave"},
    },
)
def leave_workspace(workspace_id: uuid.UUID, user: Authenticated, db: DbSession) -> Response:
    # Any member may leave, whatever their role — so no permission, but membership is required.
    membership_service.leave(db, user=user, workspace_id=workspace_id)
    return Response(status_code=204)


@router.get(
    "/{workspace_id}/needs-reassignment",
    response_model=list[ReassignmentRead],
    summary="Items still owned by former members (SX-11)",
    responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def needs_reassignment(
    workspace_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("members.manage")],
    db: DbSession,
) -> list[ReassignmentRead]:
    return [
        ReassignmentRead(
            kind="requirement",
            id=item.requirement_id,
            project_id=item.project_id,
            label=item.label,
            former_owner_id=item.former_owner_id,
            former_owner_name=item.former_owner_name,
        )
        for item in membership_service.needs_reassignment(db, workspace_id)
    ]
