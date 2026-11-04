"""Silent re-login (US-19): refresh cookie on sign-in, rotation, replay detection, logout."""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.rate_limit import InMemoryRateLimiter, get_rate_limiter
from app.core.security import create_access_token
from app.models import User
from app.services import sessions
from app.services import signup as signup_service
from tests.conftest import TEST_PASSWORD

LOGIN = "/api/v1/auth/login"
SIGNUP = "/api/v1/auth/signup"
REFRESH = "/api/v1/auth/refresh"
LOGOUT = "/api/v1/auth/logout"
ME = "/api/v1/auth/me"
COOKIE = "rcd_refresh"
CSRF = {"X-Requested-With": "rcd"}


@dataclass
class Api:
    client: TestClient
    store: sessions.InMemorySessionStore
    now: list[float]

    def login(self, user: User) -> Response:
        return self.client.post(LOGIN, data={"username": user.email, "password": TEST_PASSWORD})

    def refresh(self, token: str | None, headers: dict[str, str] | None = None) -> Response:
        """Present exactly ``token`` (or no cookie), not whatever the client's jar holds."""
        self.client.cookies.clear()
        cookie = {"Cookie": f"{COOKIE}={token}"} if token else {}
        return self.client.post(REFRESH, headers={**CSRF, **cookie, **(headers or {})})

    def logout(self, token: str | None) -> Response:
        self.client.cookies.clear()
        cookie = {"Cookie": f"{COOKIE}={token}"} if token else {}
        return self.client.post(LOGOUT, headers={**CSRF, **cookie})

    def me(self, access_token: str) -> Response:
        return self.client.get(ME, headers={"Authorization": f"Bearer {access_token}"})


@pytest.fixture
def api(client: TestClient) -> Iterator[Api]:
    from app.main import app

    now = [1_000_000.0]
    store = sessions.InMemorySessionStore(clock=lambda: now[0])
    app.dependency_overrides[sessions.get_session_store] = lambda: store
    try:
        yield Api(client, store, now)
    finally:
        app.dependency_overrides.pop(sessions.get_session_store, None)


def _refresh_cookie(response: Response) -> str:
    token = response.cookies.get(COOKIE)
    assert token, f"no {COOKIE} cookie in {response.headers.get('set-cookie')!r}"
    return token


def _set_cookie_header(response: Response) -> str:
    return response.headers.get("set-cookie", "").lower()


class TestSignInSetsTheCookie:
    def test_login_sets_an_httponly_cookie_scoped_to_the_auth_routes(
        self, api: Api, user: User
    ) -> None:
        response = api.login(user)

        assert response.status_code == 200
        header = _set_cookie_header(response)
        assert f"{COOKIE}=" in header
        assert "httponly" in header
        assert "path=/api/v1/auth" in header
        assert "samesite=lax" in header
        assert f"max-age={get_settings().refresh_token_expire_days * 86400}" in header
        assert "secure" not in header  # test environment: plain http
        assert _refresh_cookie(response) not in response.text  # never in the body

    def test_sign_up_starts_a_session_too(self, api: Api) -> None:
        from app.main import app

        app.dependency_overrides[signup_service.get_join_code_redeemer] = lambda: (
            lambda db, code, user: None  # pending approval: the account exists, no workspace
        )
        app.dependency_overrides[get_rate_limiter] = InMemoryRateLimiter
        try:
            response = api.client.post(
                SIGNUP,
                json={
                    "email": "new@example.com",
                    "password": TEST_PASSWORD,
                    "full_name": "New Person",
                    "code": "ANY",
                },
            )
        finally:
            app.dependency_overrides.pop(signup_service.get_join_code_redeemer, None)
            app.dependency_overrides.pop(get_rate_limiter, None)

        assert response.status_code == 201
        assert api.refresh(_refresh_cookie(response)).status_code == 200


