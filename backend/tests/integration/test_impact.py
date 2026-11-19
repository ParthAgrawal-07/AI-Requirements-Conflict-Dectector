"""Affected sets and findings delta for the 10 scripted change requests (Abhyudit — US-11, US-34).

Component C of the benchmark (``eval/benchmark_v2/change_requests.json``) against the planted SRS.
The impact part is exact: the affected requirements and owners must be the expected ones. The
delta part answers each comparison as the scripted request says (an oracle transport), so it
checks that the delta reports what the comparisons found — resolved, new and the rest — not how
well a model classifies.
"""

import json
import re
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.classification.llm_client import LLMClient
from app.consequences import tasks as consequence_tasks
from app.consequences.impact import ImpactAnalyzer
from app.core.permissions import DefaultRole
from app.models import ChangeRequest, Project, User
from tests.integration.planted import BENCHMARK, Planted, load, scripted

REQUESTS: list[dict[str, Any]] = scripted()["change_requests"]
_B = re.compile(r'<requirement label="B" id="(REQ-\d+)">')


class OracleTransport:
    """Answers the probe as the scripted request expects (see module doc)."""

    label = "oracle/test"

    def __init__(self, request: dict[str, Any], planted: Planted) -> None:
        self.request, self.planted = request, planted

    def send(self, system: str, user: str) -> str:
        partner = _B.search(user)
        if partner is None:  # the single check, or the narrative: nothing to report
            if "consequence report" in system:
                return "{}"
            return json.dumps(
                {
                    "category": "None",
                    "confidence": 0.9,
                    "rationale": "Clear.",
                    "vague_terms": [],
                    "missing_information": [],
                }
            )
        other = partner.group(1)
        if other in self.request["expected_new_conflicts"]:
            category = "Conflicting"
        elif other in self.request.get("expected_new_duplicates", []):
            category = "Duplicate"
        elif other in self.request["expected_resolved"]:
            category = "None"
        else:
            category = self.planted.category_between(self.request["target_req_id"], other) or "None"
        return json.dumps(
            {
                "category": category,
                "confidence": 0.9,
                "rationale": "As scripted.",
                "dependency_direction": "A_depends_on_B" if category == "Dependent" else None,
                "evidence": [],
            }
        )


@pytest.fixture
def planted(db_session: Session, project: Project, make_user: Callable[..., User]) -> Planted:
    owners: dict[str, User] = {}
    for name in scripted()["owners"]:
        user = make_user(role=DefaultRole.BUSINESS_ANALYST)
        user.full_name = name
        owners[name] = user
    db_session.commit()
    return load(db_session, project, owners)


def test_the_benchmark_has_ten_valid_scripted_requests() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((BENCHMARK / "schema.json").read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(
        {"$defs": schema["$defs"], **schema["$defs"]["change_request"]}
    )
    for request in REQUESTS:
        validator.validate(request)
    assert [r["cr_id"] for r in REQUESTS] == [f"CR-{n}" for n in range(1, 11)]
    assert {r["split"] for r in REQUESTS} == {"dev", "heldout"}


@pytest.mark.parametrize("request_", REQUESTS, ids=lambda r: r["cr_id"])
def test_affected_requirements_and_owners(
    planted: Planted, db_session: Session, request_: dict[str, Any]
) -> None:
    target = planted.by_label[request_["target_req_id"]]

    impact = ImpactAnalyzer(db_session).analyse(target)

    assert {a.label for a in impact.affected} == set(request_["expected_affected_ids"])
    names = {u.id: name for name, u in planted.owners.items()}
    assert {names[o] for o in impact.owners} == set(request_["expected_owners"])


@pytest.mark.parametrize("request_", REQUESTS, ids=lambda r: r["cr_id"])
def test_findings_delta(planted: Planted, db_session: Session, request_: dict[str, Any]) -> None:
    target = planted.by_label[request_["target_req_id"]]
    proposer = next(iter(planted.owners.values()))
    cr = ChangeRequest(
        project_id=planted.project.id,
        requirement_id=target.id,
        number=1,
        proposer_id=proposer.id,
        base_version=1,
        proposed_body=request_["proposed_text"],
        reason=request_["notes"],
    )
    db_session.add(cr)
    db_session.commit()

    report = consequence_tasks.build_report(
        db_session, cr.id, LLMClient(OracleTransport(request_, planted)), None
    )

    assert report is not None
    delta = report.findings_delta
    me = request_["target_req_id"]

    def partners(part: str, category: str | None = None) -> set[str]:
        return {
            label
            for entry in delta[part]
            if category is None or entry["category"] == category
            for label in entry["labels"]
            if label != me
        }

    assert partners("resolved") == set(request_["expected_resolved"])
    assert partners("new", "Conflicting") == set(request_["expected_new_conflicts"])
    assert partners("new", "Duplicate") == set(request_.get("expected_new_duplicates", []))
    # Every open finding on the target is accounted for exactly once.
    on_target = {k for k in planted.findings if me in k}
    accounted = [
        frozenset(entry["labels"])
        for part in ("resolved", "still_open", "must_rerun")
        for entry in delta[part]
        if entry["finding_id"] is not None and me in entry["labels"]
    ]
    assert sorted(map(sorted, accounted)) == sorted(map(sorted, on_target))
    # Two steps away is never silently trusted.
    two_steps = {a["label"] for a in report.affected if a["depth"] == 2}
    assert two_steps <= partners("must_rerun")
    checks = {c["key"]: c["status"] for c in report.checks}
    touches_protected = target.is_protected or any(a["is_protected"] for a in report.affected)
    assert (checks["protected"] == "warning") == touches_protected
    if request_["expected_new_conflicts"]:
        assert checks["new_conflicts"] == "fail" and report.risk_level == "high"
