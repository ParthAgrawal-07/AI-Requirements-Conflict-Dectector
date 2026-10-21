"""Auth routes (Role 5; Parth — US-19).

``POST /api/v1/auth/login`` follows the OAuth2 *password flow* wire format
(``application/x-www-form-urlencoded`` with ``username`` + ``password`` fields) so Swagger UI's
"Authorize" button and standard client libraries work out of the box. ``username`` is the
user's email address.

``POST /api/v1/auth/signup`` is the only way to create an account through the API, and it needs
a join code (SX-02): there is no open registration. Both routes are *public* by explicit
declaration; ``tests/api/test_access_invariants.py`` keeps that list from growing by accident.
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.api.deps import Authenticated, PublicRoute
from app.core.config import get_settings
from app.core.database import get_db
from app.core.errors import InvalidCredentialsError
from app.core.rate_limit import RateLimiter, client_ip, enforce, get_rate_limiter, hash_key_part
from app.core.security import create_access_token
from app.schemas.auth import (
    MembershipRead,
    MeRead,
    SignupRequest,
    SignupResponse,
    TokenResponse,
    UserRead,
)
from app.schemas.common import ErrorResponse
from app.services import signup as signup_service
from app.services.membership import list_active_memberships
from app.services.users import authenticate_user

router = APIRouter(prefix="/auth", tags=["auth"])


def _expires_in(expires_at: datetime) -> int:
    return int((expires_at - datetime.now(UTC)).total_seconds())


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate and receive a JWT",
    dependencies=[PublicRoute],
    responses={401: {"model": ErrorResponse, "description": "Incorrect email or password"}},
)
def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[Session, Depends(get_db)],
) -> TokenResponse:
    user = authenticate_user(db, form.username, form.password)
    if user is None:
        raise InvalidCredentialsError()
    token, expires_at = create_access_token(user.id)
    return TokenResponse(access_token=token, expires_in=_expires_in(expires_at))


@router.post(
    "/signup",
    status_code=201,
    response_model=SignupResponse,
    summary="Create an account with a join code",
    dependencies=[PublicRoute],
    responses={
        400: {
            "model": ErrorResponse,
            "description": "`weak_password`, or `signup_refused` — an invalid code and an "
            "already-registered e-mail give the same answer on purpose",
        },
        429: {"model": ErrorResponse, "description": "Too many attempts (5 per minute)"},
    },
)
def signup(
    body: SignupRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
    redeem: Annotated[
        signup_service.JoinCodeRedeemer, Depends(signup_service.get_join_code_redeemer)
    ],
) -> SignupResponse:
    limit = get_settings().signup_attempts_per_minute
    # Per address stops one machine guessing codes; per e-mail stops a distributed guess at one
    # account. Behind a reverse proxy the real address needs TRUSTED_PROXY_HOPS (see config).
    enforce(limiter, f"signup:ip:{client_ip(request)}", limit=limit)
    enforce(limiter, f"signup:email:{hash_key_part(str(body.email))}", limit=limit)

    result = signup_service.register_with_code(
        db,
        email=str(body.email),
        password=body.password,
        full_name=body.full_name,
        code=body.code.strip(),
        redeem=redeem,
    )
    token, expires_at = create_access_token(result.user.id)
    return SignupResponse(
        access_token=token,
        expires_in=_expires_in(expires_at),
        user=UserRead.model_validate(result.user),
        join_status=result.status,
        workspace_id=result.membership.workspace_id if result.membership else None,
    )


@router.get(
    "/me",
    response_model=MeRead,
    summary="Return the authenticated user and their workspaces",
    responses={401: {"model": ErrorResponse}},
)
def read_current_user(user: Authenticated, db: Annotated[Session, Depends(get_db)]) -> MeRead:
    memberships = [MembershipRead.from_model(m) for m in list_active_memberships(db, user.id)]
    return MeRead(**UserRead.model_validate(user).model_dump(), memberships=memberships)
