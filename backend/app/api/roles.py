"""Role routes (Parth — US-27, US-49, FR-48, FR-78).

* ``GET /permissions`` — the catalogue, grouped for the role editor (any signed-in user; it is
  the same for every workspace and holds no tenant data).
* ``GET /workspaces/{w}/roles`` — the nine defaults and the workspace's custom roles (``view``).
* ``POST /workspaces/{w}/roles``, ``PATCH/DELETE /roles/{id}`` — custom roles (``roles.manage``).
  ``/roles/{id}`` resolves live custom roles only, so a default role there is a 404: the defaults
  cannot be edited or deleted.
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Response

from app.api.deps import Authenticated, DbSession, requires
from app.core.errors import NotFoundError
from app.core.permissions import PERMISSION_GROUPS, PERMISSIONS
from app.models import Role
from app.schemas.common import ErrorResponse
from app.schemas.roles import PermissionRead, RoleCreate, RoleUpdate
from app.schemas.workspaces import RoleRead
from app.services import roles as role_service
from app.services.access import AccessContext

router = APIRouter(tags=["roles"])

_CHANGES: dict[int | str, dict[str, Any]] = {
    403: {"model": ErrorResponse, "description": "Missing roles.manage, or escalation"},
    404: {"model": ErrorResponse, "description": "Not a member, or not a custom role"},
    409: {"model": ErrorResponse, "description": "Name taken, in use, or not grantable"},
}


def _read(role: Role) -> RoleRead:
    return RoleRead(
        id=role.id,
        name=role.name,
        is_default=role.is_default,
        description=role.description,
        permissions=sorted(role.permission_names),
        grantable_by_join_code=role_service.grantable_by_join_code(role),
    )


@router.get(
    "/permissions",
    response_model=list[PermissionRead],
    summary="The permission catalogue, grouped for the role editor",
)
def list_permissions(user: Authenticated) -> list[PermissionRead]:
    return [
        PermissionRead(name=name, description=description, group=PERMISSION_GROUPS[name])
        for name, description in PERMISSIONS.items()
    ]


@router.get(
    "/workspaces/{workspace_id}/roles",
    response_model=list[RoleRead],
    summary="The roles this workspace can assign: the nine defaults and its custom roles",
    responses={404: {"model": ErrorResponse}},
)
def list_roles(
    workspace_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("view")],
    db: DbSession,
) -> list[RoleRead]:
    return [_read(role) for role in role_service.list_roles(db, workspace_id)]


@router.post(
    "/workspaces/{workspace_id}/roles",
    status_code=201,
    response_model=RoleRead,
    summary="Create a custom role from catalogue permissions",
    responses=_CHANGES,
)
def create_role(
    workspace_id: uuid.UUID,
    body: RoleCreate,
    ctx: Annotated[AccessContext, requires("roles.manage")],
    db: DbSession,
) -> RoleRead:
    role = role_service.create_role(
        db,
        workspace_id=ctx.workspace_id,
        actor=ctx.user,
        actor_permissions=ctx.permissions,
        name=body.name,
        description=body.description,
        permissions=set(body.permissions),
    )
    return _read(role)


def _custom_role(db: DbSession, role_id: uuid.UUID) -> Role:
    role = role_service.get_custom_role(db, role_id)
    if role is None:  # cannot happen after require_permission; defensive
        raise NotFoundError("Role not found")
    return role


@router.patch(
    "/roles/{role_id}",
    response_model=RoleRead,
    summary="Rename a custom role or change its permissions",
    responses=_CHANGES,
)
def update_role(
    role_id: uuid.UUID,
    body: RoleUpdate,
    ctx: Annotated[AccessContext, requires("roles.manage")],
    db: DbSession,
) -> RoleRead:
    role = role_service.update_role(
        db,
        role=_custom_role(db, role_id),
        actor=ctx.user,
        actor_permissions=ctx.permissions,
        name=body.name,
        description=body.description,
        permissions=None if body.permissions is None else set(body.permissions),
    )
    return _read(role)


@router.delete(
    "/roles/{role_id}",
    status_code=204,
    summary="Delete a custom role nobody holds any more",
    responses=_CHANGES,
)
def delete_role(
    role_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("roles.manage")],
    db: DbSession,
) -> Response:
    role_service.delete_role(db, role=_custom_role(db, role_id), actor=ctx.user)
    return Response(status_code=204)
