"""Severity overrides, the findings list by severity, the AI feedback report and the change
summary paragraph (Keval — US-08, US-15, US-55)."""

import json
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.classification.llm_client import FakeTransport, LLMClient, get_llm_client
from app.core.permissions import DefaultRole
from app.graph import deltas
from app.models import (
    AuditLog,
    CandidatePair,
    Finding,
    FindingCategory,
    FindingReview,
    FindingStatus,
    Project,
    Requirement,
    Severity,
    Suggestion,
    SuggestionFeedback,
    User,
)
from app.realtime import bus
from tests.analysis_helpers import make_post
from tests.api.conftest import headers_for


@pytest.fixture(autouse=True)
def quiet_bus(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(bus, "get_bus", lambda: bus.InProcessEventBus())
    yield


def url(*parts: object) -> str:
    return "/api/v1/" + "/".join(str(p) for p in parts)


def single(db: Session, requirement: Requirement, **fields: object) -> Finding:
    finding = Finding(project_id=requirement.project_id, document_id=requirement.document_id,
                      requirement_id=requirement.id, category=fields.pop("category", FindingCategory.AMBIGUOUS),
                      confidence=fields.pop("confidence", 0.8), rationale="r", original_ai_output={},
                      **fields)  # fmt: skip
    db.add(finding)
    db.commit()
    return finding


# ── US-08 severity ──────────────────────────────────────────────────────────────────────────
def test_a_reviewer_overrides_severity_with_a_reason_and_the_proposal_is_kept(
    client: TestClient, db_session: Session, user: User,
    make_requirement: Callable[..., Requirement],
) -> None:  # fmt: skip
    finding = single(db_session, make_requirement("It shall be fast."), severity=Severity.MEDIUM,
                     severity_source="system", severity_proposed="medium")  # fmt: skip

    response = client.patch(url("findings", finding.id, "severity"),
                            json={"severity": "high", "reason": "Blocks the clinical pilot"},
                            headers=headers_for(user))  # fmt: skip

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["severity"], body["severity_source"], body["severity_proposed"]) == (
        "high", "reviewer", "medium"
    )  # fmt: skip
    assert body["severity_reason"] == "Blocks the clinical pilot"
    assert body["confidence"] == 0.8  # how sure is untouched by how bad
    audit = db_session.scalars(select(AuditLog).where(AuditLog.action == "severity_changed")).one()
    assert audit.details == {"from": "medium", "to": "high", "proposed": "medium"}
    blank = client.patch(url("findings", finding.id, "severity"),
                         json={"severity": "low", "reason": "   "}, headers=headers_for(user))  # fmt: skip
    assert (blank.status_code, blank.json()["error"]["code"]) == (400, "reason_required")


def test_only_a_compliance_reviewer_changes_the_severity_of_a_protected_finding(
    client: TestClient, db_session: Session, user: User, make_user: Callable[..., User],
    make_requirement: Callable[..., Requirement],
) -> None:  # fmt: skip
    finding = single(db_session, make_requirement("Keep records 7 years.", is_protected=True))
    payload = {"severity": "high", "reason": "Regulatory"}
    analyst = client.patch(url("findings", finding.id, "severity"), json=payload,
                           headers=headers_for(user))  # fmt: skip
    assert analyst.status_code == 403
    reviewer = make_user(role=DefaultRole.COMPLIANCE_REVIEWER)
    assert client.patch(url("findings", finding.id, "severity"), json=payload,
                        headers=headers_for(reviewer)).status_code == 200  # fmt: skip


def test_findings_sort_by_severity_and_hide_dismissed_ones_unless_asked(
    client: TestClient, db_session: Session, project: Project, user: User,
    make_requirement: Callable[..., Requirement],
) -> None:  # fmt: skip
    low = single(db_session, make_requirement("a"), severity=Severity.LOW, confidence=0.99)
    high = single(db_session, make_requirement("b"), severity=Severity.HIGH, confidence=0.6)
    gone = single(db_session, make_requirement("c"), severity=Severity.HIGH,
                  status=FindingStatus.DISMISSED)  # fmt: skip
    headers = headers_for(user)

    by_severity = client.get(url("projects", project.id, "findings"), params={"sort": "severity"},
                             headers=headers).json()  # fmt: skip
    assert [f["id"] for f in by_severity["items"]] == [str(high.id), str(low.id)]
    assert by_severity["total"] == 2
    every = client.get(url("projects", project.id, "findings"),
                       params={"include_dismissed": "true"}, headers=headers).json()  # fmt: skip
    assert str(gone.id) in {f["id"] for f in every["items"]}
    restorable = client.get(url("projects", project.id, "findings"),
                            params={"status": "dismissed"}, headers=headers).json()  # fmt: skip
    assert [f["id"] for f in restorable["items"]] == [str(gone.id)]


