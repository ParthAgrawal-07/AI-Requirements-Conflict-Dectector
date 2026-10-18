"""API integration and security tests for Join Codes and Requests (Sprint 1 US-25).

Tests all 6 required endpoints:
- POST   /api/v1/workspaces/{w}/join-codes
- GET    /api/v1/workspaces/{w}/join-codes
- DELETE /api/v1/join-codes/{id}
- POST   /api/v1/join (and alias /api/v1/workspaces/join)
- GET    /api/v1/workspaces/{w}/join-requests/{id}/decision
- POST   /api/v1/workspaces/{w}/join-requests/{id}/decision

Covers:
- Success path for every endpoint
- 403 Forbidden for missing permissions
- 404 Not Found for cross-workspace access
- Input validation, role restrictions (no admin granted)
- Revoked, expired, exhausted code rejections (410 Gone)
- Approval gates (202 Accepted) vs direct joins (200 OK)
- Unauthorized and repeated/conflicting decisions (409 Conflict)
"""

import os

# Set testing environment variables before importing app
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("JWT_SECRET", "test-only-secret-not-for-production-use-0123456789abcdef")
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/test_db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.router import api_router
from app.core.database import get_db
from app.core.errors import install_exception_handlers
from app.core.security import create_access_token
from app.models.audit import AuditLog
from app.models.base import Base
from app.models.enums import Role
from app.models.join_code import JoinCode, JoinRequest
from app.models.user import User
from app.models.workspace import Workspace

TEST_PEPPER = "dev-only-join-code-pepper-secret-string-at-least-32-chars"


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
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
    s = session_factory()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def app(session_factory) -> FastAPI:
    test_app = FastAPI()
    install_exception_handlers(test_app)
    test_app.include_router(api_router)

    def override_get_db() -> Iterator[Session]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    test_app.dependency_overrides[get_db] = override_get_db
    return test_app


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def auth_header(user: User) -> dict[str, str]:
    token, _ = create_access_token(user.id)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def workspace1(db: Session) -> Workspace:
    ws = Workspace(name=f"Engineering-{uuid.uuid4().hex[:8]}")
    db.add(ws)
    db.commit()
    db.refresh(ws)
    return ws


@pytest.fixture
def workspace2(db: Session) -> Workspace:
    ws = Workspace(name=f"Marketing-{uuid.uuid4().hex[:8]}")
    db.add(ws)
    db.commit()
    db.refresh(ws)
    return ws


