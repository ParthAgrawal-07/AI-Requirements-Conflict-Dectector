"""Tests for JoinCodeService (US-25, FR-37)."""

import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool, StaticPool

from app.core.errors import (
    AlreadyMemberError,
    DuplicateJoinRequestError,
    ForbiddenError,
    JoinCodeExhaustedError,
    JoinCodeExpiredError,
    JoinCodeNotFoundError,
    JoinCodeRevokedError,
    RoleRestrictedError,
)
from app.models.audit import AuditLog
from app.models.base import Base
from app.models.enums import AuditAction, JoinCodeStatus, JoinRequestStatus, Role
from app.models.join_code import JoinCode, JoinRequest
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.join_codes import RedemptionStatus
from app.services.join_codes import (
    JOIN_CODE_ALPHABET,
    JOIN_CODE_LENGTH,
    JoinCodeService,
    canonicalize_code,
    compute_code_hash,
)

TEST_PEPPER = "test-only-secret-join-code-pepper-32-chars-long"


@pytest.fixture
def engine():
    """Create in-memory SQLite database sharing the same thread pool."""
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Create required tables for join code service testing
    Base.metadata.create_all(
        eng,
        tables=[
            Workspace.__table__,
            User.__table__,
            JoinCode.__table__,
            JoinRequest.__table__,
            AuditLog.__table__,
        ],
    )
    yield eng
    eng.dispose()