# ── US-15 AI feedback ───────────────────────────────────────────────────────────────────────
def test_the_feedback_report_groups_dismissals_and_surfaces_a_pattern_at_the_threshold(
    client: TestClient, db_session: Session, project: Project, user: User,
    make_requirement: Callable[..., Requirement], make_user: Callable[..., User],
) -> None:  # fmt: skip
    a = make_requirement("a")
    for index in range(3):
        b = make_requirement(f"b{index}")
        first, second = CandidatePair.ordered(a.id, b.id)
        pair = CandidatePair(requirement_a_id=first, requirement_b_id=second,
                             similarity_score=0.5 + index / 10)  # fmt: skip
        db_session.add(pair)
        db_session.flush()
        rule = Finding(project_id=project.id, candidate_pair_id=pair.id, category=FindingCategory.CONFLICTING,
                       confidence=0.9, rationale="r", original_ai_output={}, source="rule",
                       rule_id="R-NUM-01", status=FindingStatus.DISMISSED)  # fmt: skip
        db_session.add(rule)
        db_session.flush()
        db_session.add(FindingReview(finding_id=rule.id, actor_id=user.id, action="dismiss",
                                     from_status=FindingStatus.FLAGGED, to_status=FindingStatus.DISMISSED,
                                     from_category=FindingCategory.CONFLICTING,
                                     to_category=FindingCategory.CONFLICTING,
                                     reason="Different units, same limit"))  # fmt: skip
    confirmed = single(db_session, a, status=FindingStatus.CONFIRMED)
    suggestion = Suggestion(finding_id=confirmed.id, project_id=project.id, category="Ambiguous",
                            status="ready", options=[])  # fmt: skip
    db_session.add(suggestion)
    db_session.flush()
    db_session.add(SuggestionFeedback(suggestion_id=suggestion.id, user_id=user.id,
                                      action="rejected_meaning", option_index=0))  # fmt: skip
    db_session.commit()
    manager = make_user(role=DefaultRole.PROJECT_MANAGER)

    before = client.get(
        url("projects", project.id, "ai-feedback"), headers=headers_for(user)
    ).json()
    assert (
        before["threshold"] == 5 and before["surfaced"] == [] and before["self_training"] is False
    )
    conflicting = next(c for c in before["categories"] if c["category"] == "Conflicting")
    (pattern,) = conflicting["patterns"]
    assert (pattern["pattern"], pattern["dismissed"], pattern["false_positive_rate"]) == (
        "R-NUM-01", 3, 1.0
    )  # fmt: skip
    assert pattern["reasons"] == [{"reason": "Different units, same limit", "count": 3}]
    assert before["suggestion_totals"]["rejected_meaning"] == 1

    denied = client.put(url("projects", project.id, "ai-feedback", "threshold"),
                        json={"threshold": 3}, headers=headers_for(user))  # fmt: skip
    assert denied.status_code == 403
    after = client.put(url("projects", project.id, "ai-feedback", "threshold"),
                       json={"threshold": 3}, headers=headers_for(manager)).json()  # fmt: skip
    assert [(s["category"], s["pattern"]["pattern"]) for s in after["surfaced"]] == [
        ("Conflicting", "R-NUM-01")
    ]


# ── US-55 AI paragraph ──────────────────────────────────────────────────────────────────────
def test_the_summary_paragraph_is_optional_labelled_and_checked(
    client: TestClient, db_session: Session, project: Project, user: User
) -> None:
    from app.main import app

    post = make_post(db_session, project, user, "x", label="REQ-1")
    deltas.publish(db_session, project.id,
                   deltas.Change(new_requirements={post.id}, sentences=["Test added REQ-1 (Proposed)."]),
                   actor=user)  # fmt: skip
    headers = headers_for(user)
    path = url("projects", project.id, "changes", "summary")

    plain = client.post(path, json={"narrative": False}, headers=headers).json()
    assert (plain["narrative"], plain["narrative_status"]) == (None, "not_requested")
    app.dependency_overrides[get_llm_client] = lambda: None
    try:
        none = client.post(path, json={}, headers=headers).json()
        assert none["narrative_status"] == "no_model" and none["counts"]["requirements_added"] == 1
        paragraph = json.dumps(
            {"paragraph": "One requirement, REQ-1, was added.", "cited_keys": ["REQ-1"]}
        )
        llm = LLMClient(FakeTransport([paragraph], label="groq/llama"))
        app.dependency_overrides[get_llm_client] = lambda: llm
        body = client.post(path, json={}, headers=headers).json()
    finally:
        app.dependency_overrides.pop(get_llm_client, None)
    assert body["narrative"] == {"text": "One requirement, REQ-1, was added.", "ai": True,
                                 "provider": "groq", "model": "llama"}  # fmt: skip
    assert body["markdown"] == plain["markdown"]  # the numbers never come from the model
