"""POST /auth/signup — there is no open sign-up: an account needs a valid join code (US-19)."""

import sys
import types
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Environment, get_settings
from app.core.errors import ConflictError, ForbiddenError, InvalidJoinCodeError, NotFoundError
from app.core.permissions import DefaultRole
from app.core.rate_limit import (
    FallbackRateLimiter,
    InMemoryRateLimiter,
    RateLimitUnavailableError,
    TooManyRequestsError,
    get_rate_limiter,
    hash_key_part,
)
from app.models import Membership, Role, User, Workspace
from app.services import signup as signup_service
from app.services.membership import add_member, get_default_role
from tests.conftest import TEST_PASSWORD

SIGNUP = "/api/v1/auth/signup"
ME = "/api/v1/auth/me"
GOOD = "GOOD-CODE"
NEEDS_APPROVAL = "ASK-FIRST"


class JoinRequest:
    """Stands in for Madhav's pending join request (anything that is not a Membership)."""


@pytest.fixture
def redeem_calls() -> list[tuple[str, str]]:
    return []


@pytest.fixture
def api(
    client: TestClient,
    workspace: Workspace,
    redeem_calls: list[tuple[str, str]],
) -> Iterator[TestClient]:
    """The app with a fake ``redeem`` (the contract of Madhav's service) and an in-memory limiter."""
    from app.main import app

    def fake_redeem(db: Session, code: str, user: User) -> Any:
        redeem_calls.append((code, user.email))
        if code == GOOD:
            return add_member(
                db,
                workspace_id=workspace.id,
                user_id=user.id,
                role_id=get_default_role(db, DefaultRole.DEVELOPER).id,
                via_join_code=True,
                commit=False,
            )
        if code == NEEDS_APPROVAL:
            return JoinRequest()
        raise InvalidJoinCodeError()  # one generic error for every unusable code (NFR-35)

    limiter = InMemoryRateLimiter()
    app.dependency_overrides[signup_service.get_join_code_redeemer] = lambda: fake_redeem
    app.dependency_overrides[get_rate_limiter] = lambda: limiter
    try:
        yield client
    finally:
        app.dependency_overrides.pop(signup_service.get_join_code_redeemer, None)
        app.dependency_overrides.pop(get_rate_limiter, None)


def body(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "email": "new.person@example.com",
        "password": TEST_PASSWORD,
        "full_name": "New Person",
        "code": GOOD,
    }
    values.update(overrides)
    return values


def user_count(db: Session) -> int:
    return db.scalar(select(func.count(User.id))) or 0


class TestSignupWithAValidCode:
    def test_creates_the_account_and_the_membership_and_signs_the_user_in(
        self, api: TestClient, db_session: Session, workspace: Workspace
    ) -> None:
        response = api.post(SIGNUP, json=body())

        assert response.status_code == 201
        data = response.json()
        assert data["join_status"] == "joined"
        assert data["workspace_id"] == str(workspace.id)
        assert data["token_type"] == "bearer" and data["expires_in"] > 0
        assert data["user"]["email"] == "new.person@example.com"
        assert data["user"]["platform_role"] is None
        assert "password" not in response.text and "hashed" not in response.text

        user = db_session.scalars(select(User).where(User.email == "new.person@example.com")).one()
        membership = db_session.scalars(
            select(Membership).where(Membership.user_id == user.id)
        ).one()
        assert membership.workspace_id == workspace.id
        assert db_session.get(Role, membership.role_id).name == "Developer"  # type: ignore[union-attr]

        me = api.get(ME, headers={"Authorization": f"Bearer {data['access_token']}"}).json()
        assert [(m["workspace_name"], m["role"]["name"]) for m in me["memberships"]] == [
            (workspace.name, "Developer")
        ]

    def test_the_email_is_normalised_and_the_code_is_trimmed(
        self, api: TestClient, redeem_calls: list[tuple[str, str]]
    ) -> None:
        response = api.post(SIGNUP, json=body(email="Mixed.Case@Example.COM", code=f"  {GOOD}  "))
        assert response.status_code == 201
        assert response.json()["user"]["email"] == "mixed.case@example.com"
        assert redeem_calls == [(GOOD, "mixed.case@example.com")]

    def test_needs_no_authentication(self, api: TestClient) -> None:
        assert api.post(SIGNUP, json=body()).status_code == 201  # no Authorization header

    def test_a_code_that_needs_approval_creates_an_account_without_a_workspace(
        self, api: TestClient, db_session: Session
    ) -> None:
        response = api.post(SIGNUP, json=body(code=NEEDS_APPROVAL))

        assert response.status_code == 201
        assert response.json()["join_status"] == "pending_approval"
        assert response.json()["workspace_id"] is None
        user = db_session.scalars(select(User).where(User.email == "new.person@example.com")).one()
        assert (
            db_session.scalars(select(Membership).where(Membership.user_id == user.id)).all() == []
        )


