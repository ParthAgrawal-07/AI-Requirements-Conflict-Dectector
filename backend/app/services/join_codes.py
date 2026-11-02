"""Join codes and join requests (Madhav — US-25, FR-44, FR-77, NFR-35; contract in
``docs/contracts/join_codes.md`` and ``docs/contracts/permissions.md`` §3).

* **Codes.** 8 characters from a 32-symbol alphabet (no 0/O, 1/I): 32^8 = 2^40, the NFR-35
  minimum. Only ``HMAC-SHA256(JOIN_CODE_PEPPER, canonical code)`` is stored, plus the last four
  characters as a hint for the managers' list. The code itself is returned once, at creation.
* **Redemption** (``redeem``) is what ``POST /auth/signup`` and ``POST /join`` call. It locks the
  code row (``SELECT … FOR UPDATE``) so two people can never take the last use, and it **never
  commits**: sign-up has flushed a new user in the same session and must be able to roll the
  whole thing back. Every "this code cannot be used" case — unknown, malformed, expired, used up,
  revoked — raises the one :class:`InvalidJoinCodeError` (NFR-35).
* **Roles.** Memberships are created only through ``membership.add_member(..., via_join_code=True)``
  (and ``add_project_member`` for project-scoped codes), which refuses Owner, Admin and any role
  holding their permissions. Creation checks the same rule up front so a bad code is never issued.
* **Audit.** Code ids, user ids and role ids only — never the code or its hint (CR-04).
"""

import hashlib
import hmac
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, Update, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.core.errors import ConflictError, InvalidJoinCodeError, NotFoundError
from app.models import (
    AuditAction,
    AuditLog,
    JoinCode,
    JoinCodeStatus,
    JoinRequest,
    JoinRequestStatus,
    Membership,
    Project,
    User,
)
from app.services.access import Scope, active_membership, register_scope_resolver
from app.services.membership import (
    add_member,
    add_project_member,
    ensure_role_allowed_via_code,
    get_role,
)

logger = logging.getLogger(__name__)

# Digits 2–9 and the letters without I and O: 8 + 24 = 32 symbols, so 8 characters = 40 bits.
ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
CODE_LENGTH = 8
EXPIRY_DAYS = (1, 7, 30)  # the choices US-25 offers
JOIN_REQUEST_TTL = timedelta(days=14)  # design update §7.3: pending → expired


def _now() -> datetime:
    return datetime.now(UTC)


# ── The code itself ─────────────────────────────────────────────────────────────────────────
def generate_code() -> str:
    """A new canonical code (8 characters, no separator) from the OS CSPRNG."""
    return "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))


def format_code(canonical: str) -> str:
    """``K7QM4XPA`` -> ``K7QM-4XPA``, the form shown to people."""
    return f"{canonical[:4]}-{canonical[4:]}"


def canonicalize(raw: str) -> str | None:
    """Upper-case, drop spaces and hyphens; ``None`` if it cannot be a code at all."""
    cleaned = raw.strip().upper().replace("-", "").replace(" ", "")
    if len(cleaned) != CODE_LENGTH or any(char not in ALPHABET for char in cleaned):
        return None
    return cleaned


def hash_code(canonical: str, pepper: str | None = None) -> str:
    key = (pepper or get_settings().join_code_pepper.get_secret_value()).encode()
    return hmac.new(key, canonical.encode(), hashlib.sha256).hexdigest()


def effective_status(code: JoinCode, now: datetime | None = None) -> JoinCodeStatus:
    """The status to show and enforce: an active code past its expiry *is* expired, even before
    the beat task has written that down."""
    if code.status is JoinCodeStatus.ACTIVE and code.expires_at <= (now or _now()):
        return JoinCodeStatus.EXPIRED
    return code.status


# ── Managers: create, list, revoke ──────────────────────────────────────────────────────────
@dataclass(frozen=True)
class CreatedCode:
    join_code: JoinCode
    code: str  # formatted, shown once


def create_code(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    creator: User,
    role_id: uuid.UUID,
    expires_in_days: int,
    project_id: uuid.UUID | None = None,
    max_uses: int | None = None,
    requires_approval: bool = False,
) -> CreatedCode:
    """Issue a code. The caller has checked ``joincode.manage``; this checks everything else."""
    if expires_in_days not in EXPIRY_DAYS:
        raise ValueError(f"expires_in_days must be one of {EXPIRY_DAYS}")
    role = get_role(db, workspace_id, role_id)  # a default role or one of this workspace's
    ensure_role_allowed_via_code(role)
    if project_id is not None:
        project = db.get(Project, project_id)
        if project is None or project.workspace_id != workspace_id:
            raise NotFoundError("Project not found")

    for _ in range(3):  # a collision in 2^40 is astronomically unlikely, but cheap to handle
        canonical = generate_code()
        join_code = JoinCode(
            workspace_id=workspace_id,
            project_id=project_id,
            code_hash=hash_code(canonical),
            code_hint=canonical[-4:],
            role_id=role.id,
            created_by=creator.id,
            expires_at=_now() + timedelta(days=expires_in_days),
            max_uses=max_uses,
            requires_approval=requires_approval,
        )
        try:
            with db.begin_nested():
                db.add(join_code)
                db.flush()
            break
        except IntegrityError:
            continue
    else:
        raise RuntimeError("Could not generate a unique join code")

    _audit(
        db,
        workspace_id,
        creator.id,
        AuditAction.JOIN_CODE_CREATED,
        code_id=join_code.id,
        role_id=role.id,
        project_id=project_id,
        max_uses=max_uses,
        requires_approval=requires_approval,
    )
    db.commit()
    return CreatedCode(join_code=join_code, code=format_code(canonical))


