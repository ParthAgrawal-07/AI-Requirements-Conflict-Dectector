"""Decision rules and decision owners (Parth — US-57, FR-65, FR-100, DR-23)."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import DefaultRole
from app.models import (
    AuditLog,
    CandidatePair,
    ChangeRequest,
    Finding,
    FindingCategory,
    Project,
    Requirement,
    RequirementState,
    User,
    Workspace,
)
from app.models.decision_rule import DecisionRule
from app.realtime import bus
from app.services import decision_rules
from app.services.agreement import AgreementGuard
from app.services.decision_rules import DecisionRuleEngine, Facts
from app.services.membership import get_default_role
from tests.api.conftest import headers_for


@pytest.fixture(autouse=True)
def quiet(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bus, "publish", lambda _event: None)


@pytest.fixture
def people(make_user: Callable[..., User]) -> dict[str, User]:
    return {
        "pm": make_user(role=DefaultRole.PROJECT_MANAGER),
        "ba": make_user(role=DefaultRole.BUSINESS_ANALYST),
        "riya": make_user(role=DefaultRole.DEVELOPER),
        "meera": make_user(role=DefaultRole.COMPLIANCE_REVIEWER),
        "viewer": make_user(role=DefaultRole.VIEWER),
    }


@pytest.fixture
def seeded(db_session: Session, project: Project, people: dict[str, User]) -> list[DecisionRule]:
    rows = DecisionRuleEngine(db_session).seed(project, actor_id=people["pm"].id)
    db_session.commit()
    return rows


def url(*parts: object) -> str:
    return "/api/v1/" + "/".join(str(p) for p in parts)


# ── the engine ──────────────────────────────────────────────────────────────────────────────
def test_a_new_project_gets_the_default_and_four_examples(
    client: TestClient, db_session: Session, workspace: Workspace, people: dict[str, User]
) -> None:
    response = client.post(url("workspaces", workspace.id, "projects"), json={"name": "Pay"},
                           headers=headers_for(people["pm"]))  # fmt: skip
    assert response.status_code == 201, response.text
    rules = client.get(url("projects", response.json()["id"], "decision-rules"),
                       headers=headers_for(people["viewer"])).json()  # fmt: skip
    assert [r["name"] for r in rules][-1].startswith("Default")
    assert {r["owner"]["name"] for r in rules} == {
        "the requirement owner", "Compliance Reviewer", "Project Manager", "Business Analyst",
    }  # fmt: skip
    assert sum(r["is_default"] for r in rules) == 1


@pytest.mark.parametrize(
    ("facts", "rule"),
    [
        (Facts(protected=True), "Protected requirements"),
        (Facts(groups=frozenset({"security"})), "Security exceptions (name your security lead)"),
        (Facts(labels=frozenset({"deadline"})), "Deadline trade-offs"),
        (Facts(category="Duplicate"), "Duplicates"),
        (Facts(category="Conflicting"), decision_rules.DEFAULT_NAME),
    ],
)
def test_the_matching_rule_is_chosen(
    db_session: Session, project: Project, seeded: list[DecisionRule], facts: Facts, rule: str
) -> None:
    assert DecisionRuleEngine(db_session).resolve(project.id, facts).rule_name == rule


def test_the_most_specific_rule_wins(
    db_session: Session, project: Project, seeded: list[DecisionRule], people: dict[str, User]
) -> None:
    decision_rules.create(db_session, project, people["pm"], {
        "name": "Protected duplicates", "match_protected": True, "match_category": "Duplicate",
        "owner_kind": "user", "owner_id": str(people["ba"].id),
    })  # fmt: skip
    decision = DecisionRuleEngine(db_session).resolve(
        project.id, Facts(category="Duplicate", protected=True)
    )
    assert decision.rule_name == "Protected duplicates"


def test_a_project_without_rules_has_the_built_in_default(
    db_session: Session, project: Project
) -> None:
    decision = DecisionRuleEngine(db_session).resolve(project.id, Facts(protected=True))
    assert (decision.rule_id, decision.owner_kind) == (None, "requirement_owner")


# ── the API ─────────────────────────────────────────────────────────────────────────────────
def test_managers_edit_rules_and_it_is_audited(
    client: TestClient,
    db_session: Session,
    project: Project,
    seeded: list[DecisionRule],
    people: dict[str, User],
) -> None:
    pm = headers_for(people["pm"])
    created = client.post(url("projects", project.id, "decision-rules"), json={
        "name": "Payments", "match_group": "Payments", "owner_kind": "user",
        "owner_id": str(people["riya"].id),
        "required_reviewers": [{"kind": "role", "id": str(get_default_role(
            db_session, DefaultRole.BUSINESS_ANALYST).id)}],
    }, headers=pm)  # fmt: skip
    assert created.status_code == 201, created.text
    rule = created.json()
    assert rule["owner"]["name"] == people["riya"].full_name
    assert rule["required_reviewers"][0]["name"] == "Business Analyst"

    patched = client.patch(url("decision-rules", rule["id"]), json={"priority": 5}, headers=pm)
    assert patched.json()["priority"] == 5
    assert client.delete(url("decision-rules", rule["id"]), headers=pm).status_code == 204
    actions = db_session.scalars(select(AuditLog.action)).all()
    assert {"decision_rule_created", "decision_rule_updated", "decision_rule_deleted"} <= {
        str(a) for a in actions
    }


def test_rule_validation(
    client: TestClient, project: Project, seeded: list[DecisionRule], people: dict[str, User],
    make_workspace: Callable[..., Workspace], make_user: Callable[..., User],
) -> None:  # fmt: skip
    pm = headers_for(people["pm"])
    default = next(r for r in seeded if r.is_default)
    matchless = client.post(
        url("projects", project.id, "decision-rules"),
        json={"name": "x", "owner_kind": "requirement_owner"},
        headers=pm,
    )
    assert matchless.json()["error"]["code"] == "match_required"
    outsider = make_user(workspace=make_workspace())
    stranger = client.post(url("projects", project.id, "decision-rules"), json={
        "name": "x", "match_label": "y", "owner_kind": "user", "owner_id": str(outsider.id)},
        headers=pm)  # fmt: skip
    assert stranger.json()["error"]["code"] == "unknown_member"
    assert client.delete(url("decision-rules", default.id), headers=pm).status_code == 409
    narrowed = client.patch(url("decision-rules", default.id), json={"match_label": "x"},
                            headers=pm)  # fmt: skip
    assert narrowed.json()["error"]["code"] == "default_has_no_match"


def test_only_managers_edit_and_other_workspaces_see_nothing(
    client: TestClient,
    project: Project,
    seeded: list[DecisionRule],
    people: dict[str, User],
    make_workspace: Callable[..., Workspace],
    make_user: Callable[..., User],
) -> None:
    body = {"name": "x", "match_label": "y", "owner_kind": "requirement_owner"}
    developer = client.post(url("projects", project.id, "decision-rules"), json=body,
                            headers=headers_for(people["riya"]))  # fmt: skip
    assert developer.status_code == 403
    outsider = headers_for(make_user(role=DefaultRole.OWNER, workspace=make_workspace()))
    assert (
        client.get(url("projects", project.id, "decision-rules"), headers=outsider).status_code
        == 404
    )
    assert client.patch(url("decision-rules", seeded[0].id), json={"priority": 1},
                        headers=outsider).status_code == 404  # fmt: skip


# ── decisions on items ──────────────────────────────────────────────────────────────────────
@pytest.fixture
def protected_pair(
    db_session: Session,
    project: Project,
    make_requirement: Callable[..., Requirement],
    people: dict[str, User],
) -> Finding:
    a = make_requirement("Statements are kept for 7 years.", source_req_id="REQ-020",
                         owner_id=people["riya"].id, is_protected=True)  # fmt: skip
    b = make_requirement("Statements are deleted after 5 years.", source_req_id="REQ-044")
    first, second = CandidatePair.ordered(a.id, b.id)
    pair = CandidatePair(requirement_a_id=first, requirement_b_id=second, similarity_score=0.4)
    db_session.add(pair)
    db_session.flush()
    finding = Finding(
        project_id=project.id,
        candidate_pair_id=pair.id,
        confidence=0.8,
        category=FindingCategory.CONFLICTING,
        rationale="r",
        original_ai_output={},
    )
    db_session.add(finding)  # fmt: skip
    db_session.commit()
    return finding


def test_every_finding_shows_its_decision_owner(
    client: TestClient,
    protected_pair: Finding,
    seeded: list[DecisionRule],
    people: dict[str, User],
) -> None:
    body = client.get(url("findings", protected_pair.id, "decision"),
                      headers=headers_for(people["viewer"])).json()  # fmt: skip
    assert body["rule_name"] == "Protected requirements"
    assert body["owners"] == [
        {"id": str(people["meera"].id), "full_name": people["meera"].full_name}
    ]
    assert body["sentence"] == (
        f"Decides: Compliance Reviewer ({people['meera'].full_name}) — rule Protected requirements"
    )


def test_a_stored_decision_survives_a_rule_change_until_the_next_update(
    db_session: Session,
    project: Project,
    protected_pair: Finding,
    seeded: list[DecisionRule],
    people: dict[str, User],
) -> None:
    first, _ = decision_rules.decision_for(db_session, protected_pair)
    rule = next(r for r in seeded if r.match_protected)
    decision_rules.update(db_session, project, people["pm"], rule,
                          {"owner_kind": "user", "owner_id": str(people["ba"].id)})  # fmt: skip
    kept, _ = decision_rules.decision_for(db_session, protected_pair)
    assert kept.owner_kind == first.owner_kind == "role"
    assert decision_rules.refresh(db_session, protected_pair).owner_kind == "user"


def test_only_the_decision_owner_closes_a_finding_under_an_explicit_rule(
    client: TestClient,
    db_session: Session,
    project: Project,
    make_requirement: Callable[..., Requirement],
    seeded: list[DecisionRule],
    people: dict[str, User],
) -> None:
    a = make_requirement("Sessions last 30 minutes.", source_req_id="REQ-1")
    b = make_requirement("Sessions last thirty minutes.", source_req_id="REQ-2")
    first, second = CandidatePair.ordered(a.id, b.id)
    pair = CandidatePair(requirement_a_id=first, requirement_b_id=second, similarity_score=0.9)
    db_session.add(pair)
    db_session.flush()
    duplicate = Finding(
        project_id=project.id,
        candidate_pair_id=pair.id,
        confidence=0.9,
        category=FindingCategory.DUPLICATE,
        rationale="r",
        original_ai_output={},
    )
    db_session.add(duplicate)  # fmt: skip
    db_session.commit()
    rule = next(r for r in seeded if r.match_category == "Duplicate")
    decision_rules.update(db_session, project, people["pm"], rule,
                          {"owner_kind": "user", "owner_id": str(people["ba"].id)})  # fmt: skip
    other_ba = people["pm"]  # holds finding.review, is not the decision owner
    refused = client.post(url("findings", duplicate.id, "review"),
                          json={"action": "dismiss", "reason": "Same thing"},
                          headers=headers_for(other_ba))  # fmt: skip
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "decision_owner_only"
    allowed = client.post(url("findings", duplicate.id, "review"),
                          json={"action": "dismiss", "reason": "Same thing"},
                          headers=headers_for(people["ba"]))  # fmt: skip
    assert allowed.status_code == 200, allowed.text


def test_merge_needs_the_decision_owner_not_a_head_count(
    db_session: Session,
    project: Project,
    make_requirement: Callable[..., Requirement],
    seeded: list[DecisionRule],
    people: dict[str, User],
    make_user: Callable[..., User],
) -> None:
    from app.models import Review

    requirement = make_requirement(
        "Invoices are kept for 7 years.",
        source_req_id="REQ-9",
        owner_id=people["ba"].id,
        state=RequirementState.APPROVED,
        req_type="constraint",
        stakeholder_group="Security",
    )
    change = ChangeRequest(
        project_id=project.id,
        requirement_id=requirement.id,
        number=1,
        proposer_id=people["riya"].id,
        base_version=1,
        proposed_body="Invoices are kept for 10 years.",
        reason="Law",
    )
    db_session.add(change)  # fmt: skip
    db_session.commit()
    others = [make_user(role=DefaultRole.BUSINESS_ANALYST) for _ in range(3)]
    for reviewer in [people["ba"], *others]:  # many approvals, none by the decision owner
        db_session.add(
            Review(
                change_request_id=change.id,
                reviewer_id=reviewer.id,
                decision="approve",
                proposal_revision=1,
                reviewed_base_version=1,
            )
        )
    db_session.commit()  # fmt: skip

    codes = {u.code for u in AgreementGuard(db_session).unmet(change)}
    assert "decision_missing" in codes  # the Security rule: the Project Manager decides
    db_session.add(
        Review(
            change_request_id=change.id,
            reviewer_id=people["pm"].id,
            decision="approve",
            proposal_revision=1,
            reviewed_base_version=1,
        )
    )
    db_session.commit()  # fmt: skip
    assert "decision_missing" not in {u.code for u in AgreementGuard(db_session).unmet(change)}


def test_change_request_decision_endpoint(
    client: TestClient,
    db_session: Session,
    project: Project,
    make_requirement: Callable[..., Requirement],
    people: dict[str, User],
) -> None:
    requirement = make_requirement("x shall y.", owner_id=people["riya"].id)
    change = ChangeRequest(project_id=project.id, requirement_id=requirement.id, number=1,
                           proposer_id=people["ba"].id, base_version=1, proposed_body="x shall z.",
                           reason="r")  # fmt: skip
    db_session.add(change)
    db_session.commit()
    body: dict[str, Any] = client.get(url("change-requests", change.id, "decision"),
                                      headers=headers_for(people["viewer"])).json()  # fmt: skip
    assert body["is_default"] and body["owners"][0]["id"] == str(people["riya"].id)
