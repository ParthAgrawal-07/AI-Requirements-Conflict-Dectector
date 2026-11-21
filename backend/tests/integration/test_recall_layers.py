"""Rule checks catch the below-threshold benchmark subset (Abhyudit — US-58, NFR-37; CP2).

The pairs of ``eval/benchmark_v2/below_threshold.csv`` are stored as requirements of one project
and the rule checker runs the way the worker runs it (``RuleChecker.check_all``, through the
database): every conflict labelled with an expected rule is found by that rule, and the
look-alike non-conflicts raise nothing. Conflicts labelled ``none`` (only the AI or a person can
catch them) are recorded as such, not asserted away.
"""

import csv
from collections.abc import Callable
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.models import CandidatePair, Project, Requirement, RequirementOrigin
from app.search.rule_checker import RuleChecker

SET = Path(__file__).resolve().parents[3] / "eval" / "benchmark_v2" / "below_threshold.csv"


@pytest.fixture
def rows() -> list[dict[str, str]]:
    if not SET.is_file():
        pytest.skip(f"{SET} is not reachable (eval/ not mounted)")
    with SET.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _post(db: Session, project: Project, label: str, text: str) -> Requirement:
    requirement = Requirement(project_id=project.id, origin=RequirementOrigin.POST,
                              source_req_id=label, body=text)  # fmt: skip
    db.add(requirement)
    db.commit()
    return requirement


def test_every_rule_labelled_conflict_is_caught_and_look_alikes_are_quiet(
    db_session: Session, make_project: Callable[..., Project], rows: list[dict[str, str]]
) -> None:
    hits: dict[str, set[str]] = {}
    for row in rows:
        # One project per pair, so pairs from different rows are never compared with each other.
        project = make_project()
        a = _post(db_session, project, f"{row['id']}a", row["a_text"])
        b = _post(db_session, project, f"{row['id']}b", row["b_text"])
        found = RuleChecker(db_session).check_all([a, b])
        pairs = {db_session.get(CandidatePair, f.candidate_pair_id) for f in found}
        assert all(p is not None and {p.requirement_a_id, p.requirement_b_id} == {a.id, b.id}
                   for p in pairs)  # fmt: skip
        hits[row["id"]] = {f.rule_id or "" for f in found}

    for row in rows:
        expected = row["expected_rule"]
        if row["category"] == "Conflicting" and expected != "none":
            assert expected in hits[row["id"]], (row["id"], hits[row["id"]])
        elif row["category"] == "None":
            assert hits[row["id"]] == set(), (row["id"], hits[row["id"]])
    caught = sum(1 for r in rows if r["expected_rule"] != "none" and hits[r["id"]])
    assert caught == 12
