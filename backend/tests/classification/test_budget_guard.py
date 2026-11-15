"""The Redis budget guard (Keval — NFR-28, NFR-38, US-31): a monthly allowance per project,
counted atomically, never overspent, reset by the calendar, fail-open on a Redis blip."""

import os
import uuid
from datetime import UTC, datetime
from typing import cast

import pytest
import redis

from app.classification.budget import (
    BudgetExceededError,
    RedisBudget,
    UnlimitedBudget,
    get_budget_guard,
)
from app.classification.llm_client import (
    FakeTransport,
    FallbackTransport,
    LLMClient,
    LLMUnavailableError,
)
from app.core.config import get_settings


@pytest.fixture
def client() -> redis.Redis:
    url = get_settings().redis_url
    connection = redis.Redis.from_url(url, socket_connect_timeout=1)
    try:
        connection.ping()
    except redis.RedisError as exc:
        if os.environ.get("REQUIRE_DB") == "1":
            pytest.fail(f"Redis is not reachable: {exc}")
        pytest.skip(f"Redis is not reachable: {exc}")
    return connection


def guard(client: redis.Redis, allowance: int, month: int = 11) -> RedisBudget:
    return RedisBudget(
        client, lambda _project: allowance, now=lambda: datetime(2026, month, 15, tzinfo=UTC)
    )


def test_calls_are_counted_until_the_allowance_and_never_beyond(client: redis.Redis) -> None:
    project = uuid.uuid4()
    budget = guard(client, allowance=2)

    budget.reserve(project)
    budget.reserve(project)
    with pytest.raises(BudgetExceededError):
        budget.reserve(project)

    assert budget.remaining(project) == 0
    assert int(client.get(budget.key(project)) or 0) == 2  # the refused call was given back
    assert 0 < int(client.ttl(budget.key(project))) <= 40 * 24 * 3600


def test_a_new_month_starts_from_zero(client: redis.Redis) -> None:
    project = uuid.uuid4()
    guard(client, allowance=1, month=11).reserve(project)

    december = guard(client, allowance=1, month=12)

    assert december.remaining(project) == 1
    december.reserve(project)


def test_raising_the_cap_lets_a_waiting_project_continue(client: redis.Redis) -> None:
    project = uuid.uuid4()
    allowance = {"calls": 1}
    budget = RedisBudget(client, lambda _p: allowance["calls"])
    budget.reserve(project)
    with pytest.raises(BudgetExceededError):
        budget.reserve(project)

    allowance["calls"] = 5

    assert budget.remaining(project) == 4
    budget.reserve(project)


def test_projects_have_separate_budgets(client: redis.Redis) -> None:
    budget = guard(client, allowance=1)
    first, second = uuid.uuid4(), uuid.uuid4()

    budget.reserve(first)
    budget.reserve(second)

    with pytest.raises(BudgetExceededError):
        budget.reserve(first)


def test_a_redis_outage_lets_the_call_through() -> None:
    class Down:
        def incr(self, key: str) -> int:
            raise redis.ConnectionError("down")

        def get(self, key: str) -> None:
            raise redis.ConnectionError("down")

    budget = RedisBudget(cast(redis.Redis, Down()), lambda _p: 0)

    budget.reserve(uuid.uuid4())  # no exception
    assert budget.remaining(uuid.uuid4()) is None


def test_the_backend_setting_chooses_the_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    get_budget_guard.cache_clear()
    monkeypatch.setenv("LLM_BUDGET_BACKEND", "unlimited")
    get_settings.cache_clear()
    try:
        assert isinstance(get_budget_guard(), UnlimitedBudget)
    finally:
        monkeypatch.delenv("LLM_BUDGET_BACKEND")
        get_settings.cache_clear()
        get_budget_guard.cache_clear()
    assert isinstance(get_budget_guard(), RedisBudget)
    get_budget_guard.cache_clear()


# ── provenance (ADR-31) ─────────────────────────────────────────────────────────────────────
def test_the_client_names_the_model_that_answered() -> None:
    class Down:
        label = "gemini/gemini-2.5-flash"

        def send(self, system: str, user: str) -> str:
            raise LLMUnavailableError("rate limited")

    backup = FakeTransport(["ok"], label="groq/llama-3.3-70b-versatile")
    client = LLMClient(FallbackTransport(Down(), backup))

    assert client.model == "gemini/gemini-2.5-flash"
    client.complete_text("s", "u")
    assert client.model == "groq/llama-3.3-70b-versatile"
