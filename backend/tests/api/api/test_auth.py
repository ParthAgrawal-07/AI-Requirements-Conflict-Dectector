"""Auth API behaviour: login, /me, error format, RBAC, request IDs, CORS."""

import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
import pytest
from argon2 import PasswordHasher
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core import security
from app.core.auth import require_roles
from app.core.config import get_settings
from app.core.database import get_db
from app.core.errors import install_exception_handlers
from app.core.security import JWT_ALGORITHM, create_access_token
from app.models import Role, User
from tests.conftest import TEST_PASSWORD

LOGIN = "/api/v1/auth/login"
ME = "/api/v1/auth/me"


def login(client: TestClient, email: str, password: str = TEST_PASSWORD):
    return client.post(LOGIN, data={"username": email, "password": password})


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class TestLogin:
    def test_success_returns_bearer_token(self, client: TestClient, user: User) -> None:
        response = login(client, user.email)

        assert response.status_code == 200
        body = response.json()
        assert body["token_type"] == "bearer"
        assert body["expires_in"] == pytest.approx(
            get_settings().access_token_expire_minutes * 60, abs=5
        )
        assert security.decode_access_token(body["access_token"]).subject == user.id

    def test_email_is_case_insensitive(
        self, client: TestClient, make_user: Callable[..., User]
    ) -> None:
        make_user(email="Mixed.Case@Example.com")
        assert login(client, "MIXED.case@EXAMPLE.COM").status_code == 200

    def test_wrong_password_and_unknown_email_look_identical(
        self, client: TestClient, user: User
    ) -> None:
        wrong_password = login(client, user.email, "definitely-the-wrong-one")
        unknown_email = login(client, "nobody@example.com")

        assert wrong_password.status_code == unknown_email.status_code == 401
        assert wrong_password.json()["error"]["code"] == "invalid_credentials"
        assert wrong_password.json()["error"]["message"] == unknown_email.json()["error"]["message"]
        assert wrong_password.headers["WWW-Authenticate"] == "Bearer"

    def test_deactivated_user_cannot_log_in(
        self, client: TestClient, make_user: Callable[..., User]
    ) -> None:
        inactive = make_user(is_active=False)
        response = login(client, inactive.email)
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "invalid_credentials"

    def test_login_records_last_login(
        self, client: TestClient, user: User, db_session: Session
    ) -> None:
        assert user.last_login_at is None
        login(client, user.email)
        db_session.refresh(user)
        assert user.last_login_at is not None
        assert datetime.now(UTC) - user.last_login_at < timedelta(seconds=30)

    def test_password_hash_is_upgraded_when_parameters_change(
        self, client: TestClient, user: User, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        old_hash = user.hashed_password
        monkeypatch.setattr(
            security, "_hasher", PasswordHasher(time_cost=2, memory_cost=16, parallelism=1)
        )

        assert login(client, user.email).status_code == 200

        db_session.refresh(user)
        assert user.hashed_password != old_hash
        assert not security.password_needs_rehash(user.hashed_password)
        assert login(client, user.email).status_code == 200  # still works after the upgrade

    def test_missing_fields_return_422_without_echoing_input(self, client: TestClient) -> None:
        response = client.post(LOGIN, data={"username": "someone@example.com"})

        assert response.status_code == 422
        error = response.json()["error"]
        assert error["code"] == "validation_error"
        assert [d["field"] for d in error["details"]] == ["password"]
        assert "someone@example.com" not in response.text  # submitted values are never echoed

    def test_json_body_is_not_accepted(self, client: TestClient, user: User) -> None:
        response = client.post(LOGIN, json={"username": user.email, "password": TEST_PASSWORD})
        assert response.status_code == 422


class TestCurrentUser:
    def test_returns_profile_without_secrets(
        self, client: TestClient, user: User, auth_headers: dict[str, str]
    ) -> None:
        response = client.get(ME, headers=auth_headers)

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == str(user.id)
        assert body["email"] == user.email
        assert body["role"] == "analyst"
        assert body["workspace_id"] == str(user.workspace_id)
        assert "hashed_password" not in body
        assert "password" not in response.text

    def test_missing_token_is_401_with_standard_error_body(self, plain_client: TestClient) -> None:
        response = plain_client.get(ME)

        assert response.status_code == 401
        assert response.headers["WWW-Authenticate"] == "Bearer"
        error = response.json()["error"]
        assert error["code"] == "not_authenticated"
        assert error["request_id"] == response.headers["X-Request-ID"]

    @pytest.mark.parametrize("token", ["garbage", "a.b.c", ""])
    def test_malformed_token_is_401(self, plain_client: TestClient, token: str) -> None:
        assert plain_client.get(ME, headers=bearer(token)).status_code == 401

    def test_expired_token_is_401(self, client: TestClient, user: User) -> None:
        past = datetime.now(UTC) - timedelta(hours=3)
        token, _ = create_access_token(user.id, expires_delta=timedelta(minutes=5), now=past)
        response = client.get(ME, headers=bearer(token))
        assert response.status_code == 401
        assert response.json()["error"]["message"] == "Invalid or expired token"

    def test_token_signed_with_another_secret_is_401(self, client: TestClient, user: User) -> None:
        now = datetime.now(UTC)
        forged = jwt.encode(
            {
                "sub": str(user.id),
                "iss": security.JWT_ISSUER,
                "aud": security.JWT_AUDIENCE,
                "iat": now,
                "exp": now + timedelta(minutes=5),
                "jti": "x" * 8,
                "typ": "access",
            },
            "an-attackers-guess-that-is-long-enough-for-hs256",
            algorithm=JWT_ALGORITHM,
        )
        assert client.get(ME, headers=bearer(forged)).status_code == 401

    def test_token_for_deleted_user_is_401(self, client: TestClient) -> None:
        token, _ = create_access_token(uuid.uuid4())
        assert client.get(ME, headers=bearer(token)).status_code == 401

    def test_deactivating_a_user_revokes_existing_tokens_immediately(
        self, client: TestClient, user: User, auth_headers: dict[str, str], db_session: Session
    ) -> None:
        assert client.get(ME, headers=auth_headers).status_code == 200
        user.is_active = False
        db_session.commit()
        assert client.get(ME, headers=auth_headers).status_code == 401


def test_every_api_route_except_login_requires_authentication(plain_client: TestClient) -> None:
    """Security invariant (FR-37): a route added by any teammate must be authenticated by default.

    Checked through the OpenAPI schema, which is version-independent: an operation that depends
    on the bearer scheme is published with a ``security`` requirement.
    """
    from app.main import app

    api_paths = {p: ops for p, ops in app.openapi()["paths"].items() if p.startswith("/api/v1")}
    assert LOGIN in api_paths and ME in api_paths, "auth routes should be registered"
    for path, operations in api_paths.items():
        for method, operation in operations.items():
            if path == LOGIN:
                assert "security" not in operation, "login must stay public"
            else:
                assert operation.get("security"), f"{method.upper()} {path} is not protected"


@pytest.fixture
def rbac_client(db_session: Session) -> Iterator[TestClient]:
    app = FastAPI()
    install_exception_handlers(app)
    app.dependency_overrides[get_db] = lambda: db_session

    @app.get("/admin-only")
    def admin_only(who: Annotated[User, Depends(require_roles(Role.ADMIN))]) -> dict[str, str]:
        return {"user": who.email}

    @app.get("/reviewers")
    def reviewers(
        who: Annotated[User, Depends(require_roles(Role.COMPLIANCE_REVIEWER, Role.ADMIN))],
    ) -> dict[str, str]:
        return {"user": who.email}

    with TestClient(app) as test_client:
        yield test_client


class TestRoleBasedAccess:
    @pytest.mark.parametrize(
        ("role", "path", "expected"),
        [
            (Role.ADMIN, "/admin-only", 200),
            (Role.ANALYST, "/admin-only", 403),
            (Role.READ_ONLY, "/admin-only", 403),
            (Role.COMPLIANCE_REVIEWER, "/admin-only", 403),
            (Role.COMPLIANCE_REVIEWER, "/reviewers", 200),
            (Role.ADMIN, "/reviewers", 200),
            (Role.ANALYST, "/reviewers", 403),
        ],
    )
    def test_role_matrix(
        self,
        rbac_client: TestClient,
        make_user: Callable[..., User],
        role: Role,
        path: str,
        expected: int,
    ) -> None:
        member = make_user(role=role)
        token, _ = create_access_token(member.id)
        response = rbac_client.get(path, headers=bearer(token))
        assert response.status_code == expected
        if expected == 403:
            assert response.json()["error"]["code"] == "forbidden"

    def test_unauthenticated_is_401_not_403(self, rbac_client: TestClient) -> None:
        assert rbac_client.get("/admin-only").status_code == 401

    def test_require_roles_needs_at_least_one_role(self) -> None:
        with pytest.raises(ValueError):
            require_roles()


class TestErrorsAndMiddleware:
    def test_unknown_route_uses_standard_error_body(self, plain_client: TestClient) -> None:
        response = plain_client.get("/api/v1/does-not-exist")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_wrong_method_uses_standard_error_body(self, plain_client: TestClient) -> None:
        response = plain_client.get(LOGIN)
        assert response.status_code == 405
        assert response.json()["error"]["code"] == "method_not_allowed"

    def test_safe_incoming_request_id_is_propagated(self, plain_client: TestClient) -> None:
        response = plain_client.get("/health", headers={"X-Request-ID": "trace-abc-12345"})
        assert response.headers["X-Request-ID"] == "trace-abc-12345"

    def test_unsafe_incoming_request_id_is_replaced(self, plain_client: TestClient) -> None:
        response = plain_client.get("/health", headers={"X-Request-ID": "bad id\twith spaces"})
        assert response.headers["X-Request-ID"] != "bad id\twith spaces"
        assert len(response.headers["X-Request-ID"]) == 32

    def test_nosniff_header_set(self, plain_client: TestClient) -> None:
        assert plain_client.get("/health").headers["X-Content-Type-Options"] == "nosniff"

    def test_unhandled_exception_returns_generic_500_without_leaking_details(self) -> None:
        app = FastAPI()
        install_exception_handlers(app)

        @app.get("/boom")
        def boom() -> None:
            raise RuntimeError("secret database password is hunter2")

        with TestClient(app, raise_server_exceptions=False) as test_client:
            response = test_client.get("/boom")

        assert response.status_code == 500
        assert response.json()["error"]["code"] == "internal_error"
        assert "hunter2" not in response.text

    def test_cors_allows_configured_origin(self, plain_client: TestClient) -> None:
        response = plain_client.options(
            LOGIN,
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "http://localhost:5173"

    def test_cors_does_not_allow_other_origins(self, plain_client: TestClient) -> None:
        response = plain_client.options(
            LOGIN,
            headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
        )
        assert "access-control-allow-origin" not in response.headers
