"""Sprint 6 recall tuning of the rule checks (Heet — US-58, NFR-37): the unbounded rule and
frequency words, from the CP2 misses on the dev split. The planted pairs below are dev pairs of
``eval/benchmark_v2/labels.csv``; held-out pairs are only ever measured, never tuned on."""

from collections.abc import Callable

import pytest
from sqlalchemy.orm import Session

from app.models import Project, Requirement, RequirementOrigin
from app.search.rule_checker import RuleChecker, unbounded, with_frequencies


@pytest.mark.parametrize(
    ("text", "metric"),
    [
        ("Sessions shall remain active until the user explicitly logs out.", "timeout"),
        ("Tokens never expire.", "timeout"),
        ("Audit records shall be kept indefinitely.", "retention"),
        ("Invoices shall never be deleted.", "retention"),
        (
            "A user shall be able to stay signed in on any number of devices at the same time.",
            "concurrency",
        ),  # fmt: skip
        ("Users shall be able to sign in on any number of devices.", None),
        ("The session shall expire after 30 minutes.", None),
    ],
)
def test_unbounded_reads_what_a_requirement_leaves_open(text: str, metric: str | None) -> None:
    found = unbounded(text)
    assert (found[0] if found else None) == metric


def test_frequency_words_become_periods() -> None:
    assert with_frequencies("Rates are refreshed hourly.") == "Rates are refreshed every 1 hour."
    assert with_frequencies("Reports run nightly and every week.") == (
        "Reports run every 1 day and every 1 week."
    )


def _post(db: Session, project: Project, label: str, text: str) -> Requirement:
    requirement = Requirement(project_id=project.id, origin=RequirementOrigin.POST,
                              source_req_id=label, body=text)  # fmt: skip
    db.add(requirement)
    db.commit()
    return requirement


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        # planted dev conflicts the CP2 rules missed
        ("Admin sessions shall expire after 5 minutes of inactivity.",
         "Sessions shall remain active until the user explicitly logs out.", {"unbounded"}),
        ("The system shall allow at most 3 concurrent sessions per user.",
         "A user shall be able to stay signed in on any number of devices at the same time.",
         {"unbounded"}),
        # planted dev pairs labelled None: they must stay quiet
        ("The system shall allow at most 3 concurrent sessions per user.",
         "Admin sessions shall expire after 5 minutes of inactivity.", set()),
        ("A user shall be able to stay signed in on any number of devices at the same time.",
         "Sessions shall remain active until the user explicitly logs out.", set()),
    ],
)  # fmt: skip
def test_planted_dev_pairs(
    db_session: Session,
    make_project: Callable[..., Project],
    a: str,
    b: str,
    expected: set[str],
) -> None:
    project = make_project()
    first, second = _post(db_session, project, "REQ-A", a), _post(db_session, project, "REQ-B", b)
    found = RuleChecker(db_session).check_all([first, second])
    assert {f.rule_id for f in found} == expected
    if expected:
        assert "Both cannot hold." in found[0].rationale
