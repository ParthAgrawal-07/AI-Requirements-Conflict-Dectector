"""LLM budget guard (Keval — NFR-28, NFR-38; Sprint 0 design, enforced from Sprint 3 with US-31).

Design
------
* Every LLM call is counted against its project's ``projects.llm_budget_monthly_calls`` (default
  2,000) for the current calendar month (UTC). Calls with no project (the brief drafter before a
  project is active) count against a small platform-wide allowance.
* The counter is a Redis key ``llm:calls:<project_id>:<YYYY-MM>`` incremented *before* the call
  (``INCR`` then compare), so concurrent workers cannot overshoot by more than one call each.
  Beat resets nothing: the month is part of the key, and keys expire after 40 days.
* Over budget, :meth:`BudgetGuard.reserve` raises :class:`BudgetExceededError`. The analysis
  orchestrator (Sprint 3) then parks the run as ``waiting_budget`` and re-enqueues it at the next
  month or when a manager raises the budget; pre-flight checks show "N analyses left this month"
  and refuse when it is 0. A run never half-finishes silently.
* At 80% the project's managers are notified once per month (US-38, Sprint 5).

From Sprint 3 :func:`get_budget_guard` returns :class:`RedisBudget` (``LLM_BUDGET_BACKEND=redis``,
the default). ``unlimited`` keeps the Sprint 0–2 behaviour for local experiments. If Redis itself
is unreachable the guard lets the call through and logs it: Celery needs the same Redis, so an
outage stops analysis anyway, and a counter blip should not fail a run that is already paid for.
"""

import logging
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from functools import lru_cache
from typing import Protocol

import redis

logger = logging.getLogger(__name__)

KEY_PREFIX = "llm:calls:"
KEY_TTL_SECONDS = 40 * 24 * 60 * 60  # a month's key outlives the month, then disappears
ALLOWANCE_CACHE_SECONDS = 60.0


class BudgetExceededError(Exception):
    """The project's LLM budget for this month is used up."""

    def __init__(self, project_id: uuid.UUID | None) -> None:
        super().__init__(f"LLM budget exhausted for project {project_id}")
        self.project_id = project_id


class BudgetGuard(Protocol):
    def reserve(self, project_id: uuid.UUID | None) -> None:
        """Count one call, or raise :class:`BudgetExceededError` if none is left."""
        ...

    def remaining(self, project_id: uuid.UUID | None) -> int | None:
        """Calls left this month, or ``None`` when unlimited."""
        ...


class UnlimitedBudget:
    """No limit (Sprints 0–2, tests)."""

    def reserve(self, project_id: uuid.UUID | None) -> None:
        return None

    def remaining(self, project_id: uuid.UUID | None) -> int | None:
        return None


class CountingBudget:
    """A fixed allowance per project held in memory — for tests of callers that must stop."""

    def __init__(self, allowance: int) -> None:
        self._allowance = allowance
        self._used: dict[uuid.UUID | None, int] = {}

    def reserve(self, project_id: uuid.UUID | None) -> None:
        used = self._used.get(project_id, 0)
        if used >= self._allowance:
            raise BudgetExceededError(project_id)
        self._used[project_id] = used + 1

    def remaining(self, project_id: uuid.UUID | None) -> int | None:
        return self._allowance - self._used.get(project_id, 0)


class RedisBudget:
    """The production guard: one Redis counter per project and calendar month (UTC).

    ``INCR`` first, then compare — atomic, so concurrent workers can never spend more than the
    allowance; a call over the line is given back (``DECR``) before raising.
    """

    def __init__(
        self,
        client: redis.Redis,
        allowance: Callable[[uuid.UUID | None], int],
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._client = client
        self._allowance = allowance
        self._now = now

    def key(self, project_id: uuid.UUID | None) -> str:
        return f"{KEY_PREFIX}{project_id or 'platform'}:{self._now():%Y-%m}"

    def reserve(self, project_id: uuid.UUID | None) -> None:
        key = self.key(project_id)
        try:
            used = int(self._client.incr(key))
            if used == 1:
                self._client.expire(key, KEY_TTL_SECONDS)
            if used > self._allowance(project_id):
                self._client.decr(key)
                raise BudgetExceededError(project_id)
        except redis.RedisError:
            logger.warning("LLM budget counter unavailable; call for %s not counted", project_id)

    def remaining(self, project_id: uuid.UUID | None) -> int | None:
        try:
            used = int(self._client.get(self.key(project_id)) or 0)
        except redis.RedisError:
            return None
        return max(0, self._allowance(project_id) - used)


class _ProjectAllowance:
    """``projects.llm_budget_monthly_calls``, re-read at most once a minute per project, so a
    manager raising the cap takes effect within a minute without a query per LLM call."""

    def __init__(self) -> None:
        self._cache: dict[uuid.UUID, tuple[float, int]] = {}

    def __call__(self, project_id: uuid.UUID | None) -> int:
        from app.core.config import get_settings

        if project_id is None:
            return get_settings().llm_platform_monthly_calls
        cached = self._cache.get(project_id)
        if cached is not None and time.monotonic() - cached[0] < ALLOWANCE_CACHE_SECONDS:
            return cached[1]
        from app.core.database import session_scope
        from app.models import Project

        with session_scope() as db:
            project = db.get(Project, project_id)
            allowance = project.llm_budget_monthly_calls if project is not None else 0
        self._cache[project_id] = (time.monotonic(), allowance)
        return allowance


@lru_cache
def get_budget_guard() -> BudgetGuard:
    from app.core.config import get_settings

    settings = get_settings()
    if settings.llm_budget_backend == "unlimited":
        return UnlimitedBudget()
    client = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)
    return RedisBudget(client, _ProjectAllowance())
