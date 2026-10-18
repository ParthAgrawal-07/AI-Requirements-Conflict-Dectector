"""Join code API endpoints (Sprint 1 US-25, FR-37).

Thin router delegating business logic to JoinCodeService.
Enforces RBAC via require_permission, workspace isolation (404 for cross-workspace access),
consistent domain error translation, zero plaintext leakages, and robust state-machine transitions.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_permission
from app.core.database import get_db
from app.core.errors import (
    ForbiddenError,
    NotFoundError,
)
from app.core.rate_limit import rate_limit_join
from app.models.enums import JoinCodeStatus, Role
from app.models.join_code import JoinCode, JoinRequest
from app.schemas.common import ErrorResponse
from app.schemas.join_codes import (
    JoinCodeCreate,
    JoinCodeCreateResponse,
    JoinCodeRead,
    JoinRedeemRequest,
    JoinRedemptionResult,
    JoinRequestDecision,
    JoinRequestRead,
    RedemptionStatus,
)
from app.services.join_codes import JoinCodeService

router = APIRouter()


# ── 1. Create Join Code ───────────────────────────────────────────────────────


@router.post(
    "/workspaces/{w}/join-codes",
    response_model=JoinCodeCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new workspace join code",
    dependencies=[Depends(require_permission("join_codes:create"))],
    responses={
        201: {
            "model": JoinCodeCreateResponse,
            "description": "Join code created (plaintext code disclosed once)",
        },
        400: {"model": ErrorResponse, "description": "Invalid parameter values or past expiry"},
        403: {
            "model": ErrorResponse,
            "description": "Forbidden - requires workspace administrator",
        },
        404: {
            "model": ErrorResponse,
            "description": "Workspace not found (cross-workspace isolation)",
        },
        422: {"model": ErrorResponse, "description": "Cannot grant Administrator or Owner role"},
    },
)
def create_join_code(
    w: uuid.UUID,
    payload: JoinCodeCreate,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> JoinCodeCreateResponse:
    """Create a join code for workspace {w}.

    Plaintext code is returned once and only once in this response.
    """
    # Cross-workspace isolation: return 404 if caller is not in this workspace
    if user.workspace_id != w:
        raise NotFoundError("Workspace not found")

    code_obj, raw_code = JoinCodeService.create_code(
        db,
        workspace_id=w,
        creator=user,
        role=payload.role,
        expires_at=payload.expires_at,
        max_uses=payload.max_uses,
        requires_approval=payload.requires_approval,
    )

    return JoinCodeCreateResponse(
        id=code_obj.id,
        code=raw_code,
        workspace_id=code_obj.workspace_id,
        role=code_obj.role,
        expires_at=code_obj.expires_at,
        max_uses=code_obj.max_uses,
        use_count=code_obj.use_count,
        status=code_obj.status,
        requires_approval=code_obj.requires_approval,
        created_at=code_obj.created_at,
    )


# ── 2. List Join Codes ────────────────────────────────────────────────────────


@router.get(
    "/workspaces/{w}/join-codes",
    response_model=list[JoinCodeRead],
    summary="List join codes for a workspace",
    dependencies=[Depends(require_permission("join_codes:read"))],
    responses={
        200: {"model": list[JoinCodeRead], "description": "List of join codes (masked)"},
        403: {
            "model": ErrorResponse,
            "description": "Forbidden - requires workspace administrator",
        },
        404: {
            "model": ErrorResponse,
            "description": "Workspace not found (cross-workspace isolation)",
        },
    },
)
def list_join_codes(
    w: uuid.UUID,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    code_status: JoinCodeStatus | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> list[JoinCodeRead]:
    """List join codes for workspace {w} with tenant isolation. Stored hashes/peppers are never exposed."""
    if user.workspace_id != w:
        raise NotFoundError("Workspace not found")

    items, _ = JoinCodeService.list_codes(
        db,
        workspace_id=w,
        requesting_user=user,
        status=code_status,
        page=page,
        page_size=page_size,
    )

    return [JoinCodeRead.model_validate(c) for c in items]


# ── 3. Revoke Join Code ───────────────────────────────────────────────────────


@router.delete(
    "/join-codes/{id}",
    response_model=JoinCodeRead,
    summary="Revoke a join code",
    dependencies=[Depends(require_permission("join_codes:delete"))],
    responses={
        200: {"model": JoinCodeRead, "description": "Join code revoked"},
        403: {
            "model": ErrorResponse,
            "description": "Forbidden - requires workspace administrator",
        },
        404: {"model": ErrorResponse, "description": "Join code not found"},
        410: {"model": ErrorResponse, "description": "Join code already revoked"},
    },
)
def revoke_join_code(
    id: uuid.UUID,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> JoinCodeRead:
    """Revoke a join code, immediately invalidating any future redemption attempts."""
    code = db.get(JoinCode, id)
    # Cross-workspace isolation: hide resource existence across workspaces
    if code is None or code.workspace_id != user.workspace_id:
        raise NotFoundError("Join code not found")

    revoked = JoinCodeService.revoke_code(db, code_id=id, requesting_user=user)
    return JoinCodeRead.model_validate(revoked)


# ── 4. Redeem Join Code ───────────────────────────────────────────────────────


@router.post(
    "/join",
    response_model=JoinRedemptionResult,
    summary="Redeem a join code",
    dependencies=[
        Depends(require_permission("join_codes:redeem")),
        Depends(rate_limit_join),
    ],
    responses={
        200: {"model": JoinRedemptionResult, "description": "Direct join: membership assigned"},
        202: {
            "model": JoinRedemptionResult,
            "description": "Approval gated: pending request created",
        },
        400: {"model": ErrorResponse, "description": "Malformed join code"},
        404: {"model": ErrorResponse, "description": "Unrecognized join code"},
        409: {"model": ErrorResponse, "description": "Already member or pending request exists"},
        410: {"model": ErrorResponse, "description": "Code expired, exhausted, or revoked"},
        429: {"model": ErrorResponse, "description": "Too many join attempts (rate limited)"},
    },
)
@router.post(
    "/workspaces/join",
    response_model=JoinRedemptionResult,
    include_in_schema=False,
    dependencies=[
        Depends(require_permission("join_codes:redeem")),
        Depends(rate_limit_join),
    ],
)
def redeem_join_code(
    payload: JoinRedeemRequest,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    response: Response,
) -> JoinRedemptionResult:
    """Redeem a join code for the authenticated user.

    If the code does not require approval, membership is assigned immediately (200 OK).
    If approval is required, a pending JoinRequest is created (202 Accepted).
    Uses pessimistic row locks and serialized concurrency guards.
    """
    result = JoinCodeService.redeem(db, code=payload.code, user=user)

    if result.status == RedemptionStatus.PENDING_APPROVAL:
        response.status_code = status.HTTP_202_ACCEPTED
    else:
        response.status_code = status.HTTP_200_OK

    return result


# ── 5. Get Join Request Status / Decision ─────────────────────────────────────


@router.get(
    "/workspaces/{w}/join-requests/{id}/decision",
    response_model=JoinRequestRead,
    summary="View status and decision of a join request",
    dependencies=[Depends(require_permission("join_requests:read"))],
    responses={
        200: {"model": JoinRequestRead, "description": "Join request details"},
        403: {
            "model": ErrorResponse,
            "description": "Forbidden - unauthorized to view this request",
        },
        404: {"model": ErrorResponse, "description": "Workspace or join request not found"},
    },
)
def get_join_request_decision(
    w: uuid.UUID,
    id: uuid.UUID,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> JoinRequestRead:
    """View details of a join request.

    Authorized for workspace administrators or the user who submitted the request.
    """
    req = db.get(JoinRequest, id)
    if req is None or req.workspace_id != w:
        raise NotFoundError("Join request not found")

    # If caller is from a different workspace and is not the requester, 404
    if user.workspace_id != w and user.id != req.user_id:
        raise NotFoundError("Join request not found")

    is_admin = user.workspace_id == w and user.role == Role.ADMIN
    is_requester = user.id == req.user_id
    if not (is_admin or is_requester):
        raise ForbiddenError("You do not have permission to view this join request")

    return JoinRequestRead.model_validate(req)


# ── 6. Decide Join Request (Approve / Reject) ──────────────────────────────────


@router.post(
    "/workspaces/{w}/join-requests/{id}/decision",
    response_model=JoinRequestRead,
    summary="Approve or reject a pending join request",
    dependencies=[Depends(require_permission("join_requests:decide"))],
    responses={
        200: {"model": JoinRequestRead, "description": "Request approved or rejected"},
        403: {
            "model": ErrorResponse,
            "description": "Forbidden - requires workspace administrator",
        },
        404: {"model": ErrorResponse, "description": "Workspace or join request not found"},
        409: {"model": ErrorResponse, "description": "Request already decided (conflict)"},
    },
)
def decide_join_request(
    w: uuid.UUID,
    id: uuid.UUID,
    payload: JoinRequestDecision,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> JoinRequestRead:
    """Approve or reject a pending join request with audit trail and safe state transitions."""
    if user.workspace_id != w:
        raise NotFoundError("Workspace not found")

    req = db.get(JoinRequest, id)
    if req is None or req.workspace_id != w:
        raise NotFoundError("Join request not found")

    decided = JoinCodeService.decide_request(
        db,
        workspace_id=w,
        request_id=id,
        reviewer=user,
        decision=payload.decision,
        reason=payload.reason,
    )

    return JoinRequestRead.model_validate(decided)
