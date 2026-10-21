"""Sign-up with a join code (Parth — US-19, FR-37, FR-44, SX-02, NFR-35).

There is **no open sign-up**: an account is created only together with a valid join code. The
flow is one transaction, so a bad code never leaves an orphan account behind:

1. rate-limit by client address and by e-mail (5 attempts/minute each, NFR-35) — in the route;
2. check the password policy — *before* looking at the e-mail, so "weak password" can never be
   told apart from the refusal in step 3;
3. an e-mail that already has an account is **refused with exactly the same response as an
   invalid code** (:class:`SignupRefusedError`). Sign-up therefore cannot be used to find out
   which addresses are registered, with or without a valid code;
4. create the user (flushed, not committed);
5. hand the code to Madhav's ``JoinCodeService.redeem`` — it either creates the membership
   (and project membership for project-scoped codes) or a pending ``join_request``;
6. commit. A "this code cannot be used" error from step 5 (``InvalidJoinCodeError``, or any 4xx
   client error) rolls the user back and becomes the same :class:`SignupRefusedError`; anything
   else (rate limit, outage) rolls back and propagates unchanged.

The contract with Madhav's module (``docs/contracts/permissions.md``)::

    app.services.join_codes.redeem(db, code, user) -> Membership | JoinRequest

* it may commit or only flush — the user row is already in the same session. What matters is
  that it **raises** ``app.core.errors.InvalidJoinCodeError`` on failure (one generic error for
  invalid, expired, used-up and revoked codes, NFR-35), so this module can roll the new account
  back and answer exactly as it does for an existing e-mail;
* it must create memberships with ``membership.add_member(..., via_join_code=True)`` and project
  teams with ``add_project_member(..., via_join_code=True)``: that is what stops a code from ever
  granting Owner, Admin or any role with their permissions;
* it applies its own per-code rate limit and audit entries.

Until that module exists the stub below accepts one development code (never in production).
"""

import importlib
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Environment, get_settings
from app.core.errors import (
    AppError,
    BadRequestError,
    ConflictError,
    InvalidJoinCodeError,
    ServiceUnavailableError,
    SignupRefusedError,
)
from app.core.permissions import DefaultRole
from app.core.security import WeakPasswordError, validate_password_strength
from app.models import Membership, User, Workspace
from app.services.membership import add_member, get_default_role
from app.services.users import create_user, get_user_by_email, normalize_email

logger = logging.getLogger(__name__)

DEV_JOIN_CODE = "TEST1234"  # noqa: S105 — development stub only, refused outside dev/test
DEV_JOIN_WORKSPACE = "Demo Workspace"

JoinCodeRedeemer = Callable[[Session, str, User], Any]

# Client errors from ``redeem`` that mean "this code cannot be used". They are all folded into
# the one refusal so no variant of the message tells an attacker anything.
_CODE_REFUSAL_STATUSES = frozenset({400, 403, 404, 409, 410})


@dataclass(frozen=True)
class SignupResult:
    user: User
    # ``joined``: membership created now. ``pending_approval``: a join request awaits a manager.
    status: Literal["joined", "pending_approval"]
    membership: Membership | None


def _dev_stub_redeem(db: Session, code: str, user: User) -> Membership:
    """Stand-in for Madhav's redeem until it merges: ``TEST1234`` joins the demo workspace."""
    if get_settings().environment not in (Environment.DEVELOPMENT, Environment.TEST):
        raise ServiceUnavailableError(
            "Joining with a code is not available yet.", code="join_codes_unavailable"
        )
    workspace = db.scalar(
        select(Workspace).where(Workspace.name == DEV_JOIN_WORKSPACE).order_by(Workspace.created_at)
    )
    if code.strip().upper() != DEV_JOIN_CODE or workspace is None:
        raise InvalidJoinCodeError()
    return add_member(
        db,
        workspace_id=workspace.id,
        user_id=user.id,
        role_id=get_default_role(db, DefaultRole.DEVELOPER).id,
        via_join_code=True,
        commit=False,
    )


def get_join_code_redeemer() -> JoinCodeRedeemer:
    """FastAPI dependency: Madhav's ``join_codes.redeem`` if it exists, else the dev stub."""
    try:
        module = importlib.import_module("app.services.join_codes")
    except ModuleNotFoundError as exc:
        if exc.name != "app.services.join_codes":
            raise  # the module exists but one of *its* imports is broken: do not hide that
        return _dev_stub_redeem
    redeem = getattr(module, "redeem", None)
    if not callable(redeem):
        logger.error("app.services.join_codes has no redeem(db, code, user); using the dev stub")
        return _dev_stub_redeem
    return redeem  # type: ignore[no-any-return]


def register_with_code(
    db: Session,
    *,
    email: str,
    password: str,
    full_name: str,
    code: str,
    redeem: JoinCodeRedeemer,
) -> SignupResult:
    """Create an account and redeem ``code`` for it atomically."""
    email = normalize_email(email)
    try:
        validate_password_strength(password)  # first: it says nothing about the e-mail
    except WeakPasswordError as exc:
        raise BadRequestError(str(exc), code="weak_password") from None

    if get_user_by_email(db, email) is not None:
        # Existing users sign in and enter the code instead (POST /join). The answer is the same
        # as for an invalid code, so this endpoint cannot enumerate registered e-mails.
        raise SignupRefusedError()
    try:
        user = create_user(db, email=email, password=password, full_name=full_name, commit=False)
    except (ConflictError, IntegrityError):  # lost a race for the same e-mail
        db.rollback()
        raise SignupRefusedError() from None

    try:
        outcome = redeem(db, code, user)
        db.commit()
    except InvalidJoinCodeError:
        db.rollback()
        raise SignupRefusedError() from None
    except AppError as exc:
        db.rollback()
        if exc.status_code in _CODE_REFUSAL_STATUSES:
            logger.info("Join code refused during sign-up (%s)", exc.code)
            raise SignupRefusedError() from None
        raise
    except Exception:
        db.rollback()
        logger.exception("Join-code redemption failed unexpectedly during sign-up")
        raise

    membership = outcome if isinstance(outcome, Membership) else None
    status: Literal["joined", "pending_approval"] = "joined" if membership else "pending_approval"
    return SignupResult(user=user, status=status, membership=membership)
