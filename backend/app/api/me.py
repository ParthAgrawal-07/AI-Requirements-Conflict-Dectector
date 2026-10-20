"""``/me`` routes (Parth — US-27, FR-48).

``GET /me/permissions?project=<id>`` (or ``?workspace=<id>``) tells the UI which actions to show.
It is a *convenience*, never the gate: every route enforces its permission server-side with
``require_permission`` regardless of what the UI hides.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import Authenticated, DbSession
from app.core.errors import BadRequestError
from app.schemas.auth import RoleRef
from app.schemas.common import ErrorResponse
from app.schemas.permissions import MyPermissions
from app.services.access import Scope, build_access_context, resolve_scope

router = APIRouter(prefix="/me", tags=["me"])


@router.get(
    "/permissions",
    response_model=MyPermissions,
    summary="The caller's effective permissions in a project or workspace",
    responses={
        400: {"model": ErrorResponse, "description": "Neither `project` nor `workspace` was given"},
        404: {"model": ErrorResponse, "description": "Not a member (or no such project/workspace)"},
    },
)
def my_permissions(
    user: Authenticated,
    db: DbSession,
    project: Annotated[uuid.UUID | None, Query(description="Project id")] = None,
    workspace: Annotated[uuid.UUID | None, Query(description="Workspace id")] = None,
) -> MyPermissions:
    if project is None and workspace is None:
        raise BadRequestError("Provide `project` or `workspace`", code="scope_required")
    # A project fixes its workspace; when both are given they must agree (else: not found).
    params: dict[str, object] = {}
    if workspace is not None:
        params["workspace_id"] = workspace
    if project is not None:
        params["project_id"] = project
    scope: Scope = resolve_scope(db, params)
    context = build_access_context(db, user, scope)
    return MyPermissions(
        workspace_id=context.workspace_id,
        project_id=context.project_id,
        role=RoleRef(
            id=context.role.id, name=context.role.name, is_default=context.role.is_default
        ),
        permissions=sorted(context.permissions),
        protected_only=sorted(context.protected_only),
    )