def list_codes(db: Session, workspace_id: uuid.UUID) -> list[JoinCode]:
    """The workspace's codes, newest first, with their roles loaded."""
    return list(
        db.scalars(
            select(JoinCode)
            .where(JoinCode.workspace_id == workspace_id)
            .options(joinedload(JoinCode.role))
            .order_by(JoinCode.created_at.desc(), JoinCode.id)
        )
    )


def get_code(db: Session, join_code_id: uuid.UUID) -> JoinCode:
    join_code = db.get(JoinCode, join_code_id)
    if join_code is None:
        raise NotFoundError("Join code not found")
    return join_code


def revoke_code(db: Session, *, join_code: JoinCode, actor: User) -> JoinCode:
    """Revoke a code for good. Revoking an already revoked code changes nothing."""
    if join_code.status is not JoinCodeStatus.REVOKED:
        join_code.status = JoinCodeStatus.REVOKED
        join_code.revoked_by = actor.id
        join_code.revoked_at = _now()
        _audit(
            db,
            join_code.workspace_id,
            actor.id,
            AuditAction.JOIN_CODE_REVOKED,
            code_id=join_code.id,
        )
        db.commit()
    return join_code


# ── Redemption ──────────────────────────────────────────────────────────────────────────────
def redeem(db: Session, code: str, user: User) -> Membership | JoinRequest:
    """Use ``code`` for ``user``: a membership now, or a pending join request.

    Flushes, never commits (see the module docstring). Raises :class:`InvalidJoinCodeError` for
    every unusable code, and :class:`ConflictError` when the user is already a member (or already
    waiting for approval) — a case only a signed-in member can reach.
    """
    canonical = canonicalize(code)
    if canonical is None:
        raise InvalidJoinCodeError()
    join_code = db.scalar(
        select(JoinCode).where(JoinCode.code_hash == hash_code(canonical)).with_for_update()
    )
    if join_code is None or effective_status(join_code) is not JoinCodeStatus.ACTIVE:
        raise InvalidJoinCodeError()

    existing = active_membership(db, user.id, join_code.workspace_id)
    if existing is not None and join_code.project_id is None:
        raise ConflictError("You are already a member of this workspace")
    if _pending_request(db, user.id, join_code.workspace_id) is not None:
        raise ConflictError("Your request to join this workspace is waiting for approval")

    join_code.uses += 1
    if join_code.max_uses is not None and join_code.uses >= join_code.max_uses:
        join_code.status = JoinCodeStatus.EXHAUSTED

    if join_code.requires_approval:
        request = JoinRequest(
            workspace_id=join_code.workspace_id,
            project_id=join_code.project_id,
            join_code_id=join_code.id,
            user_id=user.id,
            role_id=join_code.role_id,
        )
        db.add(request)
        db.flush()
        _audit(
            db,
            join_code.workspace_id,
            user.id,
            AuditAction.JOIN_REQUEST_CREATED,
            code_id=join_code.id,
            request_id=request.id,
        )
        db.flush()
        return request

    # A project-scoped code for someone already in the workspace adds them to the project team.
    membership = existing or add_member(
        db,
        workspace_id=join_code.workspace_id,
        user_id=user.id,
        role_id=join_code.role_id,
        via_join_code=True,
        commit=False,
    )
    _join_project(db, join_code.project_id, user, actor_id=user.id)
    _audit(
        db,
        join_code.workspace_id,
        user.id,
        AuditAction.JOIN_CODE_REDEEMED,
        code_id=join_code.id,
        role_id=join_code.role_id,
    )
    db.flush()
    return membership


def project_of(db: Session, code: str) -> uuid.UUID | None:
    """The project a code is scoped to, if any (for the UI to open after joining)."""
    canonical = canonicalize(code)
    if canonical is None:
        return None
    return db.scalar(select(JoinCode.project_id).where(JoinCode.code_hash == hash_code(canonical)))


def _join_project(
    db: Session, project_id: uuid.UUID | None, user: User, *, actor_id: uuid.UUID
) -> None:
    if project_id is None:
        return
    project = db.get(Project, project_id)
    if project is not None:
        add_project_member(
            db, project=project, user=user, actor_id=actor_id, via_join_code=True, commit=False
        )