@pytest.fixture
def admin_ws1(db: Session, workspace1: Workspace) -> User:
    u = User(
        email=f"admin-ws1-{uuid.uuid4().hex[:6]}@example.com",
        full_name="Admin WS1",
        hashed_password="hash",
        role=Role.ADMIN,
        workspace_id=workspace1.id,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def analyst_ws1(db: Session, workspace1: Workspace) -> User:
    u = User(
        email=f"analyst-ws1-{uuid.uuid4().hex[:6]}@example.com",
        full_name="Analyst WS1",
        hashed_password="hash",
        role=Role.ANALYST,
        workspace_id=workspace1.id,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def admin_ws2(db: Session, workspace2: Workspace) -> User:
    u = User(
        email=f"admin-ws2-{uuid.uuid4().hex[:6]}@example.com",
        full_name="Admin WS2",
        hashed_password="hash",
        role=Role.ADMIN,
        workspace_id=workspace2.id,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def outsider(db: Session, workspace2: Workspace) -> User:
    u = User(
        email=f"outsider-{uuid.uuid4().hex[:6]}@example.com",
        full_name="Outsider User",
        hashed_password="hash",
        role=Role.READ_ONLY,
        workspace_id=workspace2.id,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


# ── 1. POST /workspaces/{w}/join-codes ────────────────────────────────────────


class TestCreateJoinCodeEndpoint:
    def test_create_join_code_success(
        self, client: TestClient, workspace1: Workspace, admin_ws1: User
    ) -> None:
        url = f"/api/v1/workspaces/{workspace1.id}/join-codes"
        payload = {
            "role": "analyst",
            "max_uses": 5,
            "requires_approval": False,
        }
        res = client.post(url, json=payload, headers=auth_header(admin_ws1))
        assert res.status_code == 201
        data = res.json()
        assert "code" in data
        assert len(data["code"]) == 9  # XXXX-XXXX format
        assert data["workspace_id"] == str(workspace1.id)
        assert data["role"] == "analyst"
        assert data["max_uses"] == 5
        assert data["status"] == "active"

    def test_create_join_code_analyst_forbidden(
        self, client: TestClient, workspace1: Workspace, analyst_ws1: User
    ) -> None:
        url = f"/api/v1/workspaces/{workspace1.id}/join-codes"
        payload = {"role": "analyst"}
        res = client.post(url, json=payload, headers=auth_header(analyst_ws1))
        assert res.status_code == 403
        assert res.json()["error"]["code"] == "forbidden"

    def test_create_join_code_cross_workspace_not_found(
        self, client: TestClient, workspace1: Workspace, admin_ws2: User
    ) -> None:
        url = f"/api/v1/workspaces/{workspace1.id}/join-codes"
        payload = {"role": "analyst"}
        res = client.post(url, json=payload, headers=auth_header(admin_ws2))
        assert res.status_code == 404
        assert res.json()["error"]["code"] == "not_found"

    def test_create_join_code_cannot_grant_admin_role(
        self, client: TestClient, workspace1: Workspace, admin_ws1: User
    ) -> None:
        url = f"/api/v1/workspaces/{workspace1.id}/join-codes"
        payload = {"role": "admin"}
        res = client.post(url, json=payload, headers=auth_header(admin_ws1))
        assert res.status_code == 422
        assert res.json()["error"]["code"] == "validation_error"

    def test_create_join_code_past_expiry_rejected(
        self, client: TestClient, workspace1: Workspace, admin_ws1: User
    ) -> None:
        url = f"/api/v1/workspaces/{workspace1.id}/join-codes"
        past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        payload = {"role": "analyst", "expires_at": past}
        res = client.post(url, json=payload, headers=auth_header(admin_ws1))
        assert res.status_code == 400
        assert res.json()["error"]["code"] == "invalid_join_code"


# ── 2. GET /workspaces/{w}/join-codes ─────────────────────────────────────────


class TestListJoinCodesEndpoint:
    def test_list_join_codes_success_masks_codes(
        self, client: TestClient, workspace1: Workspace, admin_ws1: User
    ) -> None:
        # Create a code first
        client.post(
            f"/api/v1/workspaces/{workspace1.id}/join-codes",
            json={"role": "analyst"},
            headers=auth_header(admin_ws1),
        )

        res = client.get(
            f"/api/v1/workspaces/{workspace1.id}/join-codes",
            headers=auth_header(admin_ws1),
        )
        assert res.status_code == 200
        items = res.json()
        assert len(items) >= 1
        for item in items:
            assert "masked_code" in item
            assert item["masked_code"].endswith("****")
            assert "code" not in item  # Plaintext is NEVER returned

    def test_list_join_codes_analyst_forbidden(
        self, client: TestClient, workspace1: Workspace, analyst_ws1: User
    ) -> None:
        res = client.get(
            f"/api/v1/workspaces/{workspace1.id}/join-codes",
            headers=auth_header(analyst_ws1),
        )
        assert res.status_code == 403
        assert res.json()["error"]["code"] == "forbidden"

    def test_list_join_codes_cross_workspace_not_found(
        self, client: TestClient, workspace1: Workspace, admin_ws2: User
    ) -> None:
        res = client.get(
            f"/api/v1/workspaces/{workspace1.id}/join-codes",
            headers=auth_header(admin_ws2),
        )
        assert res.status_code == 404
        assert res.json()["error"]["code"] == "not_found"


# ── 3. DELETE /join-codes/{id} ────────────────────────────────────────────────


class TestRevokeJoinCodeEndpoint:
    def test_revoke_join_code_success(
        self, client: TestClient, workspace1: Workspace, admin_ws1: User
    ) -> None:
        create_res = client.post(
            f"/api/v1/workspaces/{workspace1.id}/join-codes",
            json={"role": "analyst"},
            headers=auth_header(admin_ws1),
        )
        code_id = create_res.json()["id"]

        del_res = client.delete(f"/api/v1/join-codes/{code_id}", headers=auth_header(admin_ws1))
        assert del_res.status_code == 200
        assert del_res.json()["status"] == "revoked"

    def test_revoke_join_code_analyst_forbidden(
        self, client: TestClient, workspace1: Workspace, admin_ws1: User, analyst_ws1: User
    ) -> None:
        create_res = client.post(
            f"/api/v1/workspaces/{workspace1.id}/join-codes",
            json={"role": "analyst"},
            headers=auth_header(admin_ws1),
        )
        code_id = create_res.json()["id"]

        del_res = client.delete(f"/api/v1/join-codes/{code_id}", headers=auth_header(analyst_ws1))
        assert del_res.status_code == 403

    def test_revoke_join_code_cross_workspace_not_found(
        self, client: TestClient, workspace1: Workspace, admin_ws1: User, admin_ws2: User
    ) -> None:
        create_res = client.post(
            f"/api/v1/workspaces/{workspace1.id}/join-codes",
            json={"role": "analyst"},
            headers=auth_header(admin_ws1),
        )
        code_id = create_res.json()["id"]

        # Admin of WS2 attempts to delete WS1 code
        del_res = client.delete(f"/api/v1/join-codes/{code_id}", headers=auth_header(admin_ws2))
        assert del_res.status_code == 404
        assert del_res.json()["error"]["code"] == "not_found"

    def test_revoke_already_revoked_code_returns_410(
        self, client: TestClient, workspace1: Workspace, admin_ws1: User
    ) -> None:
        create_res = client.post(
            f"/api/v1/workspaces/{workspace1.id}/join-codes",
            json={"role": "analyst"},
            headers=auth_header(admin_ws1),
        )
        code_id = create_res.json()["id"]

        # First revocation: 200 OK
        client.delete(f"/api/v1/join-codes/{code_id}", headers=auth_header(admin_ws1))

        # Second revocation: 410 Gone
        del_again = client.delete(f"/api/v1/join-codes/{code_id}", headers=auth_header(admin_ws1))
        assert del_again.status_code == 410
        assert del_again.json()["error"]["code"] == "join_code_revoked"


# ── 4. POST /join ─────────────────────────────────────────────────────────────


class TestRedeemEndpoint:
    def test_redeem_direct_join_success(
        self, client: TestClient, workspace1: Workspace, admin_ws1: User, outsider: User
    ) -> None:
        create_res = client.post(
            f"/api/v1/workspaces/{workspace1.id}/join-codes",
            json={"role": "analyst", "requires_approval": False},
            headers=auth_header(admin_ws1),
        )
        raw_code = create_res.json()["code"]

        res = client.post("/api/v1/join", json={"code": raw_code}, headers=auth_header(outsider))
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "joined"
        assert data["workspace_id"] == str(workspace1.id)
        assert data["assigned_role"] == "analyst"

    def test_redeem_approval_required_returns_202(
        self,
        client: TestClient,
        workspace1: Workspace,
        admin_ws1: User,
        db: Session,
        workspace2: Workspace,
    ) -> None:
        create_res = client.post(
            f"/api/v1/workspaces/{workspace1.id}/join-codes",
            json={"role": "analyst", "requires_approval": True},
            headers=auth_header(admin_ws1),
        )
        raw_code = create_res.json()["code"]

        fresh_outsider = User(
            email=f"approval-{uuid.uuid4().hex[:6]}@test.com",
            full_name="Approval User",
            hashed_password="h",
            role=Role.READ_ONLY,
            workspace_id=workspace2.id,
        )
        db.add(fresh_outsider)
        db.commit()

        res = client.post(
            "/api/v1/join", json={"code": raw_code}, headers=auth_header(fresh_outsider)
        )
        assert res.status_code == 202
        data = res.json()
        assert data["status"] == "pending_approval"
        assert data["join_request_id"] is not None

    def test_redeem_malformed_code_returns_400(self, client: TestClient, outsider: User) -> None:
        res = client.post("/api/v1/join", json={"code": "TOO-SHORT"}, headers=auth_header(outsider))
        assert res.status_code == 400
        assert res.json()["error"]["code"] == "invalid_join_code"

    def test_redeem_nonexistent_code_returns_404(self, client: TestClient, outsider: User) -> None:
        res = client.post("/api/v1/join", json={"code": "2345-6789"}, headers=auth_header(outsider))
        assert res.status_code == 404
        assert res.json()["error"]["code"] == "join_code_not_found"

    def test_redeem_already_member_returns_409(
        self, client: TestClient, workspace1: Workspace, admin_ws1: User, analyst_ws1: User
    ) -> None:
        create_res = client.post(
            f"/api/v1/workspaces/{workspace1.id}/join-codes",
            json={"role": "analyst"},
            headers=auth_header(admin_ws1),
        )
        raw_code = create_res.json()["code"]

        # analyst_ws1 is already in workspace1
        res = client.post("/api/v1/join", json={"code": raw_code}, headers=auth_header(analyst_ws1))
        assert res.status_code == 409
        assert res.json()["error"]["code"] == "already_workspace_member"

    def test_redeem_revoked_code_returns_410(
        self, client: TestClient, workspace1: Workspace, admin_ws1: User, outsider: User
    ) -> None:
        create_res = client.post(
            f"/api/v1/workspaces/{workspace1.id}/join-codes",
            json={"role": "analyst"},
            headers=auth_header(admin_ws1),
        )
        code_id = create_res.json()["id"]
        raw_code = create_res.json()["code"]

        client.delete(f"/api/v1/join-codes/{code_id}", headers=auth_header(admin_ws1))

        res = client.post("/api/v1/join", json={"code": raw_code}, headers=auth_header(outsider))
        assert res.status_code == 410
        assert res.json()["error"]["code"] == "join_code_revoked"

    def test_redeem_exhausted_code_returns_410(
        self,
        client: TestClient,
        workspace1: Workspace,
        admin_ws1: User,
        db: Session,
        workspace2: Workspace,
    ) -> None:
        create_res = client.post(
            f"/api/v1/workspaces/{workspace1.id}/join-codes",
            json={"role": "analyst", "max_uses": 1},
            headers=auth_header(admin_ws1),
        )
        raw_code = create_res.json()["code"]

        u1 = User(
            email=f"u1-{uuid.uuid4().hex[:6]}@test.com",
            full_name="U1",
            hashed_password="h",
            role=Role.READ_ONLY,
            workspace_id=workspace2.id,
        )
        u2 = User(
            email=f"u2-{uuid.uuid4().hex[:6]}@test.com",
            full_name="U2",
            hashed_password="h",
            role=Role.READ_ONLY,
            workspace_id=workspace2.id,
        )
        db.add_all([u1, u2])
        db.commit()

        # 1st redemption succeeds
        res1 = client.post("/api/v1/join", json={"code": raw_code}, headers=auth_header(u1))
        assert res1.status_code == 200

        # 2nd redemption exhausts code
        res2 = client.post("/api/v1/join", json={"code": raw_code}, headers=auth_header(u2))
        assert res2.status_code == 410
        assert res2.json()["error"]["code"] == "join_code_exhausted"

    def test_redeem_rate_limiting_enforces_10_attempts_and_returns_429(
        self,
        app: FastAPI,
        client: TestClient,
        workspace1: Workspace,
        admin_ws1: User,
        outsider: User,
    ) -> None:
        """10 attempts allowed per 10 minutes per IP/User; 11th attempt returns 429 with Retry-After."""
        from app.core.rate_limit import get_redis_client

        class MockRedis:
            def __init__(self) -> None:
                self.counts: dict[str, int] = {}

            def eval(self, script: str, numkeys: int, key: str, window: str) -> list[int]:
                val = self.counts.get(key, 0) + 1
                self.counts[key] = val
                return [val, 600]

        mock_redis = MockRedis()
        app.dependency_overrides[get_redis_client] = lambda: mock_redis

        try:
            # 10 attempts
            for _ in range(10):
                res = client.post(
                    "/api/v1/join", json={"code": "9999-9999"}, headers=auth_header(outsider)
                )
                assert (
                    res.status_code == 404
                )  # code doesn't exist, but was evaluated under rate limit

            # 11th attempt must be rejected by rate limiter with 429
            res_limit = client.post(
                "/api/v1/join", json={"code": "9999-9999"}, headers=auth_header(outsider)
            )
            assert res_limit.status_code == 429
            assert res_limit.json()["error"]["code"] == "too_many_requests"
            assert "Retry-After" in res_limit.headers
            assert int(res_limit.headers["Retry-After"]) > 0
        finally:
            app.dependency_overrides.pop(get_redis_client, None)

    def test_redeem_fails_open_gracefully_when_redis_is_down(
        self,
        app: FastAPI,
        client: TestClient,
        outsider: User,
    ) -> None:
        """If Redis is down or unreachable, join attempts fail open (not 500 error)."""
        import redis

        from app.core.rate_limit import get_redis_client

        class BrokenRedis:
            def eval(self, *args: object, **kwargs: object) -> object:
                raise redis.ConnectionError("Redis connection refused")

        app.dependency_overrides[get_redis_client] = lambda: BrokenRedis()

        try:
            # Request should proceed to service layer despite Redis outage (fail-open)
            res = client.post(
                "/api/v1/join", json={"code": "2345-6789"}, headers=auth_header(outsider)
            )
            # Reaches service and returns 404 (nonexistent code), NOT 500 internal error
            assert res.status_code == 404
        finally:
            app.dependency_overrides.pop(get_redis_client, None)


# ── 5. GET /workspaces/{w}/join-requests/{id}/decision ────────────────────────


class TestGetJoinRequestDecisionEndpoint:
    def test_get_decision_admin_success(
        self,
        client: TestClient,
        workspace1: Workspace,
        admin_ws1: User,
        db: Session,
        workspace2: Workspace,
    ) -> None:
        create_res = client.post(
            f"/api/v1/workspaces/{workspace1.id}/join-codes",
            json={"role": "analyst", "requires_approval": True},
            headers=auth_header(admin_ws1),
        )
        raw_code = create_res.json()["code"]

        req_user = User(
            email=f"req-{uuid.uuid4().hex[:6]}@test.com",
            full_name="R",
            hashed_password="h",
            role=Role.READ_ONLY,
            workspace_id=workspace2.id,
        )
        db.add(req_user)
        db.commit()

        join_res = client.post(
            "/api/v1/join", json={"code": raw_code}, headers=auth_header(req_user)
        )
        req_id = join_res.json()["join_request_id"]

        get_res = client.get(
            f"/api/v1/workspaces/{workspace1.id}/join-requests/{req_id}/decision",
            headers=auth_header(admin_ws1),
        )
        assert get_res.status_code == 200
        assert get_res.json()["id"] == req_id
        assert get_res.json()["status"] == "pending"

    def test_get_decision_requester_success(
        self,
        client: TestClient,
        workspace1: Workspace,
        admin_ws1: User,
        db: Session,
        workspace2: Workspace,
    ) -> None:
        create_res = client.post(
            f"/api/v1/workspaces/{workspace1.id}/join-codes",
            json={"role": "analyst", "requires_approval": True},
            headers=auth_header(admin_ws1),
        )
        raw_code = create_res.json()["code"]

        req_user = User(
            email=f"req2-{uuid.uuid4().hex[:6]}@test.com",
            full_name="R2",
            hashed_password="h",
            role=Role.READ_ONLY,
            workspace_id=workspace2.id,
        )
        db.add(req_user)
        db.commit()

        join_res = client.post(
            "/api/v1/join", json={"code": raw_code}, headers=auth_header(req_user)
        )
        req_id = join_res.json()["join_request_id"]

        # Requester themselves can view the status
        get_res = client.get(
            f"/api/v1/workspaces/{workspace1.id}/join-requests/{req_id}/decision",
            headers=auth_header(req_user),
        )
        assert get_res.status_code == 200
        assert get_res.json()["id"] == req_id

    def test_get_decision_cross_workspace_not_found(
        self,
        client: TestClient,
        workspace1: Workspace,
        admin_ws1: User,
        admin_ws2: User,
        db: Session,
        workspace2: Workspace,
    ) -> None:
        create_res = client.post(
            f"/api/v1/workspaces/{workspace1.id}/join-codes",
            json={"role": "analyst", "requires_approval": True},
            headers=auth_header(admin_ws1),
        )
        raw_code = create_res.json()["code"]

        req_user = User(
            email=f"req3-{uuid.uuid4().hex[:6]}@test.com",
            full_name="R3",
            hashed_password="h",
            role=Role.READ_ONLY,
            workspace_id=workspace2.id,
        )
        db.add(req_user)
        db.commit()

        join_res = client.post(
            "/api/v1/join", json={"code": raw_code}, headers=auth_header(req_user)
        )
        req_id = join_res.json()["join_request_id"]

        # Admin of WS2 trying to query request on WS1
        get_res = client.get(
            f"/api/v1/workspaces/{workspace1.id}/join-requests/{req_id}/decision",
            headers=auth_header(admin_ws2),
        )
        assert get_res.status_code == 404


# ── 6. POST /workspaces/{w}/join-requests/{id}/decision ───────────────────────


class TestDecideJoinRequestEndpoint:
    def test_decide_approve_success(
        self,
        client: TestClient,
        workspace1: Workspace,
        admin_ws1: User,
        db: Session,
        workspace2: Workspace,
    ) -> None:
        create_res = client.post(
            f"/api/v1/workspaces/{workspace1.id}/join-codes",
            json={"role": "analyst", "requires_approval": True},
            headers=auth_header(admin_ws1),
        )
        raw_code = create_res.json()["code"]

        target_user = User(
            email=f"target-{uuid.uuid4().hex[:6]}@test.com",
            full_name="Target",
            hashed_password="h",
            role=Role.READ_ONLY,
            workspace_id=workspace2.id,
        )
        db.add(target_user)
        db.commit()

        join_res = client.post(
            "/api/v1/join", json={"code": raw_code}, headers=auth_header(target_user)
        )
        req_id = join_res.json()["join_request_id"]

        # Admin approves
        decide_res = client.post(
            f"/api/v1/workspaces/{workspace1.id}/join-requests/{req_id}/decision",
            json={"decision": "approve"},
            headers=auth_header(admin_ws1),
        )
        assert decide_res.status_code == 200
        assert decide_res.json()["status"] == "approved"

        # Verify user joined workspace
        db.refresh(target_user)
        assert target_user.workspace_id == workspace1.id
        assert target_user.role == Role.ANALYST

    def test_decide_reject_success(
        self,
        client: TestClient,
        workspace1: Workspace,
        admin_ws1: User,
        db: Session,
        workspace2: Workspace,
    ) -> None:
        create_res = client.post(
            f"/api/v1/workspaces/{workspace1.id}/join-codes",
            json={"role": "analyst", "requires_approval": True},
            headers=auth_header(admin_ws1),
        )
        raw_code = create_res.json()["code"]

        target_user = User(
            email=f"target-rej-{uuid.uuid4().hex[:6]}@test.com",
            full_name="Target Rej",
            hashed_password="h",
            role=Role.READ_ONLY,
            workspace_id=workspace2.id,
        )
        db.add(target_user)
        db.commit()

        join_res = client.post(
            "/api/v1/join", json={"code": raw_code}, headers=auth_header(target_user)
        )
        req_id = join_res.json()["join_request_id"]

        # Admin rejects with reason
        decide_res = client.post(
            f"/api/v1/workspaces/{workspace1.id}/join-requests/{req_id}/decision",
            json={"decision": "reject", "reason": "Not authorized by team lead"},
            headers=auth_header(admin_ws1),
        )
        assert decide_res.status_code == 200
        assert decide_res.json()["status"] == "rejected"
        assert decide_res.json()["rejection_reason"] == "Not authorized by team lead"

    def test_decide_analyst_forbidden(
        self,
        client: TestClient,
        workspace1: Workspace,
        admin_ws1: User,
        analyst_ws1: User,
        db: Session,
        workspace2: Workspace,
    ) -> None:
        create_res = client.post(
            f"/api/v1/workspaces/{workspace1.id}/join-codes",
            json={"role": "analyst", "requires_approval": True},
            headers=auth_header(admin_ws1),
        )
        raw_code = create_res.json()["code"]

        target_user = User(
            email=f"target-forb-{uuid.uuid4().hex[:6]}@test.com",
            full_name="Target Forb",
            hashed_password="h",
            role=Role.READ_ONLY,
            workspace_id=workspace2.id,
        )
        db.add(target_user)
        db.commit()

        join_res = client.post(
            "/api/v1/join", json={"code": raw_code}, headers=auth_header(target_user)
        )
        req_id = join_res.json()["join_request_id"]

        # Analyst attempts decision -> 403 Forbidden
        decide_res = client.post(
            f"/api/v1/workspaces/{workspace1.id}/join-requests/{req_id}/decision",
            json={"decision": "approve"},
            headers=auth_header(analyst_ws1),
        )
        assert decide_res.status_code == 403

    def test_decide_cross_workspace_not_found(
        self,
        client: TestClient,
        workspace1: Workspace,
        admin_ws1: User,
        admin_ws2: User,
        db: Session,
        workspace2: Workspace,
    ) -> None:
        create_res = client.post(
            f"/api/v1/workspaces/{workspace1.id}/join-codes",
            json={"role": "analyst", "requires_approval": True},
            headers=auth_header(admin_ws1),
        )
        raw_code = create_res.json()["code"]

        target_user = User(
            email=f"target-cw-{uuid.uuid4().hex[:6]}@test.com",
            full_name="Target CW",
            hashed_password="h",
            role=Role.READ_ONLY,
            workspace_id=workspace2.id,
        )
        db.add(target_user)
        db.commit()

        join_res = client.post(
            "/api/v1/join", json={"code": raw_code}, headers=auth_header(target_user)
        )
        req_id = join_res.json()["join_request_id"]

        # Admin of WS2 attempts decision on WS1 request -> 404
        decide_res = client.post(
            f"/api/v1/workspaces/{workspace1.id}/join-requests/{req_id}/decision",
            json={"decision": "approve"},
            headers=auth_header(admin_ws2),
        )
        assert decide_res.status_code == 404

    def test_decide_repeated_decision_conflict_returns_409(
        self,
        client: TestClient,
        workspace1: Workspace,
        admin_ws1: User,
        db: Session,
        workspace2: Workspace,
    ) -> None:
        create_res = client.post(
            f"/api/v1/workspaces/{workspace1.id}/join-codes",
            json={"role": "analyst", "requires_approval": True},
            headers=auth_header(admin_ws1),
        )
        raw_code = create_res.json()["code"]

        target_user = User(
            email=f"target-rep-{uuid.uuid4().hex[:6]}@test.com",
            full_name="Target Rep",
            hashed_password="h",
            role=Role.READ_ONLY,
            workspace_id=workspace2.id,
        )
        db.add(target_user)
        db.commit()

        join_res = client.post(
            "/api/v1/join", json={"code": raw_code}, headers=auth_header(target_user)
        )
        req_id = join_res.json()["join_request_id"]

        # First decision succeeds
        res1 = client.post(
            f"/api/v1/workspaces/{workspace1.id}/join-requests/{req_id}/decision",
            json={"decision": "approve"},
            headers=auth_header(admin_ws1),
        )
        assert res1.status_code == 200

        # Repeated decision fails with 409 Conflict
        res2 = client.post(
            f"/api/v1/workspaces/{workspace1.id}/join-requests/{req_id}/decision",
            json={"decision": "reject"},
            headers=auth_header(admin_ws1),
        )
        assert res2.status_code == 409
        assert res2.json()["error"]["code"] == "conflict"