class TestSignupFailures:
    def test_a_bad_code_creates_nothing(
        self, api: TestClient, db_session: Session, redeem_calls: list[tuple[str, str]]
    ) -> None:
        before = user_count(db_session)

        response = api.post(SIGNUP, json=body(code="WRONG-CODE"))

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "signup_refused"
        assert user_count(db_session) == before, "no orphan account for a bad code"
        assert redeem_calls  # the code *was* checked

    def test_the_same_email_can_retry_with_a_good_code_after_a_bad_one(
        self, api: TestClient
    ) -> None:
        assert api.post(SIGNUP, json=body(code="WRONG-CODE")).status_code == 400
        assert api.post(SIGNUP, json=body()).status_code == 201

    def test_a_weak_password_is_rejected_before_the_code_is_used(
        self, api: TestClient, db_session: Session, redeem_calls: list[tuple[str, str]]
    ) -> None:
        before = user_count(db_session)
        response = api.post(SIGNUP, json=body(password="short"))

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "weak_password"
        assert "at least 12 characters" in response.json()["error"]["message"]
        assert user_count(db_session) == before
        assert redeem_calls == []  # a use of the code is never spent on an invalid request

    def test_an_existing_email_is_refused_without_using_the_code(
        self, api: TestClient, user: User, redeem_calls: list[tuple[str, str]]
    ) -> None:
        response = api.post(SIGNUP, json=body(email=user.email.upper()))
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "signup_refused"
        assert "sign in" in response.json()["error"]["message"]
        assert redeem_calls == []

    @pytest.mark.parametrize(
        "payload",
        [
            {"email": "not-an-email"},
            {"code": ""},
            {"code": "x" * 65},
            {"full_name": ""},
            {"password": ""},
        ],
    )
    def test_invalid_input_is_a_422(self, api: TestClient, payload: dict[str, object]) -> None:
        response = api.post(SIGNUP, json=body(**payload))
        assert response.status_code == 422
        assert TEST_PASSWORD not in response.text  # submitted values are never echoed

    @pytest.mark.parametrize("missing", ["email", "password", "full_name", "code"])
    def test_every_field_is_required_in_particular_the_code(
        self, api: TestClient, missing: str
    ) -> None:
        payload = body()
        del payload[missing]
        assert api.post(SIGNUP, json=payload).status_code == 422

    def test_an_unexpected_failure_while_redeeming_rolls_the_account_back(
        self, api: TestClient, db_session: Session
    ) -> None:
        from app.main import app

        def exploding(_db: Session, _code: str, _user: User) -> Any:
            raise RuntimeError("database fell over")

        app.dependency_overrides[signup_service.get_join_code_redeemer] = lambda: exploding
        before = user_count(db_session)
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post(SIGNUP, json=body())
        assert response.status_code == 500
        assert user_count(db_session) == before


def refusal_of(response: Any) -> tuple[int, str, str]:
    error = response.json()["error"]
    return response.status_code, error["code"], error["message"]


