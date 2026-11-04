"""Auth routes (Role 5; Parth — US-19).

``POST /api/v1/auth/login`` follows the OAuth2 *password flow* wire format
(``application/x-www-form-urlencoded`` with ``username`` + ``password`` fields) so Swagger UI's
"Authorize" button and standard client libraries work out of the box. ``username`` is the
user's email address.

``POST /api/v1/auth/signup`` is the only way to create an account through the API, and it needs
a join code (SX-02): there is no open registration. Both routes are *public* by explicit
declaration; ``tests/api/test_access_invariants.py`` keeps that list from growing by accident.

Silent re-login (US-19): login and sign-up also set an HttpOnly refresh cookie, scoped to
``/api/v1/auth``. ``POST /auth/refresh`` trades it for a new access token (and rotates it);
``POST /auth/logout`` revokes it. Both are public — the access token may already have expired —
and need the ``X-Requested-With`` header: a custom header forces a CORS preflight, so another
site cannot fire them with a plain form post. See ``app/services/sessions.py``.
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Header, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.api.deps import Authenticated, PublicRoute
from app.core.config import get_settings
from app.core.database import get_db
from app.core.errors import ForbiddenError, InvalidCredentialsError, SessionExpiredError
from app.core.rate_limit import RateLimiter, client_ip, enforce, get_rate_limiter, hash_key_part
from app.schemas.auth import (
    MembershipRead,
    MeRead,
    SignupRequest,
    SignupResponse,
    TokenResponse,
    UserRead,
)
from app.schemas.common import ErrorResponse
from app.services import sessions
from app.services import signup as signup_service
from app.services.membership import list_active_memberships
from app.services.users import authenticate_user

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "rcd_refresh"
REFRESH_COOKIE_PATH = "/api/v1/auth"  # sent to the auth routes only, never to the rest of the API
CSRF_HEADER = "X-Requested-With"


def _expires_in(expires_at: datetime) -> int:
    return round((expires_at - datetime.now(UTC)).total_seconds())


def _set_refresh_cookie(response: Response, tokens: sessions.IssuedTokens) -> None:
    settings = get_settings()
    response.set_cookie(
        REFRESH_COOKIE,
        tokens.refresh_token,
        max_age=max(0, _expires_in(tokens.refresh_expires_at)),
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=settings.refresh_cookie_is_secure,
        samesite=settings.refresh_cookie_samesite,
    )


def _clear_refresh_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        REFRESH_COOKIE,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=settings.refresh_cookie_is_secure,
        samesite=settings.refresh_cookie_samesite,
    )


def _clearing_cookie_header() -> str:
    response = Response()
    _clear_refresh_cookie(response)
    return response.headers["set-cookie"]


def _require_csrf_header(
    requested_with: Annotated[str | None, Header(alias=CSRF_HEADER)] = None,
) -> None:
    if not requested_with:
        raise ForbiddenError(f"The {CSRF_HEADER} header is required")


RefreshCookie = Annotated[str | None, Cookie(alias=REFRESH_COOKIE)]
SessionStoreDep = Annotated[sessions.SessionStore, Depends(sessions.get_session_store)]


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate and receive a JWT",
    dependencies=[PublicRoute],
    responses={401: {"model": ErrorResponse, "description": "Incorrect email or password"}},
)
def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> TokenResponse:
    user = authenticate_user(db, form.username, form.password)
    if user is None:
        raise InvalidCredentialsError()
    tokens = sessions.start_session(user.id)
    _set_refresh_cookie(response, tokens)
    return TokenResponse(
        access_token=tokens.access_token, expires_in=_expires_in(tokens.access_expires_at)
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Trade the refresh cookie for a new access token (silent re-login)",
    dependencies=[PublicRoute, Depends(_require_csrf_header)],
    responses={
        401: {"model": ErrorResponse, "description": "`session_expired` — sign in again"},
        403: {"model": ErrorResponse, "description": "The X-Requested-With header is missing"},
        503: {"model": ErrorResponse, "description": "`session_store_unavailable`"},
    },
)
def refresh(
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    store: SessionStoreDep,
    refresh_cookie: RefreshCookie = None,
) -> TokenResponse:
    try:
        tokens = sessions.refresh_session(db, store, refresh_cookie)
    except SessionExpiredError:
        # Raising discards ``response``: the dead cookie is cleared on the error answer instead.
        raise SessionExpiredError(headers={"set-cookie": _clearing_cookie_header()}) from None
    _set_refresh_cookie(response, tokens)
    return TokenResponse(
        access_token=tokens.access_token, expires_in=_expires_in(tokens.access_expires_at)
    )


@router.post(
    "/logout",
    status_code=204,
    summary="End this browser's session (revokes the refresh cookie)",
    dependencies=[PublicRoute, Depends(_require_csrf_header)],
    responses={403: {"model": ErrorResponse}},
)
def logout(store: SessionStoreDep, refresh_cookie: RefreshCookie = None) -> Response:
    sessions.end_session(store, refresh_cookie)
    response = Response(status_code=204)
    _clear_refresh_cookie(response)
    return response


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
    response: Response,
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
    tokens = sessions.start_session(result.user.id)
    _set_refresh_cookie(response, tokens)
    return SignupResponse(
        access_token=tokens.access_token,
        expires_in=_expires_in(tokens.access_expires_at),
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
