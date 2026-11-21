"""Risk level of a change request, by rule (Madhav — US-34, ADR-17; never by the LLM).

==========  ===============================================================================
``high``    a check failed for a reason in the text (a new conflict, a broken dependency), a
            protected requirement is involved, or more than ``MANY_AFFECTED`` requirements are
``medium``  any other warning, a new finding in the delta, a High-severity finding the change
            leaves open (US-08), or ``SOME_AFFECTED`` or more
``low``     everything else
==========  ===============================================================================

The ``stale`` check is procedural (update the request), not a risk of the change itself, and
checks that could not run are reported as such, not counted as risk. Every rule that fired is
returned as a reason, so the level can always be explained.
"""

from typing import Any, Literal

from app.consequences.checks import Check
from app.consequences.impact import Impact

RiskLevel = Literal["low", "medium", "high"]
SOME_AFFECTED = 3
MANY_AFFECTED = 10


def assess(
    checks: list[Check], impact: Impact, delta: dict[str, list[Any]]
) -> tuple[RiskLevel, list[str]]:
    high: list[str] = []
    medium: list[str] = []
    for check in checks:
        if check.key == "stale":
            continue
        if check.status == "fail":
            high.append(check.message)
        elif check.status == "warning":
            (high if check.key == "protected" else medium).append(check.message)
    count = len(impact.affected)
    if count > MANY_AFFECTED:
        high.append(f"{count} requirements are affected")
    elif count >= SOME_AFFECTED:
        medium.append(f"{count} requirements are affected")
    severe = [e for e in delta.get("still_open", []) if e.get("severity") == "high"]
    if severe:
        medium.append(
            f"{len(severe)} High-severity finding{'s' * (len(severe) != 1)} stay"
            f"{'s' * (len(severe) == 1)} open"
        )
    if delta.get("new"):
        medium.append(
            f"{len(delta['new'])} new finding{'s' * (len(delta['new']) != 1)} with the new text"
        )
    if high:
        return "high", high + medium
    if medium:
        return "medium", medium
    return "low", ["No check raised a concern"]
