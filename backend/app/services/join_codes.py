"""JoinCodeService — Domain logic for workspace invite codes (US-25, FR-37).

Security invariants:
- Plaintext codes are never stored or logged — only SHA-256 hashes with server-side pepper.
- 8-character codes drawn from a 32-character unambiguous alphabet provide 40 bits of entropy.
- Join codes MUST NEVER grant Administrator or Owner privileges.
- Concurrency races on maximum uses are serialized using SELECT ... FOR UPDATE.
"""

from __future__ import annotations

import hashlib
import logging
import re
import secrets
import uuid
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import and_, case, func, or_, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_sessionmaker
from app.core.errors import (
    AlreadyMemberError,
    ConflictError,
    DuplicateJoinRequestError,
    ForbiddenError,
    InvalidJoinCodeError,
    JoinCodeExhaustedError,
    JoinCodeExpiredError,
    JoinCodeNotFoundError,
    JoinCodeRevokedError,
    NotFoundError,
    RoleRestrictedError,
)
from app.models.audit import AuditLog
from app.models.enums import AuditAction, JoinCodeStatus, JoinRequestStatus, Role
from app.models.join_code import JoinCode, JoinRequest
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.join_codes import JoinRedemptionResult, RedemptionStatus

logger = logging.getLogger(__name__)

# 32-character unambiguous alphabet (Crockford-style base32, excluding 0/O, 1/I/L, U)
# 32^8 = 2^40 combinations -> exactly 40.0 bits of cryptographic entropy.
JOIN_CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
JOIN_CODE_LENGTH = 8
_CANONICAL_PATTERN = re.compile(f"^[{JOIN_CODE_ALPHABET}]{{{JOIN_CODE_LENGTH}}}$")


def _now_utc() -> datetime:
    """Return current UTC timestamp with timezone awareness."""
    return datetime.now(UTC)


def generate_secure_code() -> str:
    """Generate an 8-character cryptographically secure join code (XXXX-XXXX)."""
    raw_chars = [secrets.choice(JOIN_CODE_ALPHABET) for _ in range(JOIN_CODE_LENGTH)]
    # Group into XXXX-XXXX for user presentation
    return f"{''.join(raw_chars[:4])}-{''.join(raw_chars[4:])}"


def canonicalize_code(code: str) -> str:
    """Normalize and validate a raw join code string.

    Strips whitespace, hyphens, and spaces, and converts to uppercase.
    Raises:
        InvalidJoinCodeError: If code length != 8 or contains invalid characters.
    """
    if not code or not isinstance(code, str):
        raise InvalidJoinCodeError("Join code must be a non-empty string")
    cleaned = code.strip().upper().replace("-", "").replace(" ", "")
    if not _CANONICAL_PATTERN.match(cleaned):
        raise InvalidJoinCodeError(
            f"Invalid join code format: expected {JOIN_CODE_LENGTH} characters from unambiguous alphabet"
        )
    return cleaned


def compute_code_hash(code: str, pepper: str | None = None) -> str:
    """Compute the SHA-256 digest of (server_pepper + canonical_code).

    Plaintext code is never persisted.
    """
    canonical = canonicalize_code(code)
    if pepper is None:
        pepper = get_settings().join_code_pepper.get_secret_value()
    data = (pepper + canonical).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def mask_code(code_or_canonical: str) -> str:
    """Return a masked representation (e.g., K9Q2****) safe for audit or admin lists."""
    cleaned = code_or_canonical.strip().upper().replace("-", "").replace(" ", "")
    if len(cleaned) >= 4:
        return f"{cleaned[:4]}****"
    return "****"


