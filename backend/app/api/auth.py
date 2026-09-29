"""Auth routes (Role 5 — Backend API & Orchestration).

``POST /api/v1/auth/login`` follows the OAuth2 *password flow* wire format
(``application/x-www-form-urlencoded`` with ``username`` + ``password`` fields) so Swagger UI's
"Authorize" button and standard client libraries work out of the box. ``username`` is the
user's email address.
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser
from app.core.database import get_db
from app.core.errors import InvalidCredentialsError
from app.core.security import create_access_token
from app.schemas.auth import TokenResponse, UserRead
from app.schemas.common import ErrorResponse
from app.services.users import authenticate_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate and receive a JWT",
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
    return TokenResponse(
        access_token=token,
        expires_in=int((expires_at - datetime.now(UTC)).total_seconds()),
    )


@router.get(
    "/me",
    response_model=UserRead,
    summary="Return the authenticated user",
    responses={401: {"model": ErrorResponse}},
)
def read_current_user(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)