def _pending_request(
    db: Session, user_id: uuid.UUID, workspace_id: uuid.UUID
) -> JoinRequest | None:
    return db.scalar(
        select(JoinRequest).where(
            JoinRequest.user_id == user_id,
            JoinRequest.workspace_id == workspace_id,
            JoinRequest.status == JoinRequestStatus.PENDING,
        )
    )


# ── Join requests ───────────────────────────────────────────────────────────────────────────
def list_requests(
    db: Session, workspace_id: uuid.UUID, *, status: JoinRequestStatus | None = None
) -> list[JoinRequest]:
    conditions = [JoinRequest.workspace_id == workspace_id]
    if status is not None:
        conditions.append(JoinRequest.status == status)
    return list(
        db.scalars(
            select(JoinRequest)
            .where(*conditions)
            .options(joinedload(JoinRequest.user), joinedload(JoinRequest.role))
            .order_by(JoinRequest.created_at.desc(), JoinRequest.id)
        )
    )


def get_request(db: Session, join_request_id: uuid.UUID) -> JoinRequest:
    request = db.get(JoinRequest, join_request_id)
    if request is None:
        raise NotFoundError("Join request not found")
    return request


def decide(
    db: Session,
    *,
    request: JoinRequest,
    actor: User,
    approve: bool,
    role_id: uuid.UUID | None = None,
) -> JoinRequest:
    """Approve (optionally with another role) or deny a pending request (US-25)."""
    if request.status is not JoinRequestStatus.PENDING:
        raise ConflictError(f"This request has already been {request.status.value}")
    if approve:
        role = get_role(db, request.workspace_id, role_id or request.role_id)
        user = db.get(User, request.user_id)
        if user is None:  # FK makes this impossible; defensive
            raise NotFoundError("User not found")
        if active_membership(db, user.id, request.workspace_id) is None:
            add_member(
                db,
                workspace_id=request.workspace_id,
                user_id=user.id,
                role_id=role.id,
                actor_id=actor.id,
                via_join_code=True,  # an approved request is still a join by code
                commit=False,
            )
        _join_project(db, request.project_id, user, actor_id=actor.id)
        request.role_id = role.id
        request.status = JoinRequestStatus.APPROVED
        action = AuditAction.JOIN_REQUEST_APPROVED
    else:
        request.status = JoinRequestStatus.DENIED
        action = AuditAction.JOIN_REQUEST_DENIED
    request.decided_by = actor.id
    request.decided_at = _now()
    _audit(
        db,
        request.workspace_id,
        actor.id,
        action,
        request_id=request.id,
        user_id=request.user_id,
        role_id=request.role_id,
    )
    db.commit()
    return request


# ── Housekeeping (Celery beat) ──────────────────────────────────────────────────────────────
def expire_stale(db: Session, now: datetime | None = None) -> tuple[int, int]:
    """Mark expired codes and 14-day-old pending requests. Returns ``(codes, requests)``."""
    now = now or _now()
    codes = _updated(
        db,
        update(JoinCode)
        .where(JoinCode.status == JoinCodeStatus.ACTIVE, JoinCode.expires_at <= now)
        .values(status=JoinCodeStatus.EXPIRED),
    )
    requests = _updated(
        db,
        update(JoinRequest)
        .where(
            JoinRequest.status == JoinRequestStatus.PENDING,
            JoinRequest.created_at <= now - JOIN_REQUEST_TTL,
        )
        .values(status=JoinRequestStatus.EXPIRED),
    )
    db.commit()
    if codes or requests:
        logger.info("Expired %d join codes and %d join requests", codes, requests)
    return codes, requests


def _updated(db: Session, statement: Update) -> int:
    """Rows changed by a bulk UPDATE."""
    result = cast(CursorResult[Any], db.execute(statement))
    return result.rowcount


def _audit(
    db: Session,
    workspace_id: uuid.UUID,
    actor_id: uuid.UUID,
    action: AuditAction,
    **details: object,
) -> None:
    db.add(
        AuditLog(
            workspace_id=workspace_id,
            actor_id=actor_id,
            action=action,
            details={
                key: str(value) if isinstance(value, uuid.UUID) else value
                for key, value in details.items()
            },
        )
    )


# ── Access: teach require_permission where codes and requests live ──────────────────────────
def _join_code_scope(db: Session, join_code_id: uuid.UUID) -> Scope | None:
    row = db.execute(
        select(JoinCode.workspace_id, JoinCode.project_id).where(JoinCode.id == join_code_id)
    ).first()
    return None if row is None else Scope(row[0], row[1])


def _join_request_scope(db: Session, join_request_id: uuid.UUID) -> Scope | None:
    row = db.execute(
        select(JoinRequest.workspace_id, JoinRequest.project_id).where(
            JoinRequest.id == join_request_id
        )
    ).first()
    return None if row is None else Scope(row[0], row[1])


register_scope_resolver("join_code_id", _join_code_scope)
register_scope_resolver("join_request_id", _join_request_scope)
