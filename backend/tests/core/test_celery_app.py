import os

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/test_db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET", "test-only-secret-not-for-production-use-0123456789abcdef")

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.celery_app import celery_app
from app.core.tasks import expire_join_codes, ping
from app.models.base import Base
from app.models.enums import JoinCodeStatus, Role
from app.models.join_code import JoinCode
from app.models.user import User
from app.models.workspace import Workspace
from app.services.join_codes import compute_code_hash


def test_only_json_is_accepted() -> None:
    """Pickle would let anyone who can write to Redis execute code on the worker."""
    assert celery_app.conf.accept_content == ["json"]
    assert celery_app.conf.task_serializer == "json"
    assert celery_app.conf.result_serializer == "json"


def test_tasks_are_acked_late_and_time_limited() -> None:
    conf = celery_app.conf
    assert conf.task_acks_late is True
    assert conf.task_reject_on_worker_lost is True
    assert 0 < conf.task_soft_time_limit < conf.task_time_limit


def test_system_ping_is_registered_and_runs() -> None:
    assert "system.ping" in celery_app.tasks
    assert ping() == "pong"


def test_expire_join_codes_registered_in_tasks_and_beat_schedule() -> None:
    """Task must be registered in celery tasks and beat schedule (US-25)."""
    assert "security.expire_join_codes" in celery_app.tasks
    schedule = celery_app.conf.beat_schedule
    assert "expire_join_codes_every_5_minutes" in schedule
    entry = schedule["expire_join_codes_every_5_minutes"]
    assert entry["task"] == "security.expire_join_codes"
    assert entry["schedule"] == 300.0


def test_expire_join_codes_task_lifecycle_and_idempotence() -> None:
    """Test expire_join_codes task against expired, valid, revoked, and already-expired codes."""
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        eng,
        tables=[Workspace.__table__, User.__table__, JoinCode.__table__],
    )
    sm = sessionmaker(bind=eng, autoflush=False, expire_on_commit=False)

    with sm() as db:
        ws = Workspace(name="ExpireTestWS")
        db.add(ws)
        db.commit()

        creator = User(
            email="creator@test.com",
            full_name="Creator",
            hashed_password="h",
            role=Role.ADMIN,
            workspace_id=ws.id,
        )
        db.add(creator)
        db.commit()

        now = datetime.now(UTC)
        past = now - timedelta(hours=2)
        future = now + timedelta(days=2)

        # 1. Active expired code (should be transitioned to EXPIRED)
        c_active_expired = JoinCode(
            code_hash=compute_code_hash("EXPR-2222"),
            workspace_id=ws.id,
            role=Role.ANALYST,
            created_by=creator.id,
            expires_at=past,
            status=JoinCodeStatus.ACTIVE,
        )

        # 2. Active valid code (should remain ACTIVE)
        c_active_valid = JoinCode(
            code_hash=compute_code_hash("VKAD-3333"),
            workspace_id=ws.id,
            role=Role.ANALYST,
            created_by=creator.id,
            expires_at=future,
            status=JoinCodeStatus.ACTIVE,
        )

        # 3. Revoked code with past expiry (should remain REVOKED)
        c_revoked = JoinCode(
            code_hash=compute_code_hash("REVK-4444"),
            workspace_id=ws.id,
            role=Role.ANALYST,
            created_by=creator.id,
            expires_at=past,
            status=JoinCodeStatus.REVOKED,
        )

        # 4. Already expired code (should remain EXPIRED)
        c_already_expired = JoinCode(
            code_hash=compute_code_hash("AKRD-5555"),
            workspace_id=ws.id,
            role=Role.ANALYST,
            created_by=creator.id,
            expires_at=past,
            status=JoinCodeStatus.EXPIRED,
        )

        # 5. Exhausted code (should remain EXHAUSTED)
        c_exhausted = JoinCode(
            code_hash=compute_code_hash("EXST-6666"),
            workspace_id=ws.id,
            role=Role.ANALYST,
            created_by=creator.id,
            max_uses=1,
            use_count=1,
            status=JoinCodeStatus.EXHAUSTED,
        )

        db.add_all([c_active_expired, c_active_valid, c_revoked, c_already_expired, c_exhausted])
        db.commit()

        active_expired_id = c_active_expired.id
        active_valid_id = c_active_valid.id
        revoked_id = c_revoked.id
        already_expired_id = c_already_expired.id
        exhausted_id = c_exhausted.id

    # Execute task with mocked sessionmaker pointing to our test database
    with patch("app.core.database.get_sessionmaker", return_value=sm):
        count1 = expire_join_codes()
        assert count1 == 1

        with sm() as db:
            assert db.get(JoinCode, active_expired_id).status == JoinCodeStatus.EXPIRED
            assert db.get(JoinCode, active_valid_id).status == JoinCodeStatus.ACTIVE
            assert db.get(JoinCode, revoked_id).status == JoinCodeStatus.REVOKED
            assert db.get(JoinCode, already_expired_id).status == JoinCodeStatus.EXPIRED
            assert db.get(JoinCode, exhausted_id).status == JoinCodeStatus.EXHAUSTED

        # Repeat execution must be safe and idempotent (returns 0)
        count2 = expire_join_codes()
        assert count2 == 0