class TestRefresh:
    def test_the_cookie_buys_a_working_access_token_and_is_rotated(
        self, api: Api, user: User
    ) -> None:
        first = _refresh_cookie(api.login(user))

        response = api.refresh(first)

        assert response.status_code == 200
        assert response.json()["expires_in"] > 0
        assert api.me(response.json()["access_token"]).json()["id"] == str(user.id)
        assert _refresh_cookie(response) != first

    def test_a_chain_of_rotations_keeps_working(self, api: Api, user: User) -> None:
        token = _refresh_cookie(api.login(user))
        for _ in range(3):
            api.now[0] += 3600
            response = api.refresh(token)
            assert response.status_code == 200
            token = _refresh_cookie(response)

    def test_a_replayed_token_revokes_the_whole_session(self, api: Api, user: User) -> None:
        stolen = _refresh_cookie(api.login(user))
        current = _refresh_cookie(api.refresh(stolen))  # the real user rotates it
        api.now[0] += sessions.REUSE_GRACE_SECONDS + 1

        replay = api.refresh(stolen)

        assert replay.status_code == 401
        assert replay.json()["error"]["code"] == "session_expired"
        assert api.refresh(current).status_code == 401  # the rest of the session dies with it

    def test_two_tabs_refreshing_together_both_succeed(self, api: Api, user: User) -> None:
        shared = _refresh_cookie(api.login(user))
        assert api.refresh(shared).status_code == 200
        api.now[0] += sessions.REUSE_GRACE_SECONDS - 1

        assert api.refresh(shared).status_code == 200

    def test_another_sign_in_is_a_separate_session(self, api: Api, user: User) -> None:
        laptop = _refresh_cookie(api.login(user))
        phone = _refresh_cookie(api.login(user))
        api.logout(laptop)

        assert api.refresh(phone).status_code == 200

    @pytest.mark.parametrize("cookie", [None, "garbage", "a.b.c"])
    def test_no_usable_cookie_is_401_and_clears_it(self, api: Api, cookie: str | None) -> None:
        response = api.refresh(cookie)

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "session_expired"
        header = _set_cookie_header(response)
        assert f"{COOKIE}=" in header and "max-age=0" in header

    def test_an_access_token_is_not_a_refresh_token(self, api: Api, user: User) -> None:
        access, _ = create_access_token(user.id)
        assert api.refresh(access).status_code == 401

    def test_a_refresh_token_is_not_an_access_token(self, api: Api, user: User) -> None:
        refresh = _refresh_cookie(api.login(user))
        assert api.me(refresh).status_code == 401

    def test_a_deactivated_account_cannot_refresh(
        self, api: Api, user: User, db_session: Session
    ) -> None:
        token = _refresh_cookie(api.login(user))
        user.is_active = False
        db_session.commit()

        assert api.refresh(token).status_code == 401

    def test_the_csrf_header_is_required(self, api: Api, user: User) -> None:
        token = _refresh_cookie(api.login(user))
        api.client.cookies.clear()

        response = api.client.post(REFRESH, headers={"Cookie": f"{COOKIE}={token}"})

        assert response.status_code == 403
        assert api.refresh(token).status_code == 200  # the refused call did not use the token

    def test_redis_down_fails_closed(self, api: Api, user: User) -> None:
        from app.main import app

        class Down:
            def use(self, payload: Any) -> sessions.Use:
                raise sessions.SessionStoreUnavailableError()

            def revoke(self, session_id: str) -> None:
                raise sessions.SessionStoreUnavailableError()

        token = _refresh_cookie(api.login(user))
        app.dependency_overrides[sessions.get_session_store] = Down

        response = api.refresh(token)

        assert response.status_code == 503
        assert response.json()["error"]["code"] == "session_store_unavailable"


class TestLogout:
    def test_logout_revokes_the_session_and_clears_the_cookie(self, api: Api, user: User) -> None:
        token = _refresh_cookie(api.login(user))

        response = api.logout(token)

        assert response.status_code == 204
        header = _set_cookie_header(response)
        assert f"{COOKIE}=" in header and "max-age=0" in header
        assert api.refresh(token).status_code == 401

    @pytest.mark.parametrize("cookie", [None, "garbage"])
    def test_logout_without_a_valid_cookie_still_succeeds(
        self, api: Api, cookie: str | None
    ) -> None:
        assert api.logout(cookie).status_code == 204

    def test_logout_needs_the_csrf_header(self, api: Api) -> None:
        assert api.client.post(LOGOUT).status_code == 403


class TestCors:
    def test_the_spa_may_send_the_cookie_and_the_csrf_header(self, client: TestClient) -> None:
        response = client.options(
            REFRESH,
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "x-requested-with",
            },
        )

        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
        assert response.headers["access-control-allow-credentials"] == "true"
        assert "x-requested-with" in response.headers["access-control-allow-headers"].lower()