class JoinCodeService:
    """Domain service managing join-code lifecycle, creation, revocation, and redemption."""

    @classmethod
    def create_code(
        cls,
        db: Session,
        *,
        workspace_id: uuid.UUID,
        creator: User,
        role: Role = Role.ANALYST,
        expires_at: datetime | None = None,
        max_uses: int | None = None,
        requires_approval: bool = False,
        pepper: str | None = None,
    ) -> tuple[JoinCode, str]:
        """Create a new join code for a workspace.

        Returns:
            Tuple of (persisted JoinCode model, plaintext code 'XXXX-XXXX' disclosed once).
        Raises:
            RoleRestrictedError: If role is Administrator or Owner.
            ForbiddenError: If creator is not an Admin in target workspace.
            InvalidJoinCodeError: If parameters are invalid.
        """
        # Security invariant: join codes must never grant Admin/Owner privileges
        if role == Role.ADMIN or str(role).lower() in ("admin", "owner"):
            raise RoleRestrictedError("Join codes cannot grant administrator or owner privileges")

        # Workspace authority check
        if creator.workspace_id != workspace_id or creator.role != Role.ADMIN:
            raise ForbiddenError("Only workspace administrators can create join codes")

        if max_uses is not None and max_uses <= 0:
            raise InvalidJoinCodeError("max_uses must be a positive integer or null")

        now = _now_utc()
        if expires_at is not None:
            # If naive, treat as UTC
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if expires_at <= now:
                raise InvalidJoinCodeError("expires_at must be in the future")

        # Generate secure code and hash
        raw_code = generate_secure_code()
        code_hash = compute_code_hash(raw_code, pepper=pepper)

        join_code = JoinCode(
            code_hash=code_hash,
            workspace_id=workspace_id,
            role=role,
            created_by=creator.id,
            max_uses=max_uses,
            use_count=0,
            expires_at=expires_at,
            status=JoinCodeStatus.ACTIVE,
            requires_approval=requires_approval,
        )
        db.add(join_code)

        # Audit trail
        audit = AuditLog(
            workspace_id=workspace_id,
            actor_id=creator.id,
            action=AuditAction.JOIN_CODE_CREATED,
            details={
                "code_id": str(join_code.id),
                "role": role.value,
                "max_uses": max_uses,
                "requires_approval": requires_approval,
                "expires_at": expires_at.isoformat() if expires_at else None,
            },
        )
        db.add(audit)
        db.commit()
        db.refresh(join_code)

        logger.info(
            "Created join code %s for workspace %s by user %s (role=%s, requires_approval=%s)",
            join_code.id,
            workspace_id,
            creator.id,
            role.value,
            requires_approval,
        )
        return join_code, raw_code

    @classmethod
    def list_codes(
        cls,
        db: Session,
        *,
        workspace_id: uuid.UUID,
        requesting_user: User,
        status: JoinCodeStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[JoinCode], int]:
        """List join codes for a workspace with isolation check."""
        if requesting_user.workspace_id != workspace_id or requesting_user.role != Role.ADMIN:
            raise ForbiddenError("Only workspace administrators can view join codes")

        query = select(JoinCode).where(JoinCode.workspace_id == workspace_id)
        if status is not None:
            query = query.where(JoinCode.status == status)

        count_query = select(func.count()).select_from(query.subquery())
        total_count = db.scalar(count_query) or 0

        offset = max(0, (page - 1) * page_size)
        items = list(
            db.scalars(query.order_by(JoinCode.created_at.desc()).offset(offset).limit(page_size))
        )
        return items, total_count

    @classmethod
    def revoke_code(
        cls,
        db: Session,
        *,
        code_id: uuid.UUID,
        requesting_user: User,
    ) -> JoinCode:
        """Revoke a join code, invalidating all future redemption attempts."""
        code = db.get(JoinCode, code_id)
        if code is None:
            raise JoinCodeNotFoundError("Join code not found")

        if code.workspace_id != requesting_user.workspace_id or requesting_user.role != Role.ADMIN:
            raise ForbiddenError(
                "You do not have permission to revoke join codes in this workspace"
            )

        if code.status == JoinCodeStatus.REVOKED:
            raise JoinCodeRevokedError("Join code is already revoked")

        now = _now_utc()
        code.status = JoinCodeStatus.REVOKED
        code.revoked_by = requesting_user.id
        code.revoked_at = now

        audit = AuditLog(
            workspace_id=code.workspace_id,
            actor_id=requesting_user.id,
            action=AuditAction.JOIN_CODE_REVOKED,
            details={"code_id": str(code.id)},
        )
        db.add(audit)
        db.commit()
        db.refresh(code)

        logger.info("Revoked join code %s by user %s", code.id, requesting_user.id)
        return code

    @classmethod
    def redeem(
        cls,
        db_or_code: Session | str,
        user_or_code: User | str | None = None,
        *,
        code: str | None = None,
        user: User | None = None,
        db: Session | None = None,
        pepper: str | None = None,
    ) -> JoinRedemptionResult:
        """Redeem a join code for an authenticated user.

        Supports both:
            JoinCodeService.redeem(code, user)        # uses ambient/default session
            JoinCodeService.redeem(db, code=code, user=user)

        Uses `SELECT ... FOR UPDATE` row locking to prevent race conditions on max_uses.
        """
        # Resolve flexible positional/keyword arguments
        actual_db: Session
        actual_code: str
        actual_user: User

        if isinstance(db_or_code, Session):
            actual_db = db_or_code
            actual_code = code if code is not None else str(user_or_code)
            if user is None:
                raise ValueError("user is required when passing db as first argument")
            actual_user = user
        elif isinstance(db_or_code, str):
            actual_code = db_or_code
            if not isinstance(user_or_code, User):
                raise ValueError("user must be provided as second argument when code is first")
            actual_user = user_or_code
            actual_db = db if db is not None else get_sessionmaker()()
        else:
            raise TypeError("First argument must be either Session or str code")

        return cls._execute_redemption(actual_db, code=actual_code, user=actual_user, pepper=pepper)

    @classmethod
    def _execute_redemption(
        cls,
        db: Session,
        *,
        code: str,
        user: User,
        pepper: str | None = None,
    ) -> JoinRedemptionResult:
        """Internal execution of redemption under transaction and FOR UPDATE lock."""
        # 1. Canonicalize input code and compute hash
        code_hash = compute_code_hash(code, pepper=pepper)

        # 2. Pessimistic lock row to serialize concurrent redemptions
        stmt = select(JoinCode).where(JoinCode.code_hash == code_hash).with_for_update()
        join_code = db.scalar(stmt)
        if join_code is None:
            raise JoinCodeNotFoundError("Invalid or unrecognized join code")

        now = _now_utc()

        # 3. State & Validity checks
        if join_code.status == JoinCodeStatus.REVOKED:
            raise JoinCodeRevokedError("This join code has been revoked by an administrator")

        # Expiry check
        if join_code.expires_at is not None:
            exp = join_code.expires_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=UTC)
            if now >= exp:
                if join_code.status != JoinCodeStatus.EXPIRED:
                    join_code.status = JoinCodeStatus.EXPIRED
                    db.commit()
                raise JoinCodeExpiredError("This join code has expired")

        if join_code.status == JoinCodeStatus.EXPIRED:
            raise JoinCodeExpiredError("This join code has expired")

        # Usage limit check
        if join_code.max_uses is not None and join_code.use_count >= join_code.max_uses:
            if join_code.status != JoinCodeStatus.EXHAUSTED:
                join_code.status = JoinCodeStatus.EXHAUSTED
                db.commit()
            raise JoinCodeExhaustedError("This join code has reached its maximum allowed uses")

        if join_code.status == JoinCodeStatus.EXHAUSTED:
            raise JoinCodeExhaustedError("This join code has reached its maximum allowed uses")

        # 4. User Tenancy Check: is user already a member of this workspace?
        if user.workspace_id == join_code.workspace_id:
            raise AlreadyMemberError("User is already a member of this workspace")

        # 5. Pending join request check: does user already have a pending request for this workspace?
        pending_stmt = select(JoinRequest).where(
            JoinRequest.user_id == user.id,
            JoinRequest.workspace_id == join_code.workspace_id,
            JoinRequest.status == JoinRequestStatus.PENDING,
        )
        if db.scalar(pending_stmt) is not None:
            raise DuplicateJoinRequestError(
                "A join request is already pending approval for this workspace"
            )

        # Fetch workspace name for clean response metadata
        workspace = db.get(Workspace, join_code.workspace_id)
        ws_name = workspace.name if workspace else None

        # 6. Atomically increment usage with conditional concurrency guard
        update_stmt = (
            update(JoinCode)
            .where(
                JoinCode.id == join_code.id,
                JoinCode.status == JoinCodeStatus.ACTIVE,
                or_(
                    JoinCode.max_uses.is_(None),
                    JoinCode.use_count < JoinCode.max_uses,
                ),
            )
            .values(
                use_count=JoinCode.use_count + 1,
                status=case(
                    (
                        and_(
                            JoinCode.max_uses.is_not(None),
                            JoinCode.use_count + 1 >= JoinCode.max_uses,
                        ),
                        JoinCodeStatus.EXHAUSTED,
                    ),
                    else_=JoinCode.status,
                ),
            )
        )
        update_res = db.execute(update_stmt)
        if update_res.rowcount == 0:
            # Another concurrent transaction claimed the last use or exhausted the code
            db.rollback()
            raise JoinCodeExhaustedError("This join code has reached its maximum allowed uses")

        db.refresh(join_code)

        # 7. Direct Join vs. Approval Gate
        if not join_code.requires_approval:
            # Immediate membership assignment
            user.workspace_id = join_code.workspace_id
            user.role = join_code.role

            audit = AuditLog(
                workspace_id=join_code.workspace_id,
                actor_id=user.id,
                action=AuditAction.JOIN_CODE_REDEEMED,
                details={
                    "code_id": str(join_code.id),
                    "role": join_code.role.value,
                    "use_count": join_code.use_count,
                },
            )
            db.add(audit)
            db.commit()

            logger.info(
                "User %s successfully redeemed join code %s and joined workspace %s as %s",
                user.id,
                join_code.id,
                join_code.workspace_id,
                join_code.role.value,
            )
            return JoinRedemptionResult(
                status=RedemptionStatus.JOINED,
                workspace_id=join_code.workspace_id,
                workspace_name=ws_name,
                assigned_role=join_code.role,
                user_id=user.id,
                join_request_id=None,
                message=f"Successfully joined workspace {ws_name or join_code.workspace_id}",
            )
        else:
            # Gated Join: create pending request
            join_request = JoinRequest(
                workspace_id=join_code.workspace_id,
                user_id=user.id,
                join_code_id=join_code.id,
                assigned_role=join_code.role,
                status=JoinRequestStatus.PENDING,
            )
            db.add(join_request)

            audit = AuditLog(
                workspace_id=join_code.workspace_id,
                actor_id=user.id,
                action=AuditAction.JOIN_REQUEST_CREATED,
                details={
                    "code_id": str(join_code.id),
                    "role": join_code.role.value,
                    "request_id": str(join_request.id),
                },
            )
            db.add(audit)
            db.commit()
            db.refresh(join_request)

            logger.info(
                "User %s submitted join code %s; created pending join request %s for workspace %s",
                user.id,
                join_code.id,
                join_request.id,
                join_code.workspace_id,
            )
            return JoinRedemptionResult(
                status=RedemptionStatus.PENDING_APPROVAL,
                workspace_id=join_code.workspace_id,
                workspace_name=ws_name,
                assigned_role=join_code.role,
                user_id=user.id,
                join_request_id=join_request.id,
                message="Join code accepted. Your request is pending workspace administrator approval.",
            )

    @classmethod
    def decide_request(
        cls,
        db: Session,
        *,
        workspace_id: uuid.UUID,
        request_id: uuid.UUID,
        reviewer: User,
        decision: Literal["approve", "reject"],
        reason: str | None = None,
    ) -> JoinRequest:
        """Approve or reject a pending join request."""
        if reviewer.workspace_id != workspace_id or reviewer.role != Role.ADMIN:
            raise ForbiddenError("Only workspace administrators can decide join requests")

        request = db.get(JoinRequest, request_id)
        if request is None or request.workspace_id != workspace_id:
            raise NotFoundError("Join request not found")

        if request.status != JoinRequestStatus.PENDING:
            raise ConflictError(f"Join request has already been decided ({request.status.value})")

        now = _now_utc()
        request.reviewed_by = reviewer.id
        request.reviewed_at = now

        if decision == "approve":
            request.status = JoinRequestStatus.APPROVED
            # Update target user's workspace and role
            target_user = db.get(User, request.user_id)
            if target_user is not None:
                target_user.workspace_id = request.workspace_id
                target_user.role = request.assigned_role

            audit = AuditLog(
                workspace_id=workspace_id,
                actor_id=reviewer.id,
                action=AuditAction.JOIN_REQUEST_APPROVED,
                details={
                    "request_id": str(request.id),
                    "target_user_id": str(request.user_id),
                    "role": request.assigned_role.value,
                },
            )
            db.add(audit)
            logger.info(
                "Join request %s approved by %s for user %s",
                request.id,
                reviewer.id,
                request.user_id,
            )
        elif decision == "reject":
            request.status = JoinRequestStatus.REJECTED
            request.rejection_reason = reason

            audit = AuditLog(
                workspace_id=workspace_id,
                actor_id=reviewer.id,
                action=AuditAction.JOIN_REQUEST_REJECTED,
                details={
                    "request_id": str(request.id),
                    "target_user_id": str(request.user_id),
                    "reason": reason,
                },
            )
            db.add(audit)
            logger.info(
                "Join request %s rejected by %s for user %s",
                request.id,
                reviewer.id,
                request.user_id,
            )
        else:
            raise ValueError(f"Unknown decision '{decision}': must be 'approve' or 'reject'")

        db.commit()
        db.refresh(request)
        return request

    @classmethod
    def get_request(
        cls,
        db: Session,
        *,
        workspace_id: uuid.UUID,
        request_id: uuid.UUID,
        requesting_user: User,
    ) -> JoinRequest:
        """Fetch request details for either the requester or a workspace administrator."""
        request = db.get(JoinRequest, request_id)
        if request is None or request.workspace_id != workspace_id:
            raise NotFoundError("Join request not found")

        is_admin = (
            requesting_user.workspace_id == workspace_id and requesting_user.role == Role.ADMIN
        )
        is_owner = requesting_user.id == request.user_id
        if not (is_admin or is_owner):
            raise ForbiddenError("You do not have permission to view this join request")

        return request

    @classmethod
    def expire_stale_codes(cls, db: Session) -> int:
        """Mark active codes that have passed expires_at as EXPIRED.

        Designed to be called periodically by Celery Beat.
        """
        now = _now_utc()
        stmt = (
            select(JoinCode)
            .where(
                JoinCode.status == JoinCodeStatus.ACTIVE,
                JoinCode.expires_at.is_not(None),
                JoinCode.expires_at <= now,
            )
            .with_for_update()
        )
        expired_codes = list(db.scalars(stmt))
        for code in expired_codes:
            code.status = JoinCodeStatus.EXPIRED

        if expired_codes:
            db.commit()
            logger.info("Marked %d stale join codes as expired", len(expired_codes))
        return len(expired_codes)
