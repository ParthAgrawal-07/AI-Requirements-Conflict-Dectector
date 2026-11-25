"""Rate limits under attack (Affan — Sprint 6 security pass; NFR-28, NFR-35, US-25).

Sign-up and join-code guessing are covered by ``test_join_codes.py``. This module covers every
other limited route — the ones a signed-in member could use to flood a channel or burn the AI
budget:

==============================================  ===============================  ============
Route                                           Bucket (per user)                Limit
==============================================  ===============================  ============
``POST /channels/{c}/messages``                 ``messages``                     30 / min
``POST /channels/{c}/requirement-posts``        ``messages`` (shared)            30 / min
``POST /projects/{p}/requirements``             ``messages`` (shared)            30 / min
``POST /projects/{p}/similar``                  ``similar``                      60 / min
``POST /projects/{p}/preflight``                ``preflight``                    6 / min
``POST /projects/{p}/improve-wording``          ``wording``                      6 / min
``POST /projects/{p}/changes/summary``          ``change-summary``               6 / min
==============================================  ===============================  ============

For each: once the bucket is full the route answers **429** with ``Retry-After``, stores nothing
and never reaches the model; the limit is per user (a teammate is not blocked); and buckets do
not leak into each other.
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.change_summary import SUMMARIES_PER_MINUTE
from app.classification.budget import CountingBudget, get_budget_guard
from app.classification.llm_client import FakeTransport, LLMClient, get_llm_client
from app.core.config import get_settings
from app.core.permissions import DefaultRole
from app.core.rate_limit import InMemoryRateLimiter, get_rate_limiter
from app.embeddings.model import HashingEmbedder, get_embedder
from app.models import Channel, Message, Project, Requirement, User
from tests.api.conftest import headers_for

pytestmark = pytest.mark.integration

FIELDS: dict[str, Any] = {
    "template": "event_driven",
    "slots": {
        "trigger": "the user is inactive for 5 minutes",
        "system": "mobile app",
        "response": "log the user out",
    },
    "type": "functional",
    "priority": "must",
    "tags": ["session"],
    "rationale": "RBI guideline on idle sessions",
}


@dataclass
class Stack:
    limiter: InMemoryRateLimiter
    transport: FakeTransport


@pytest.fixture
def stack() -> Iterator[Stack]:
    from app.main import app

    state = Stack(limiter=InMemoryRateLimiter(), transport=FakeTransport([]))
    llm = LLMClient(state.transport, CountingBudget(100))
    app.dependency_overrides[get_rate_limiter] = lambda: state.limiter
    app.dependency_overrides[get_embedder] = HashingEmbedder
    app.dependency_overrides[get_llm_client] = lambda: llm
    app.dependency_overrides[get_budget_guard] = lambda: CountingBudget(100)
    yield state
    for dependency in (get_rate_limiter, get_embedder, get_llm_client, get_budget_guard):
        app.dependency_overrides.pop(dependency, None)


@pytest.fixture
def member(make_user: Callable[..., User]) -> User:
    return make_user(role=DefaultRole.BUSINESS_ANALYST)


@pytest.fixture
def channel(db_session: Session, project: Project) -> Channel:
    channel = Channel(project_id=project.id, name="general", is_default=True)
    db_session.add(channel)
    db_session.commit()
    return channel


def fill(limiter: InMemoryRateLimiter, bucket: str, user: User, limit: int) -> None:
    """Spend a user's whole allowance in one bucket, as a flood would."""
    for _ in range(limit):
        assert limiter.hit(f"{bucket}:user:{user.id}", limit=limit, window_seconds=60) is None


def assert_limited(response: Any) -> None:
    assert response.status_code == 429, response.text
    assert response.json()["error"]["code"] == "too_many_requests"
    assert int(response.headers["Retry-After"]) >= 1


def count(db: Session, model: type[Any]) -> int:
    return db.scalar(select(func.count()).select_from(model)) or 0


