"""Join-code abuse tests (Affan — US-25, NFR-35).

* brute force: guessing is cut off by the rate limits on ``POST /join`` and ``POST /auth/signup``;
* expiry, use limit and revocation are enforced — with one identical answer for every refusal,
  so an attacker cannot tell a nearly-valid code from a random one;
* the database never holds a usable code;
* two people racing for the last use of a code: exactly one gets in (row lock).
"""

import hashlib
import threading
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.core import security
from app.core.errors import InvalidJoinCodeError
from app.core.permissions import DefaultRole
from app.core.rate_limit import InMemoryRateLimiter, get_rate_limiter
from app.models import JoinCode, JoinCodeStatus, Membership, User, Workspace
from app.services import join_codes as join_code_service
from app.services.membership import get_default_role
from app.services.users import create_user
from tests.conftest import _run_migrations

API = "/api/v1"


@pytest.fixture
def limiter(client: TestClient) -> Iterator[InMemoryRateLimiter]:
    from app.main import app

    limiter = InMemoryRateLimiter()
    app.dependency_overrides[get_rate_limiter] = lambda: limiter
    yield limiter
    app.dependency_overrides.pop(get_rate_limiter, None)


@pytest.fixture
def issue(
    db_session: Session, workspace: Workspace, make_user: Callable[..., User]
) -> Callable[..., join_code_service.CreatedCode]:
    manager = make_user(role=DefaultRole.PROJECT_MANAGER)

    def build(**kwargs: object) -> join_code_service.CreatedCode:
        values: dict[str, object] = {"expires_in_days": 7}
        values.update(kwargs)
        return join_code_service.create_code(
            db_session,
            workspace_id=workspace.id,
            creator=manager,
            role_id=get_default_role(db_session, DefaultRole.DEVELOPER).id,
            **values,  # type: ignore[arg-type]
        )

    return build


def _headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {security.create_access_token(user.id)[0]}"}


def _signup(client: TestClient, code: str, email: str) -> Response:
    return client.post(
        f"{API}/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery-staple",
            "full_name": "Guesser",
            "code": code,
        },
    )


class TestBruteForce:
    def test_guessing_with_post_join_is_cut_off_after_ten_attempts(
        self, client: TestClient, make_user: Callable[..., User], limiter: InMemoryRateLimiter
    ) -> None:
        headers = _headers(make_user(role=None))
        statuses = [
            client.post(
                f"{API}/join", json={"code": join_code_service.generate_code()}, headers=headers
            ).status_code
            for _ in range(12)
        ]
        assert statuses[:10] == [400] * 10
        assert set(statuses[10:]) == {429}

    def test_the_limit_holds_across_users_from_one_address(
        self, client: TestClient, make_user: Callable[..., User], limiter: InMemoryRateLimiter
    ) -> None:
        statuses = [
            client.post(
                f"{API}/join",
                json={"code": "ZZZZ-ZZZZ"},
                headers=_headers(make_user(role=None)),  # a fresh account per attempt
            ).status_code
            for _ in range(11)
        ]
        assert statuses[-1] == 429

    def test_a_valid_code_after_the_limit_is_still_refused(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        limiter: InMemoryRateLimiter,
        issue: Callable[..., join_code_service.CreatedCode],
    ) -> None:
        good = issue().code
        headers = _headers(make_user(role=None))
        for _ in range(10):
            client.post(f"{API}/join", json={"code": "ZZZZ-ZZZZ"}, headers=headers)

        assert client.post(f"{API}/join", json={"code": good}, headers=headers).status_code == 429

    def test_guessing_through_sign_up_is_limited_too(
        self, client: TestClient, limiter: InMemoryRateLimiter
    ) -> None:
        statuses = [_signup(client, "ZZZZ-ZZZZ", f"g{i}@example.com").status_code for i in range(6)]
        assert statuses[:5] == [400] * 5
        assert statuses[5] == 429


