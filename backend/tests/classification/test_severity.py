"""Severity rules (Keval — US-08, FR-42): proposed from facts, never by the LLM."""

import pytest

from app.classification.severity import apply_proposal, propose
from app.models import Finding, FindingCategory, Requirement, RequirementState, Severity


def req(body: str = "x", **fields: object) -> Requirement:
    return Requirement(body=body, **fields)


@pytest.mark.parametrize(
    ("category", "expected"),
    [
        (FindingCategory.CONFLICTING, Severity.MEDIUM),
        (FindingCategory.AMBIGUOUS, Severity.MEDIUM),
        (FindingCategory.INCOMPLETE, Severity.MEDIUM),
        (FindingCategory.DUPLICATE, Severity.LOW),
        (FindingCategory.DEPENDENT, Severity.LOW),
    ],
)
def test_each_category_has_a_base_severity(category: FindingCategory, expected: Severity) -> None:
    assert propose(category, 0.8, [req(), req()]).severity is expected


def test_a_confident_conflict_on_a_protected_requirement_is_high() -> None:
    proposal = propose(FindingCategory.CONFLICTING, 0.91, [req(is_protected=True), req()])
    assert proposal.severity is Severity.HIGH
    assert "protected" in proposal.reason


def test_a_less_confident_conflict_on_the_baseline_goes_up_one_level_only() -> None:
    proposal = propose(
        FindingCategory.CONFLICTING, 0.7, [req(state=RequirementState.APPROVED), req()]
    )
    assert proposal.severity is Severity.HIGH  # medium + 1
    duplicate = propose(FindingCategory.DUPLICATE, 0.95, [req(priority="must"), req()])
    assert duplicate.severity is Severity.MEDIUM  # never straight to High


def test_an_uncertain_finding_goes_down_a_level_but_never_below_low() -> None:
    assert propose(FindingCategory.AMBIGUOUS, 0.4, [req()]).severity is Severity.LOW
    lowest = propose(FindingCategory.DEPENDENT, 0.4, [req(), req()])
    assert lowest.severity is Severity.LOW and "confidence is 0.40" not in lowest.reason


def test_the_reason_names_facts_not_requirement_text() -> None:
    secret = req(body="The vault code is 4711.", priority="must")
    proposal = propose(FindingCategory.AMBIGUOUS, 0.8, [secret])
    assert "4711" not in proposal.reason and "Must" in proposal.reason


def test_apply_proposal_never_overwrites_a_set_severity() -> None:
    rule = Finding(category=FindingCategory.CONFLICTING, confidence=0.9, severity=Severity.LOW)
    apply_proposal(rule, [req(is_protected=True)])
    assert rule.severity is Severity.LOW

    ai = Finding(category=FindingCategory.CONFLICTING, confidence=0.9)
    apply_proposal(ai, [req(is_protected=True), req()])
    assert (ai.severity, ai.severity_proposed, ai.severity_source) == (
        Severity.HIGH,
        "high",
        "system",
    )
