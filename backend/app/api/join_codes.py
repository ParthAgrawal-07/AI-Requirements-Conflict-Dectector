"""Join-code routes (Madhav — US-25, FR-44, FR-77, NFR-35).

* ``POST/GET /workspaces/{w}/join-codes`` and ``DELETE /join-codes/{id}`` need ``joincode.manage``
  (a project-scoped code also needs it in that project);
* ``GET /workspaces/{w}/join-requests`` and ``GET/POST …/join-requests/{id}/decision`` need
  ``members.manage``;
* ``POST /join`` is for a signed-in user entering a code; rate-limited per address and per user
  (10 attempts per 10 minutes by default, NFR-35). New accounts use ``POST /auth/signup``.
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response

from app.api.deps import Authenticated, DbSession, requires
from app.core.config import get_settings
from app.core.errors import ForbiddenError
from app.core.rate_limit import RateLimiter, client_ip, enforce, get_rate_limiter
from app.models import JoinRequest, JoinRequestStatus, Membership
from app.schemas.common import ErrorResponse
from app.schemas.join_codes import (
    JoinCodeCreate,
    JoinCodeCreated,
    JoinCodeRead,
    JoinDecision,
    JoinRequestBody,
    JoinRequestRead,
    JoinResult,
)
from app.services import join_codes as join_code_service
from app.services.access import AccessContext, Scope, build_access_context

router = APIRouter(tags=["join codes"])

_NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Not a member, or no such resource"}
}


@router.post(
    "/workspaces/{workspace_id}/join-codes",
    status_code=201,
    response_model=JoinCodeCreated,
    summary="Create a join code (the full code is returned only now)",
    responses={
        **_NOT_FOUND,
        403: {"model": ErrorResponse},
        409: {"model": ErrorResponse, "description": "The role can never be granted by a code"},
    },
)
def create_join_code(
    workspace_id: uuid.UUID,
    body: JoinCodeCreate,
    ctx: Annotated[AccessContext, requires("joincode.manage")],
    db: DbSession,
) -> JoinCodeCreated:
    if body.project_id is not None:
        # The project-level role (FR-79) decides for a project code; a foreign project is a 404.
        project_ctx = build_access_context(db, ctx.user, Scope(workspace_id, body.project_id))
        if not project_ctx.can("joincode.manage"):
            raise ForbiddenError()
    created = join_code_service.create_code(
        db,
        workspace_id=workspace_id,
        creator=ctx.user,
        role_id=body.role_id,
        project_id=body.project_id,
        expires_in_days=body.expires_in_days,
        max_uses=body.max_uses,
        requires_approval=body.requires_approval,
    )
    db.refresh(created.join_code)
    read = JoinCodeRead.from_model(created.join_code)
    return JoinCodeCreated(**read.model_dump(), code=created.code)


@router.get(
    "/workspaces/{workspace_id}/join-codes",
    response_model=list[JoinCodeRead],
    summary="List the workspace's join codes with uses and expiry",
    responses=_NOT_FOUND,
)
def list_join_codes(
    workspace_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("joincode.manage")],
    db: DbSession,
) -> list[JoinCodeRead]:
    return [
        JoinCodeRead.from_model(code) for code in join_code_service.list_codes(db, workspace_id)
    ]


@router.delete(
    "/join-codes/{join_code_id}",
    status_code=204,
    summary="Revoke a join code",
    responses={**_NOT_FOUND, 403: {"model": ErrorResponse}},
)
def revoke_join_code(
    join_code_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("joincode.manage")],
    db: DbSession,
) -> Response:
    join_code = join_code_service.get_code(db, join_code_id)
    join_code_service.revoke_code(db, join_code=join_code, actor=ctx.user)
    return Response(status_code=204)


@router.post(
    "/join",
    response_model=JoinResult,
    summary="Join a workspace (or project) with a code, as a signed-in user",
    responses={
        202: {"model": JoinResult, "description": "The code needs approval: request created"},
        400: {"model": ErrorResponse, "description": "`invalid_join_code` — one answer for all"},
        409: {"model": ErrorResponse, "description": "Already a member, or already waiting"},
        429: {"model": ErrorResponse, "description": "Too many attempts"},
    },
)
def join_with_code(
    body: JoinRequestBody,
    request: Request,
    response: Response,
    user: Authenticated,
    db: DbSession,
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> JoinResult:
    settings = get_settings()
    limit, window = settings.join_attempts_per_window, settings.join_attempt_window_seconds
    enforce(limiter, f"join:ip:{client_ip(request)}", limit=limit, window_seconds=window)
    enforce(limiter, f"join:user:{user.id}", limit=limit, window_seconds=window)

    try:
        outcome = join_code_service.redeem(db, body.code, user)
        db.commit()
    except Exception:
        db.rollback()
        raise

    if isinstance(outcome, Membership):
        return JoinResult(
            status="joined",
            workspace_id=outcome.workspace_id,
            project_id=join_code_service.project_of(db, body.code),
        )
    assert isinstance(outcome, JoinRequest)  # noqa: S101 — redeem returns one of the two
    response.status_code = 202
    return JoinResult(
        status="pending_approval",
        workspace_id=outcome.workspace_id,
        project_id=outcome.project_id,
        join_request_id=outcome.id,
    )


@router.get(
    "/workspaces/{workspace_id}/join-requests",
    response_model=list[JoinRequestRead],
    summary="Join requests waiting for a decision (or all, with ?status=)",
    responses=_NOT_FOUND,
)
def list_join_requests(
    workspace_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("members.manage")],
    db: DbSession,
    status: JoinRequestStatus | None = JoinRequestStatus.PENDING,
) -> list[JoinRequestRead]:
    return [
        JoinRequestRead.from_model(item)
        for item in join_code_service.list_requests(db, workspace_id, status=status)
    ]


@router.get(
    "/workspaces/{workspace_id}/join-requests/{join_request_id}/decision",
    response_model=JoinRequestRead,
    summary="A join request and its decision so far",
    responses=_NOT_FOUND,
)
def get_join_request(
    workspace_id: uuid.UUID,
    join_request_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("members.manage")],
    db: DbSession,
) -> JoinRequestRead:
    return JoinRequestRead.from_model(join_code_service.get_request(db, join_request_id))


@router.post(
    "/workspaces/{workspace_id}/join-requests/{join_request_id}/decision",
    response_model=JoinRequestRead,
    summary="Approve (choosing the role) or deny a join request",
    responses={**_NOT_FOUND, 409: {"model": ErrorResponse, "description": "Already decided"}},
)
def decide_join_request(
    workspace_id: uuid.UUID,
    join_request_id: uuid.UUID,
    body: JoinDecision,
    ctx: Annotated[AccessContext, requires("members.manage")],
    db: DbSession,
) -> JoinRequestRead:
    request = join_code_service.get_request(db, join_request_id)
    decided = join_code_service.decide(
        db, request=request, actor=ctx.user, approve=body.approve, role_id=body.role_id
    )
    db.refresh(decided)
    return JoinRequestRead.from_model(decided)
