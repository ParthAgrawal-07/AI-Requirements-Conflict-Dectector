"""User and workspace services (Role 5): authentication, creation, lookup."""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError
from app.core.security import (
    dummy_password_hash,
    hash_password,
    password_needs_rehash,
    validate_password_strength,
    verify_password,
)
from app.models import Role, User, Workspace

logger = logging.getLogger(__name__)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def get_user(db: Session, user_id: uuid.UUID) -> User | None:
    return db.get(User, user_id)


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == normalize_email(email)))


def get_or_create_workspace(db: Session, name: str) -> Workspace:
    workspace = db.scalar(select(Workspace).where(Workspace.name == name))
    if workspace is None:
        workspace = Workspace(name=name)
        db.add(workspace)
        db.commit()
    return workspace


def create_user(
    db: Session,
    *,
    email: str,
    password: str,
    full_name: str,
    role: Role,
    workspace: Workspace,
) -> User:
    """Create a user. Raises ``WeakPasswordError`` or ``ConflictError`` on invalid input."""
    validate_password_strength(password)
    email = normalize_email(email)
    if get_user_by_email(db, email) is not None:
        raise ConflictError(f"A user with email {email} already exists")
    user = User(
        email=email,
        full_name=full_name.strip(),
        hashed_password=hash_password(password),
        role=role,
        workspace_id=workspace.id,
    )
    db.add(user)
    db.commit()
    return user


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    """Return the user if credentials are valid and the account is active, else ``None``.

    Always performs exactly one Argon2 verification, whether or not the account exists, so
    timing doesn't reveal which emails are registered. The failure reason is logged
    server-side only — callers must return one generic error to the client.
    """
    user = get_user_by_email(db, email)
    if user is None:
        verify_password(password, dummy_password_hash())
        logger.info("Login failed: unknown email")
        return None
    if not verify_password(password, user.hashed_password):
        logger.info("Login failed: wrong password for user %s", user.id)
        return None
    if not user.is_active:
        logger.warning("Login refused: user %s is deactivated", user.id)
        return None

    if password_needs_rehash(user.hashed_password):  # hashing parameters were raised since signup
        user.hashed_password = hash_password(password)
    user.last_login_at = datetime.now(UTC)
    db.commit()
    return user
