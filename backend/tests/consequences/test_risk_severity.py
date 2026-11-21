"""Severity feeds the risk level of a consequence report (Keval — US-08 into US-34)."""

from app.consequences.impact import Impact
from app.consequences.risk import assess
from app.models import Requirement


def impact() -> Impact:
    return Impact(requirement=Requirement(body="x"), affected=[], owners=[], stakeholder_groups=[])


def test_a_high_severity_finding_left_open_raises_the_risk_to_medium() -> None:
    delta = {"resolved": [], "new": [], "must_rerun": [],
             "still_open": [{"category": "Conflicting", "severity": "high"},
                            {"category": "Ambiguous", "severity": "low"}]}  # fmt: skip
    level, reasons = assess([], impact(), delta)
    assert level == "medium"
    assert reasons == ["1 High-severity finding stays open"]


def test_resolving_a_high_severity_finding_is_not_a_risk() -> None:
    delta = {"resolved": [{"category": "Conflicting", "severity": "high"}], "new": [],
             "still_open": [], "must_rerun": []}  # fmt: skip
    assert assess([], impact(), delta)[0] == "low"