@pytest.fixture
def session_factory(engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def db(session_factory) -> Iterator[Session]:
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def workspace(db: Session) -> Workspace:
    ws = Workspace(name=f"Workspace-{uuid.uuid4().hex[:6]}")
    db.add(ws)
    db.commit()
    db.refresh(ws)
    return ws


@pytest.fixture
def other_workspace(db: Session) -> Workspace:
    ws = Workspace(name=f"OtherWorkspace-{uuid.uuid4().hex[:6]}")
    db.add(ws)
    db.commit()
    db.refresh(ws)
    return ws


@pytest.fixture
def admin_user(db: Session, workspace: Workspace) -> User:
    u = User(
        email=f"admin-{uuid.uuid4().hex[:6]}@example.com",
        full_name="Admin User",
        hashed_password="hash",
        role=Role.ADMIN,
        workspace_id=workspace.id,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def analyst_user(db: Session, workspace: Workspace) -> User:
    u = User(
        email=f"analyst-{uuid.uuid4().hex[:6]}@example.com",
        full_name="Analyst User",
        hashed_password="hash",
        role=Role.ANALYST,
        workspace_id=workspace.id,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def outsider_user(db: Session, other_workspace: Workspace) -> User:
    u = User(
        email=f"outsider-{uuid.uuid4().hex[:6]}@example.com",
        full_name="Outsider User",
        hashed_password="hash",
        role=Role.READ_ONLY,
        workspace_id=other_workspace.id,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


# ── 1. Code Generation & Hashing ─────────────────────────────────────────────


def test_code_format_and_entropy() -> None:
    code, raw = (
        JoinCodeService.create_code.__wrapped__
        if hasattr(JoinCodeService.create_code, "__wrapped__")
        else (None, None)
    )
    # Test canonical format
    from app.services.join_codes import generate_secure_code

    code = generate_secure_code()
    assert len(code) == 9  # XXXX-XXXX
    assert code[4] == "-"
    canonical = canonicalize_code(code)
    assert len(canonical) == JOIN_CODE_LENGTH
    assert all(c in JOIN_CODE_ALPHABET for c in canonical)


def test_hashing_without_plaintext_persistence(
    db: Session, workspace: Workspace, admin_user: User
) -> None:
    code_obj, raw_code = JoinCodeService.create_code(
        db,
        workspace_id=workspace.id,
        creator=admin_user,
        role=Role.ANALYST,
        pepper=TEST_PEPPER,
    )

    # Verify database model only contains SHA-256 hash
    assert code_obj.code_hash != raw_code
    assert code_obj.code_hash == compute_code_hash(raw_code, pepper=TEST_PEPPER)
    assert len(code_obj.code_hash) == 64

    # Verify pepper dependence: different pepper produces different hash
    alt_hash = compute_code_hash(raw_code, pepper="different-pepper-secret-string-at-least-32")
    assert code_obj.code_hash != alt_hash


# ── 2. Valid Direct Redemption ───────────────────────────────────────────────


def test_valid_direct_redemption(
    db: Session, workspace: Workspace, admin_user: User, outsider_user: User
) -> None:
    code_obj, raw_code = JoinCodeService.create_code(
        db,
        workspace_id=workspace.id,
        creator=admin_user,
        role=Role.ANALYST,
        requires_approval=False,
        pepper=TEST_PEPPER,
    )

    result = JoinCodeService.redeem(
        db,
        code=raw_code,
        user=outsider_user,
        pepper=TEST_PEPPER,
    )

    assert result.status == RedemptionStatus.JOINED
    assert result.workspace_id == workspace.id
    assert result.assigned_role == Role.ANALYST
    assert result.user_id == outsider_user.id
    assert result.join_request_id is None

    # Verify user state updated
    db.refresh(outsider_user)
    assert outsider_user.workspace_id == workspace.id
    assert outsider_user.role == Role.ANALYST

    # Verify audit log
    audit = db.scalar(
        select(AuditLog).where(
            AuditLog.actor_id == outsider_user.id,
            AuditLog.action == AuditAction.JOIN_CODE_REDEEMED,
        )
    )
    assert audit is not None
    assert audit.workspace_id == workspace.id


# ── 3. Approval-Required Redemption ──────────────────────────────────────────


def test_approval_required_redemption_and_decision(
    db: Session,
    workspace: Workspace,
    admin_user: User,
    outsider_user: User,
    other_workspace: Workspace,
) -> None:
    code_obj, raw_code = JoinCodeService.create_code(
        db,
        workspace_id=workspace.id,
        creator=admin_user,
        role=Role.COMPLIANCE_REVIEWER,
        requires_approval=True,
        pepper=TEST_PEPPER,
    )

    result = JoinCodeService.redeem(
        db,
        code=raw_code,
        user=outsider_user,
        pepper=TEST_PEPPER,
    )

    assert result.status == RedemptionStatus.PENDING_APPROVAL
    assert result.workspace_id == workspace.id
    assert result.join_request_id is not None

    # User workspace must NOT change yet
    db.refresh(outsider_user)
    assert outsider_user.workspace_id == other_workspace.id

    # Verify pending join request
    join_req = db.get(JoinRequest, result.join_request_id)
    assert join_req is not None
    assert join_req.status == JoinRequestStatus.PENDING
    assert join_req.assigned_role == Role.COMPLIANCE_REVIEWER

    # Admin approves request
    decided = JoinCodeService.decide_request(
        db,
        workspace_id=workspace.id,
        request_id=join_req.id,
        reviewer=admin_user,
        decision="approve",
    )
    assert decided.status == JoinRequestStatus.APPROVED

    # Now user should be joined
    db.refresh(outsider_user)
    assert outsider_user.workspace_id == workspace.id
    assert outsider_user.role == Role.COMPLIANCE_REVIEWER


def test_approval_request_rejection(
    db: Session,
    workspace: Workspace,
    admin_user: User,
    outsider_user: User,
    other_workspace: Workspace,
) -> None:
    code_obj, raw_code = JoinCodeService.create_code(
        db,
        workspace_id=workspace.id,
        creator=admin_user,
        role=Role.ANALYST,
        requires_approval=True,
        pepper=TEST_PEPPER,
    )

    result = JoinCodeService.redeem(
        db,
        code=raw_code,
        user=outsider_user,
        pepper=TEST_PEPPER,
    )

    decided = JoinCodeService.decide_request(
        db,
        workspace_id=workspace.id,
        request_id=result.join_request_id,
        reviewer=admin_user,
        decision="reject",
        reason="External contractors not permitted",
    )
    assert decided.status == JoinRequestStatus.REJECTED
    assert decided.rejection_reason == "External contractors not permitted"

    # User remains in other workspace
    db.refresh(outsider_user)
    assert outsider_user.workspace_id == other_workspace.id


# ── 4. Revocation, Expiry, and Exhaustion ─────────────────────────────────────


def test_revoked_code_rejected(
    db: Session, workspace: Workspace, admin_user: User, outsider_user: User
) -> None:
    code_obj, raw_code = JoinCodeService.create_code(
        db,
        workspace_id=workspace.id,
        creator=admin_user,
        role=Role.ANALYST,
        pepper=TEST_PEPPER,
    )

    JoinCodeService.revoke_code(db, code_id=code_obj.id, requesting_user=admin_user)
    db.refresh(code_obj)
    assert code_obj.status == JoinCodeStatus.REVOKED

    with pytest.raises(JoinCodeRevokedError):
        JoinCodeService.redeem(db, code=raw_code, user=outsider_user, pepper=TEST_PEPPER)


def test_expired_code_rejected(
    db: Session, workspace: Workspace, admin_user: User, outsider_user: User
) -> None:
    # Create code with near-future expiry and manually wind back for testing
    code_obj, raw_code = JoinCodeService.create_code(
        db,
        workspace_id=workspace.id,
        creator=admin_user,
        role=Role.ANALYST,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        pepper=TEST_PEPPER,
    )
    code_obj.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()

    with pytest.raises(JoinCodeExpiredError):
        JoinCodeService.redeem(db, code=raw_code, user=outsider_user, pepper=TEST_PEPPER)


def test_expire_stale_codes_batch(db: Session, workspace: Workspace, admin_user: User) -> None:
    code_obj, _ = JoinCodeService.create_code(
        db,
        workspace_id=workspace.id,
        creator=admin_user,
        role=Role.ANALYST,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        pepper=TEST_PEPPER,
    )
    code_obj.expires_at = datetime.now(UTC) - timedelta(minutes=2)
    db.commit()

    count = JoinCodeService.expire_stale_codes(db)
    assert count >= 1
    db.refresh(code_obj)
    assert code_obj.status == JoinCodeStatus.EXPIRED


def test_maximum_uses_enforcement(
    db: Session, workspace: Workspace, admin_user: User, other_workspace: Workspace
) -> None:
    code_obj, raw_code = JoinCodeService.create_code(
        db,
        workspace_id=workspace.id,
        creator=admin_user,
        role=Role.ANALYST,
        max_uses=2,
        pepper=TEST_PEPPER,
    )

    user1 = User(
        email="u1@test.com",
        full_name="U1",
        hashed_password="h",
        role=Role.READ_ONLY,
        workspace_id=other_workspace.id,
    )
    user2 = User(
        email="u2@test.com",
        full_name="U2",
        hashed_password="h",
        role=Role.READ_ONLY,
        workspace_id=other_workspace.id,
    )
    user3 = User(
        email="u3@test.com",
        full_name="U3",
        hashed_password="h",
        role=Role.READ_ONLY,
        workspace_id=other_workspace.id,
    )
    db.add_all([user1, user2, user3])
    db.commit()

    # 1st redemption
    r1 = JoinCodeService.redeem(db, code=raw_code, user=user1, pepper=TEST_PEPPER)
    assert r1.status == RedemptionStatus.JOINED

    db.refresh(code_obj)
    assert code_obj.use_count == 1
    assert code_obj.status == JoinCodeStatus.ACTIVE

    # 2nd redemption (exhausts the code)
    r2 = JoinCodeService.redeem(db, code=raw_code, user=user2, pepper=TEST_PEPPER)
    assert r2.status == RedemptionStatus.JOINED

    db.refresh(code_obj)
    assert code_obj.use_count == 2
    assert code_obj.status == JoinCodeStatus.EXHAUSTED

    # 3rd redemption must be refused
    with pytest.raises(JoinCodeExhaustedError):
        JoinCodeService.redeem(db, code=raw_code, user=user3, pepper=TEST_PEPPER)


# ── 5. Security Invariants & Role Restrictions ───────────────────────────────


def test_admin_role_cannot_be_granted_by_join_code(
    db: Session, workspace: Workspace, admin_user: User
) -> None:
    with pytest.raises(RoleRestrictedError, match="administrator"):
        JoinCodeService.create_code(
            db,
            workspace_id=workspace.id,
            creator=admin_user,
            role=Role.ADMIN,
            pepper=TEST_PEPPER,
        )


def test_non_admin_cannot_create_join_code(
    db: Session, workspace: Workspace, analyst_user: User
) -> None:
    with pytest.raises(ForbiddenError):
        JoinCodeService.create_code(
            db,
            workspace_id=workspace.id,
            creator=analyst_user,
            role=Role.ANALYST,
            pepper=TEST_PEPPER,
        )


def test_already_member_cannot_redeem(
    db: Session, workspace: Workspace, admin_user: User, analyst_user: User
) -> None:
    _, raw_code = JoinCodeService.create_code(
        db,
        workspace_id=workspace.id,
        creator=admin_user,
        role=Role.READ_ONLY,
        pepper=TEST_PEPPER,
    )
    # analyst_user is already a member of workspace
    with pytest.raises(AlreadyMemberError):
        JoinCodeService.redeem(db, code=raw_code, user=analyst_user, pepper=TEST_PEPPER)


def test_duplicate_pending_request_prevented(
    db: Session, workspace: Workspace, admin_user: User, outsider_user: User
) -> None:
    _, raw_code = JoinCodeService.create_code(
        db,
        workspace_id=workspace.id,
        creator=admin_user,
        role=Role.ANALYST,
        requires_approval=True,
        pepper=TEST_PEPPER,
    )

    JoinCodeService.redeem(db, code=raw_code, user=outsider_user, pepper=TEST_PEPPER)

    # Submitting again while request is pending should fail
    with pytest.raises(DuplicateJoinRequestError):
        JoinCodeService.redeem(db, code=raw_code, user=outsider_user, pepper=TEST_PEPPER)


def test_cross_workspace_revocation_forbidden(
    db: Session, workspace: Workspace, other_workspace: Workspace, admin_user: User
) -> None:
    other_admin = User(
        email="other-admin@test.com",
        full_name="Other Admin",
        hashed_password="h",
        role=Role.ADMIN,
        workspace_id=other_workspace.id,
    )
    db.add(other_admin)
    db.commit()

    code_obj, _ = JoinCodeService.create_code(
        db,
        workspace_id=workspace.id,
        creator=admin_user,
        role=Role.ANALYST,
        pepper=TEST_PEPPER,
    )

    # other_admin cannot revoke code belonging to workspace
    with pytest.raises(ForbiddenError):
        JoinCodeService.revoke_code(db, code_id=code_obj.id, requesting_user=other_admin)


# ── 6. Concurrent Redemption Races ───────────────────────────────────────────


def test_concurrent_redemption_race(tmp_path: pytest.TempPathFactory) -> None:
    """Multi-threaded concurrency test: 5 threads racing to redeem a single-use code."""
    db_file = tmp_path / "concurrent_race.db"
    race_engine = create_engine(f"sqlite:///{db_file}?timeout=30", poolclass=NullPool)
    with race_engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))
        conn.commit()

    Base.metadata.create_all(
        race_engine,
        tables=[
            Workspace.__table__,
            User.__table__,
            JoinCode.__table__,
            JoinRequest.__table__,
            AuditLog.__table__,
        ],
    )

    race_session_factory = sessionmaker(bind=race_engine, autoflush=False, expire_on_commit=False)

    init_db = race_session_factory()
    ws = Workspace(name="RaceWorkspace")
    other_ws = Workspace(name="OtherRaceWorkspace")
    init_db.add_all([ws, other_ws])
    init_db.commit()

    admin = User(
        email="admin-race@test.com",
        full_name="A",
        hashed_password="h",
        role=Role.ADMIN,
        workspace_id=ws.id,
    )
    init_db.add(admin)
    init_db.commit()

    code_obj, raw_code = JoinCodeService.create_code(
        init_db,
        workspace_id=ws.id,
        creator=admin,
        role=Role.ANALYST,
        max_uses=1,
        pepper=TEST_PEPPER,
    )

    # Create 5 distinct outsider users
    test_users = []
    for i in range(5):
        u = User(
            email=f"racer-{i}@test.com",
            full_name=f"Racer {i}",
            hashed_password="h",
            role=Role.READ_ONLY,
            workspace_id=other_ws.id,
        )
        init_db.add(u)
        test_users.append(u)
    init_db.commit()
    user_ids = [u.id for u in test_users]
    code_id = code_obj.id
    init_db.close()

    successes = []
    failures = []

    def attempt_redeem(uid: uuid.UUID) -> None:
        th_db = race_session_factory()
        try:
            th_user = th_db.get(User, uid)
            if th_user is None:
                raise ValueError(f"User {uid} not found")
            res = JoinCodeService.redeem(th_db, code=raw_code, user=th_user, pepper=TEST_PEPPER)
            successes.append(res)
        except (JoinCodeExhaustedError, JoinCodeRevokedError, JoinCodeNotFoundError) as exc:
            failures.append(type(exc))
        finally:
            th_db.close()

    with ThreadPoolExecutor(max_workers=5) as executor:
        list(executor.map(attempt_redeem, user_ids))

    # Exactly 1 redemption must succeed
    assert len(successes) == 1
    # Exactly 4 must fail due to exhaustion
    assert len(failures) == 4
    assert all(f == JoinCodeExhaustedError for f in failures)

    verify_db = race_session_factory()
    final_code = verify_db.get(JoinCode, code_id)
    assert final_code is not None
    assert final_code.use_count == 1
    assert final_code.status == JoinCodeStatus.EXHAUSTED
    verify_db.close()
    race_engine.dispose()
