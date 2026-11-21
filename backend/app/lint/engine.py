"""The lint engine (Keval — US-51, FR-82, NFR-34, DR-07).

Runs the catalogue (``catalogue.json``) over one piece of text and says what it found, where, and
how to fix it — no LLM, no database, a few milliseconds. The composer runs the **same file** in
the browser on every pause in typing (NFR-34: within 300 ms); this module is the server half,
behind ``POST /projects/{p}/lint`` (a fallback for clients that cannot run it) and the pre-flight
check. Lint never blocks anything: a submission with errors is still a submission.

The quality indicator summarises the issues in one word for the composer's badge:

==========  =================================================================================
``good``    score 80 or more
``fair``    50 to 79
``poor``    below 50
==========  =================================================================================

where the score starts at 100 and loses 25 per error, 10 per warning and 3 per info, never
below 0. The weights are deliberately simple so the browser computes the same number.
"""

import json
import re
from dataclasses import asdict, dataclass
from functools import cache
from pathlib import Path
from typing import Any, Literal

CATALOGUE_PATH = Path(__file__).parent / "catalogue.json"
WEIGHTS = {"error": 25, "warning": 10, "info": 3}
MAX_ISSUES = 50  # a pasted wall of text must not return thousands of underlines

Severity = Literal["info", "warning", "error"]
Quality = Literal["good", "fair", "poor"]


@dataclass(frozen=True)
class Rule:
    id: str
    category: str
    pattern: re.Pattern[str]
    message: str
    hint: str
    severity: Severity


@dataclass(frozen=True)
class LintIssue:
    rule_id: str
    category: str
    severity: Severity
    start: int  # character offsets into the text, for the underline
    end: int
    match: str
    message: str
    hint: str

    def as_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LintResult:
    issues: list[LintIssue]
    score: int
    quality: Quality


@cache
def catalogue() -> dict[str, Any]:
    """The catalogue as stored (what ``GET /lint/catalogue`` serves to the browser)."""
    data: dict[str, Any] = json.loads(CATALOGUE_PATH.read_text(encoding="utf-8"))
    return data


@cache
def rules() -> tuple[Rule, ...]:
    return tuple(
        Rule(
            id=entry["id"],
            category=entry["category"],
            pattern=re.compile(entry["pattern"], re.IGNORECASE),
            message=entry["message"],
            hint=entry["hint"],
            severity=entry["severity"],
        )
        for entry in catalogue()["entries"]
    )


def score_of(issues: list[LintIssue]) -> tuple[int, Quality]:
    score = max(0, 100 - sum(WEIGHTS[issue.severity] for issue in issues))
    quality: Quality = "good" if score >= 80 else "fair" if score >= 50 else "poor"
    return score, quality


def lint(text: str) -> LintResult:
    """Every catalogue match in ``text``, in reading order (overlaps are kept: they are
    different problems with the same words)."""
    issues: list[LintIssue] = []
    for rule in rules():
        for found in rule.pattern.finditer(text):
            if found.end() == found.start():
                continue
            issues.append(
                LintIssue(
                    rule_id=rule.id,
                    category=rule.category,
                    severity=rule.severity,
                    start=found.start(),
                    end=found.end(),
                    match=found.group(0),
                    message=rule.message,
                    hint=rule.hint,
                )
            )
    issues.sort(key=lambda issue: (issue.start, issue.end, issue.rule_id))
    issues = issues[:MAX_ISSUES]
    score, quality = score_of(issues)
    return LintResult(issues=issues, score=score, quality=quality)