class TestLifecycle:
    def _refusal(self, db: Session, code: str) -> str:
        newcomer = create_user(
            db,
            email=f"x-{uuid.uuid4().hex[:8]}@example.com",
            password="correct-horse-battery-staple",
            full_name="X",
        )
        with pytest.raises(InvalidJoinCodeError) as refused:
            join_code_service.redeem(db, code, newcomer)
        return refused.value.message

    def test_expiry_use_limit_and_revocation_give_one_identical_answer(
        self,
        db_session: Session,
        issue: Callable[..., join_code_service.CreatedCode],
        make_user: Callable[..., User],
    ) -> None:
        expired = issue()
        expired.join_code.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        used_up = issue(max_uses=1)
        join_code_service.redeem(db_session, used_up.code, make_user(role=None))
        revoked = issue()
        join_code_service.revoke_code(
            db_session, join_code=revoked.join_code, actor=make_user(role=DefaultRole.OWNER)
        )

        answers = {
            self._refusal(db_session, expired.code),
            self._refusal(db_session, used_up.code),
            self._refusal(db_session, revoked.code),
            self._refusal(db_session, join_code_service.generate_code()),  # random guess
        }

        assert answers == {InvalidJoinCodeError().message}

    def test_sign_up_refusals_are_byte_identical_for_every_kind_of_bad_code(
        self,
        client: TestClient,
        db_session: Session,
        issue: Callable[..., join_code_service.CreatedCode],
        limiter: InMemoryRateLimiter,
    ) -> None:
        revoked = issue()
        revoked.join_code.status = JoinCodeStatus.REVOKED
        db_session.commit()

        bodies = []
        for i, code in enumerate([revoked.code, "ZZZZ-ZZZZ", "not even a code"]):
            limiter.reset()
            response = _signup(client, code, f"r{i}@example.com")
            body = response.json()
            body["error"].pop("request_id", None)
            bodies.append(body)
        assert bodies[0] == bodies[1] == bodies[2]


def test_the_database_holds_no_usable_code(
    db_session: Session, issue: Callable[..., join_code_service.CreatedCode]
) -> None:
    created = issue()
    canonical = join_code_service.canonicalize(created.code)
    assert canonical is not None

    row = db_session.scalars(select(JoinCode).where(JoinCode.id == created.join_code.id)).one()
    stored = " ".join(str(value) for value in vars(row).values())

    assert canonical not in stored and created.code not in stored
    # Without the pepper the hash is useless: a plain SHA-256 of the code does not match it.
    assert row.code_hash != hashlib.sha256(canonical.encode()).hexdigest()


def test_two_people_racing_for_the_last_use_only_one_gets_in(scratch_engine: Engine) -> None:
    """Real concurrency: two connections, committed data, the row lock decides."""
    _run_migrations(scratch_engine)
    with Session(scratch_engine) as setup:
        workspace = Workspace(name="Race")
        setup.add(workspace)
        setup.commit()
        owner = create_user(
            setup, email="owner@example.com", password="correct-horse-battery-staple",
            full_name="Owner",
        )  # fmt: skip
        racers = [
            create_user(
                setup,
                email=f"racer{i}@example.com",
                password="correct-horse-battery-staple",
                full_name=f"Racer {i}",
            )  # fmt: skip
            for i in range(2)
        ]
        code = join_code_service.create_code(
            setup,
            workspace_id=workspace.id,
            creator=owner,
            role_id=get_default_role(setup, DefaultRole.DEVELOPER).id,
            expires_in_days=1,
            max_uses=1,
        ).code
        racer_ids = [racer.id for racer in racers]
        workspace_id = workspace.id

    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def race(user_id: uuid.UUID) -> None:
        with Session(scratch_engine) as db:
            user = db.get(User, user_id)
            assert user is not None
            barrier.wait()
            try:
                join_code_service.redeem(db, code, user)
                db.commit()
                outcomes.append("joined")
            except InvalidJoinCodeError:
                db.rollback()
                outcomes.append("refused")

    threads = [threading.Thread(target=race, args=(user_id,)) for user_id in racer_ids]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert sorted(outcomes) == ["joined", "refused"]
    with Session(scratch_engine) as check:
        members = check.scalar(
            select(func.count(Membership.id)).where(Membership.workspace_id == workspace_id)
        )
        assert members == 1
