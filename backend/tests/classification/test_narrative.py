"""The consequence narrative never contradicts the checks (Keval — US-34, FR-99)."""

import json
import uuid
from typing import Any

import pytest

from app.classification.budget import CountingBudget
from app.classification.llm_client import FakeTransport, LLMClient
from app.classification.narrative import NarrativeOutput, contradictions, known_ids, write
from app.models import ConsequenceReport


def report(*, risk: str = "high", failing: bool = True) -> ConsequenceReport:
    checks: list[dict[str, Any]] = [
        {"key": "stale", "title": "Up to date", "status": "pass", "message": "Written against REQ-014 v1, its current version", "details": {}},
        {"key": "new_conflicts", "title": "New conflicts", "status": "fail" if failing else "pass",
         "message": "The new text conflicts with REQ-040" if failing else "None found among 2 related requirements", "details": {}},
        {"key": "wording", "title": "Wording", "status": "pass", "message": "The new text is specific and complete", "details": {}},
    ]  # fmt: skip
    return ConsequenceReport(
        id=uuid.uuid4(),
        change_request_id=uuid.uuid4(),
        proposal_revision=1,
        base_version=1,
        baseline_revision=0,
        risk_level=risk,
        risk_reasons=["The new text conflicts with REQ-040"]
        if failing
        else ["No check raised a concern"],
        checks=checks,
        affected=[
            {
                "label": "REQ-031",
                "relation": "conflict",
                "depth": 1,
                "reason": "REQ-031 conflicts with REQ-014 today",
                "status": "potential",
            },
        ],  # fmt: skip
        findings_delta={
            "resolved": [
                {
                    "category": "Conflicting",
                    "labels": ["REQ-014", "REQ-031"],
                    "reason": "No longer holds",
                }
            ],
            "new": [
                {"category": "Conflicting", "labels": ["REQ-014", "REQ-040"], "reason": "Found"}
            ]
            if failing
            else [],
            "still_open": [],
            "must_rerun": [],
        },  # fmt: skip
        llm_calls=0,
    )


def out(
    summary: str, cited: list[str] | None = None, points: list[str] | None = None
) -> NarrativeOutput:
    return NarrativeOutput(summary=summary, points=points or [], cited_ids=cited or [])


FAITHFUL = "RCR-1 is high risk: the new text conflicts with REQ-040, though it resolves the conflict with REQ-031."


def problems(narrative: NarrativeOutput, r: ConsequenceReport | None = None) -> list[str]:
    r = r or report()
    return contradictions(narrative, r, known=known_ids(r, "RCR-1", "REQ-014"))


def test_a_faithful_summary_passes() -> None:
    assert problems(out(FAITHFUL, ["RCR-1", "REQ-040", "REQ-031"])) == []


@pytest.mark.parametrize(
    ("summary", "cited", "expected"),
    [
        (
            FAITHFUL.replace("REQ-031", "REQ-099"),
            [],
            "names IDs that are not in the report: REQ-099",
        ),
        (FAITHFUL, ["REQ-777"], "names IDs that are not in the report: REQ-777"),
        (
            FAITHFUL.replace("high risk", "low risk"),
            [],
            "says the risk is low; the report says high",
        ),
        (
            "RCR-1 has a risk level of medium and changes REQ-014 in a few places only.",
            [],
            "says the risk is medium",
        ),
        (
            "RCR-1 changes REQ-014; the high-risk part is the wording of REQ-031.",
            [],
            "does not mention the failed check 'New conflicts'",
        ),
        (FAITHFUL + " It has been verified.", [], "uses words the report cannot support: verified"),
        (
            FAITHFUL + " Otherwise there are no conflicts.",
            [],
            "reassures although checks did not all pass: no conflicts",
        ),
    ],
)
def test_contradictions_are_caught(summary: str, cited: list[str], expected: str) -> None:
    found = problems(out(summary, cited))
    assert any(p.startswith(expected) for p in found), found


def test_no_conflicts_may_be_said_only_when_everything_passed() -> None:
    clean = report(risk="low", failing=False)
    said = out("The checks found no conflicts for RCR-1; analysis can miss conflicts.")
    assert problems(said, clean) == []


def test_points_count_too() -> None:
    narrative = out(FAITHFUL, points=["Nothing to worry about."])
    assert any("nothing to worry" in p for p in problems(narrative))


def _reply(summary: str) -> str:
    return json.dumps({"summary": summary, "points": [], "cited_ids": []})


def test_a_contradicting_reply_is_re_asked_once_then_kept() -> None:
    transport = FakeTransport([_reply(FAITHFUL.replace("high", "low")), _reply(FAITHFUL)])
    narrative, calls = write(
        report(),
        change_request_key="RCR-1",
        requirement_label="REQ-014",
        llm=LLMClient(transport),
        project_id=None,
    )
    assert narrative is not None and narrative["summary"] == FAITHFUL
    assert narrative["label"] == "AI" and narrative["prompt_version"] == "narrative-v1"
    assert narrative["cited_ids"] == ["RCR-1", "REQ-031", "REQ-040"]
    assert calls == 2
    assert "was rejected because it says the risk is low" in transport.calls[1][1]


def test_two_contradicting_replies_mean_no_narrative() -> None:
    bad = _reply(FAITHFUL + " Verified.")
    narrative, calls = write(
        report(),
        change_request_key="RCR-1",
        requirement_label="REQ-014",
        llm=LLMClient(FakeTransport([bad, bad])),
        project_id=None,
    )
    assert (narrative, calls) == (None, 2)


def test_out_of_budget_means_no_narrative() -> None:
    llm = LLMClient(FakeTransport([_reply(FAITHFUL)]), CountingBudget(0))
    assert write(
        report(),
        change_request_key="RCR-1",
        requirement_label="REQ-014",
        llm=llm,
        project_id=uuid.uuid4(),
    ) == (None, 0)


def test_the_model_sees_the_structured_report_only() -> None:
    transport = FakeTransport([_reply(FAITHFUL)])
    write(
        report(),
        change_request_key="RCR-1",
        requirement_label="REQ-014",
        llm=LLMClient(transport),
        project_id=None,
    )
    system, user = transport.calls[0]
    assert "<report>" in user and "&quot;risk_level&quot;: &quot;high&quot;" in user
    assert "RCR-1 on REQ-014" in user
    assert '"summary"' in system  # the output schema is in the system prompt