class TestNoEmailEnumeration:
    """Sign-up must not reveal which e-mails have accounts — with or without a valid code."""

    def test_an_existing_email_gets_the_same_answer_as_an_invalid_code(
        self, api: TestClient, user: User
    ) -> None:
        existing_with_good_code = api.post(SIGNUP, json=body(email=user.email, code=GOOD))
        existing_with_bad_code = api.post(SIGNUP, json=body(email=user.email, code="WRONG"))
        new_with_bad_code = api.post(SIGNUP, json=body(email="nobody@example.com", code="WRONG"))

        assert (
            refusal_of(existing_with_good_code)
            == refusal_of(existing_with_bad_code)
            == refusal_of(new_with_bad_code)
        )
        assert refusal_of(new_with_bad_code)[:2] == (400, "signup_refused")

    def test_the_refusal_names_neither_the_code_nor_the_email_as_the_reason(
        self, api: TestClient, user: User
    ) -> None:
        message = refusal_of(api.post(SIGNUP, json=body(email=user.email)))[2]
        assert "already registered" not in message and "not valid" not in message
        assert "join code" in message and "sign in" in message  # both causes are mentioned

    def test_a_weak_password_is_reported_the_same_for_new_and_existing_emails(
        self, api: TestClient, user: User
    ) -> None:
        """If the password were checked after the e-mail lookup, 'weak_password' vs 'refused'
        would itself be an oracle for registered addresses."""
        existing = api.post(SIGNUP, json=body(email=user.email, password="short"))
        fresh = api.post(SIGNUP, json=body(email="fresh@example.com", password="short"))
        assert refusal_of(existing) == refusal_of(fresh)
        assert refusal_of(fresh)[:2] == (400, "weak_password")

    @pytest.mark.parametrize(
        "raised", [NotFoundError("x"), ConflictError("x"), ForbiddenError("x")]
    )
    def test_any_client_error_from_redeem_is_folded_into_the_same_refusal(
        self, api: TestClient, db_session: Session, raised: Exception
    ) -> None:
        from app.main import app

        def refusing(_db: Session, _code: str, _user: User) -> Any:
            raise raised

        app.dependency_overrides[signup_service.get_join_code_redeemer] = lambda: refusing
        before = user_count(db_session)

        response = api.post(SIGNUP, json=body(email="folded@example.com"))

        assert refusal_of(response)[:2] == (400, "signup_refused")
        assert user_count(db_session) == before

    def test_rate_limit_and_outage_errors_from_redeem_are_not_hidden(
        self, api: TestClient, db_session: Session
    ) -> None:
        from app.main import app

        def throttled(_db: Session, _code: str, _user: User) -> Any:
            raise TooManyRequestsError(30)

        app.dependency_overrides[signup_service.get_join_code_redeemer] = lambda: throttled
        before = user_count(db_session)

        response = api.post(SIGNUP, json=body(email="throttled@example.com"))

        assert response.status_code == 429  # a different problem: say so
        assert user_count(db_session) == before

    def test_losing_a_race_for_the_same_email_is_also_the_refusal(
        self, api: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from sqlalchemy.exc import IntegrityError

        def racing(*_args: object, **_kwargs: object) -> User:
            raise IntegrityError("INSERT", {}, Exception("duplicate key"))

        monkeypatch.setattr(signup_service, "create_user", racing)
        response = api.post(SIGNUP, json=body(email="racer@example.com"))
        assert refusal_of(response)[:2] == (400, "signup_refused")


class TestJoinCodesNeverGrantPrivilegedRoles:
    @pytest.mark.parametrize("role", [DefaultRole.OWNER, DefaultRole.ADMIN])
    def test_a_redeemer_that_tries_to_grant_owner_or_admin_is_stopped_and_nothing_is_created(
        self, api: TestClient, workspace: Workspace, db_session: Session, role: DefaultRole
    ) -> None:
        from app.main import app

        def greedy(db: Session, _code: str, user: User) -> Any:
            return add_member(
                db,
                workspace_id=workspace.id,
                user_id=user.id,
                role_id=get_default_role(db, role).id,
                via_join_code=True,  # what the join-code service must always pass
                commit=False,
            )

        app.dependency_overrides[signup_service.get_join_code_redeemer] = lambda: greedy
        before = user_count(db_session)

        response = api.post(SIGNUP, json=body(email="climber@example.com"))

        assert refusal_of(response)[:2] == (400, "signup_refused")
        assert user_count(db_session) == before


class TestSignupRateLimit:
    def test_the_sixth_attempt_per_minute_from_one_address_is_429(self, api: TestClient) -> None:
        limit = get_settings().signup_attempts_per_minute
        for i in range(limit):
            assert (
                api.post(SIGNUP, json=body(email=f"p{i}@example.com", code="WRONG")).status_code
                == 400
            )

        response = api.post(SIGNUP, json=body(email="one-more@example.com", code=GOOD))

        assert response.status_code == 429
        assert response.json()["error"]["code"] == "too_many_requests"
        assert 1 <= int(response.headers["Retry-After"]) <= 60

    def test_guessing_codes_for_one_email_from_many_addresses_is_limited_too(
        self, api: TestClient
    ) -> None:
        from app.main import app

        limiter: InMemoryRateLimiter = app.dependency_overrides[get_rate_limiter]()
        limit = get_settings().signup_attempts_per_minute
        for _ in range(limit):  # as if five different machines already tried this e-mail
            limiter.hit(
                f"signup:email:{hash_key_part('victim@example.com')}",
                limit=limit,
                window_seconds=60,
            )

        blocked = api.post(SIGNUP, json=body(email="Victim@Example.com"))
        other = api.post(SIGNUP, json=body(email="bystander@example.com"))

        assert blocked.status_code == 429
        assert other.status_code == 201

    def test_a_correct_code_still_counts_as_an_attempt(self, api: TestClient) -> None:
        limit = get_settings().signup_attempts_per_minute
        for i in range(limit):
            assert api.post(SIGNUP, json=body(email=f"ok{i}@example.com")).status_code == 201
        assert api.post(SIGNUP, json=body(email="late@example.com")).status_code == 429

    def test_behind_one_trusted_proxy_each_real_client_has_its_own_budget(
        self, api: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(get_settings(), "trusted_proxy_hops", 1)
        limit = get_settings().signup_attempts_per_minute
        busy = {"X-Forwarded-For": "203.0.113.7"}
        for i in range(limit):
            api.post(SIGNUP, json=body(email=f"busy{i}@example.com", code="WRONG"), headers=busy)
        assert api.post(SIGNUP, json=body(email="b@example.com"), headers=busy).status_code == 429

        other = api.post(
            SIGNUP,
            json=body(email="other@example.com"),
            headers={"X-Forwarded-For": "198.51.100.9"},
        )
        assert other.status_code == 201  # not throttled by someone else's attempts

    def test_a_forged_forwarded_for_header_cannot_buy_a_fresh_budget(
        self, api: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(get_settings(), "trusted_proxy_hops", 1)
        limit = get_settings().signup_attempts_per_minute
        for i in range(limit):  # the proxy appends the true address (203.0.113.7) on the right
            api.post(
                SIGNUP,
                json=body(email=f"forge{i}@example.com", code="WRONG"),
                headers={"X-Forwarded-For": f"10.0.0.{i}, 203.0.113.7"},
            )
        spoofed = api.post(
            SIGNUP,
            json=body(email="forge-final@example.com"),
            headers={"X-Forwarded-For": "10.9.9.9, 203.0.113.7"},
        )
        assert spoofed.status_code == 429

    def test_without_a_trusted_proxy_the_header_is_ignored(self, api: TestClient) -> None:
        limit = get_settings().signup_attempts_per_minute
        for i in range(limit):
            api.post(
                SIGNUP,
                json=body(email=f"h{i}@example.com", code="WRONG"),
                headers={"X-Forwarded-For": f"10.0.0.{i}"},
            )
        response = api.post(
            SIGNUP, json=body(email="h-final@example.com"), headers={"X-Forwarded-For": "10.1.1.1"}
        )
        assert response.status_code == 429  # one socket peer, however many addresses it claims

    def test_sign_up_still_works_and_is_still_limited_when_redis_is_down(
        self, api: TestClient
    ) -> None:
        """PR review #4: an unreachable Redis must not block every sign-up with a 503."""
        from app.main import app

        class Down:
            def hit(self, key: str, *, limit: int, window_seconds: int) -> int | None:
                raise RateLimitUnavailableError()

        degraded = FallbackRateLimiter(Down(), InMemoryRateLimiter())
        app.dependency_overrides[get_rate_limiter] = lambda: degraded

        assert api.post(SIGNUP, json=body()).status_code == 201
        limit = get_settings().signup_attempts_per_minute
        for i in range(limit):
            api.post(SIGNUP, json=body(email=f"x{i}@example.com", code="WRONG"))
        assert api.post(SIGNUP, json=body(email="late@example.com")).status_code == 429

    def test_the_limiter_key_holds_a_hash_not_the_email(self) -> None:
        assert "victim" not in hash_key_part("victim@example.com")
        assert hash_key_part(" Victim@Example.com ") == hash_key_part("victim@example.com")


class TestJoinCodeRedeemerWiring:
    """Until Madhav's ``app.services.join_codes`` exists, a development stub stands in."""

    def test_the_real_service_is_used_when_it_exists(self, monkeypatch: pytest.MonkeyPatch) -> None:
        module = types.ModuleType("app.services.join_codes")
        module.redeem = lambda db, code, user: "real"  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "app.services.join_codes", module)
        assert signup_service.get_join_code_redeemer()(None, "c", None) == "real"  # type: ignore[arg-type]

    def test_the_stub_is_used_when_the_module_does_not_exist_yet(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setitem(sys.modules, "app.services.join_codes", None)  # import -> ImportError
        # ModuleNotFoundError for exactly this module -> stub
        redeemer = signup_service.get_join_code_redeemer()
        assert redeemer is signup_service._dev_stub_redeem

    def test_a_broken_import_inside_the_real_module_is_not_hidden(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def broken(_name: str) -> object:
            raise ModuleNotFoundError("No module named 'redis_missing'", name="redis_missing")

        monkeypatch.setattr(signup_service.importlib, "import_module", broken)
        with pytest.raises(ModuleNotFoundError, match="redis_missing"):
            signup_service.get_join_code_redeemer()

    def test_a_module_without_redeem_falls_back_to_the_stub(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setitem(sys.modules, "app.services.join_codes", types.ModuleType("x"))
        assert signup_service.get_join_code_redeemer() is signup_service._dev_stub_redeem

    def test_the_stub_accepts_only_the_development_code_into_the_demo_workspace(
        self,
        db_session: Session,
        make_workspace: Callable[..., Workspace],
        make_user: Callable[..., User],
    ) -> None:
        demo = make_workspace(signup_service.DEV_JOIN_WORKSPACE)
        newcomer = make_user(role=None)

        with pytest.raises(InvalidJoinCodeError):
            signup_service._dev_stub_redeem(db_session, "NOPE", newcomer)
        membership = signup_service._dev_stub_redeem(db_session, " test1234 ", newcomer)
        assert membership.workspace_id == demo.id

    def test_the_stub_is_unavailable_in_production(
        self, db_session: Session, monkeypatch: pytest.MonkeyPatch, make_user: Callable[..., User]
    ) -> None:
        from types import SimpleNamespace

        from app.core.errors import ServiceUnavailableError

        monkeypatch.setattr(
            signup_service,
            "get_settings",
            lambda: SimpleNamespace(environment=Environment.PRODUCTION),
        )
        with pytest.raises(ServiceUnavailableError):
            signup_service._dev_stub_redeem(
                db_session, signup_service.DEV_JOIN_CODE, make_user(role=None)
            )