# (route, bucket, limit, body) — the project/channel ids are filled in by each test.
ROUTES: list[tuple[str, str, Callable[[], int], dict[str, Any]]] = [
    ("/channels/{c}/messages", "messages", lambda: get_settings().messages_per_minute,
     {"body": "flood"}),
    ("/channels/{c}/requirement-posts", "messages", lambda: get_settings().messages_per_minute,
     {"fields": FIELDS}),
    ("/projects/{p}/requirements", "messages", lambda: get_settings().messages_per_minute,
     {"fields": FIELDS}),
    ("/projects/{p}/similar", "similar", lambda: get_settings().similar_requests_per_minute,
     {"text": "Sessions shall expire."}),
    ("/projects/{p}/preflight", "preflight", lambda: get_settings().preflight_requests_per_minute,
     {"text": "Sessions shall expire."}),
    ("/projects/{p}/improve-wording", "wording",
     lambda: get_settings().wording_requests_per_minute, {"text": "Sessions shall expire."}),
    ("/projects/{p}/changes/summary", "change-summary", lambda: SUMMARIES_PER_MINUTE,
     {"since_last_visit": True, "narrative": True}),
]  # fmt: skip


def url(route: str, project: Project, channel: Channel) -> str:
    return "/api/v1" + route.replace("{p}", str(project.id)).replace("{c}", str(channel.id))


@pytest.mark.parametrize(("route", "bucket", "limit", "body"), ROUTES, ids=[r[0] for r in ROUTES])
def test_a_full_bucket_answers_429_stores_nothing_and_never_calls_the_model(
    client: TestClient, db_session: Session, stack: Stack, project: Project, channel: Channel,
    member: User, route: str, bucket: str, limit: Callable[[], int], body: dict[str, Any],
) -> None:  # fmt: skip
    fill(stack.limiter, bucket, member, limit())
    messages, requirements = count(db_session, Message), count(db_session, Requirement)

    response = client.post(url(route, project, channel), json=body, headers=headers_for(member))

    assert_limited(response)
    assert count(db_session, Message) == messages
    assert count(db_session, Requirement) == requirements
    assert stack.transport.calls == []


def test_the_limit_is_per_user_a_teammate_still_posts(
    client: TestClient, stack: Stack, project: Project, channel: Channel, member: User,
    make_user: Callable[..., User],
) -> None:  # fmt: skip
    fill(stack.limiter, "messages", member, get_settings().messages_per_minute)
    teammate = make_user(role=DefaultRole.BUSINESS_ANALYST)
    target = url("/channels/{c}/messages", project, channel)

    assert_limited(client.post(target, json={"body": "one more"}, headers=headers_for(member)))
    assert (
        client.post(target, json={"body": "hi"}, headers=headers_for(teammate)).status_code == 201
    )


def test_posting_through_every_door_shares_one_message_allowance(
    client: TestClient, stack: Stack, project: Project, channel: Channel, member: User
) -> None:
    """Chat, channel posts and composer posts draw on one bucket: switching routes is no way out."""
    limit = get_settings().messages_per_minute
    fill(stack.limiter, "messages", member, limit - 1)
    headers = headers_for(member)

    last = client.post(url("/channels/{c}/messages", project, channel), json={"body": "last"},
                       headers=headers)  # fmt: skip
    assert last.status_code == 201
    assert_limited(
        client.post(
            url("/projects/{p}/requirements", project, channel),
            json={"fields": FIELDS},
            headers=headers,
        )  # fmt: skip
    )


def test_buckets_do_not_leak_into_each_other(
    client: TestClient, stack: Stack, project: Project, channel: Channel, member: User
) -> None:
    """Spending the AI allowance never silences chat, and a chat flood never blocks pre-flight."""
    fill(stack.limiter, "wording", member, get_settings().wording_requests_per_minute)
    fill(stack.limiter, "preflight", member, get_settings().preflight_requests_per_minute)

    chat = client.post(url("/channels/{c}/messages", project, channel), json={"body": "still here"},
                       headers=headers_for(member))  # fmt: skip
    assert chat.status_code == 201
    similar = client.post(url("/projects/{p}/similar", project, channel),
                          json={"text": "Sessions shall expire."}, headers=headers_for(member))  # fmt: skip
    assert similar.status_code == 200


def test_a_flood_is_cut_off_at_exactly_the_limit(
    client: TestClient, stack: Stack, project: Project, channel: Channel, member: User
) -> None:
    target = url("/projects/{p}/similar", project, channel)
    headers = headers_for(member)
    allowed = get_settings().similar_requests_per_minute
    statuses = [
        client.post(target, json={"text": "Sessions shall expire."}, headers=headers).status_code
        for _ in range(allowed + 2)
    ]
    assert statuses[:allowed] == [200] * allowed
    assert statuses[allowed:] == [429, 429]
    # The costly AI routes are stricter than the embedding-only one.
    assert get_settings().preflight_requests_per_minute < allowed
