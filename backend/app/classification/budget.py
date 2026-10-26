"""LLM budget guard (Keval — NFR-38; Sprint 0 design, enforced from Sprint 3 with US-31).

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

Until Sprint 3 :func:`get_budget_guard` returns :class:`UnlimitedBudget`, so the interface is in
place for the classifier and drafter without blocking anyone.
"""

import uuid
from typing import Protocol


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


def get_budget_guard() -> BudgetGuard:
    return UnlimitedBudget()
