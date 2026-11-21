"""From an accepted suggestion to a change (Bansil — US-51 wiring, US-45, US-33; DR-04)."""

from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.permissions import DefaultRole
from app.core.rate_limit import InMemoryRateLimiter, get_rate_limiter
from app.models import (
    CandidatePair,
    Channel,
    Finding,
    FindingCategory,
    Issue,
    IssueRequirement,
    Project,
    Requirement,
    RequirementOrigin,
    RequirementState,
    User,
)
from app.models.suggestion import READY, Suggestion
from app.realtime import bus
from tests.api.conftest import headers_for
from tests.api.test_composer import FIELDS

NEW_TEXT = "Sessions shall time out after 15 minutes."


@pytest.fixture(autouse=True)
def quiet(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    from app.main import app

    monkeypatch.setattr(bus, "publish", lambda _event: None)
    app.dependency_overrides[get_rate_limiter] = InMemoryRateLimiter
    yield
    app.dependency_overrides.pop(get_rate_limiter, None)


@pytest.fixture
def people(make_user: Callable[..., User]) -> dict[str, User]:
    return {
        "riya": make_user(role=DefaultRole.DEVELOPER),
        "arjun": make_user(role=DefaultRole.DEVELOPER),
    }


@pytest.fixture
def setup(
    db_session: Session,
    project: Project,
    make_requirement: Callable[..., Requirement],
    people: dict[str, User],
) -> dict[str, Any]:
    a = make_requirement("Sessions shall time out after 30 minutes.", source_req_id="REQ-012",
                         owner_id=people["riya"].id, state=RequirementState.APPROVED)  # fmt: skip
    b = make_requirement("Payment screens shall time out after 5 minutes.",
                         source_req_id="REQ-031", owner_id=people["arjun"].id,
                         state=RequirementState.APPROVED)  # fmt: skip
    first, second = CandidatePair.ordered(a.id, b.id)
    pair = CandidatePair(requirement_a_id=first, requirement_b_id=second, similarity_score=0.8)
    db_session.add(pair)
    db_session.flush()
    finding = Finding(
        project_id=project.id,
        candidate_pair_id=pair.id,
        confidence=0.9,
        category=FindingCategory.CONFLICTING,
        rationale="r",
        original_ai_output={},
    )
    db_session.add(finding)  # fmt: skip
    db_session.flush()
    issue = Issue(project_id=project.id, number=1, title="Conflict", auto=True,
                  finding_id=finding.id)  # fmt: skip
    db_session.add(issue)
    db_session.flush()
    db_session.add_all([IssueRequirement(issue_id=issue.id, requirement_id=r.id) for r in (a, b)])
    option = {"text": NEW_TEXT, "target": "REQ-012", "target_requirement_id": str(a.id),
              "trade_off": "t", "confidence": 0.7, "tbd_slots": []}  # fmt: skip
    suggestion = Suggestion(finding_id=finding.id, project_id=project.id, category="Conflicting",
                            status=READY, options=[option])  # fmt: skip
    db_session.add(suggestion)
    db_session.add(Channel(project_id=project.id, name="general", is_default=True))
    db_session.commit()
    return {"a": a, "b": b, "issue": issue, "suggestion": suggestion}


def accept(client: TestClient, suggestion: Suggestion, who: User) -> dict[str, Any]:
    response = client.post(f"/api/v1/suggestions/{suggestion.id}/feedback",
                           json={"action": "accepted", "option_index": 0},
                           headers=headers_for(who))  # fmt: skip
    assert response.status_code == 201, response.text
    prefill: dict[str, Any] = response.json()["prefill"]
    return prefill


def open_request(client: TestClient, requirement: Requirement, who: User, **extra: Any) -> Any:
    body = {"proposed_body": NEW_TEXT, "reason": "As the AI suggested", **extra}
    return client.post(f"/api/v1/requirements/{requirement.id}/change-requests", json=body,
                       headers=headers_for(who))  # fmt: skip


def test_an_accepted_suggestion_opens_a_prefilled_request_that_resolves_the_issue(
    client: TestClient, setup: dict[str, Any], people: dict[str, User]
) -> None:
    prefill = accept(client, setup["suggestion"], people["riya"])
    assert prefill["kind"] == "change_request" and prefill["issue_number"] == 1

    response = open_request(client, setup["a"], people["riya"],
                            proposed_body=prefill["proposed_body"],
                            source_suggestion_id=prefill["source_suggestion_id"])  # fmt: skip

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["source_suggestion_id"] == str(setup["suggestion"].id)
    assert [i["key"] for i in body["resolves"]] == ["ISS-1"]


def test_the_acceptance_must_be_on_record(
    client: TestClient, setup: dict[str, Any], people: dict[str, User]
) -> None:
    response = open_request(client, setup["a"], people["riya"],
                            source_suggestion_id=str(setup["suggestion"].id))  # fmt: skip
    assert (response.status_code, response.json()["error"]["code"]) == (409, "not_accepted")


def test_the_suggestion_must_target_that_requirement(
    client: TestClient, setup: dict[str, Any], people: dict[str, User]
) -> None:
    accept(client, setup["suggestion"], people["riya"])
    response = open_request(client, setup["b"], people["riya"],
                            source_suggestion_id=str(setup["suggestion"].id))  # fmt: skip
    assert response.json()["error"]["code"] == "suggestion_mismatch"


def test_a_superseded_suggestion_cannot_be_used(
    client: TestClient, db_session: Session, setup: dict[str, Any], people: dict[str, User]
) -> None:
    accept(client, setup["suggestion"], people["riya"])
    setup["suggestion"].status = "superseded"
    db_session.commit()
    response = open_request(client, setup["a"], people["riya"],
                            source_suggestion_id=str(setup["suggestion"].id))  # fmt: skip
    assert response.json()["error"]["code"] == "suggestion_unusable"


def test_unfilled_placeholders_are_refused(
    client: TestClient, setup: dict[str, Any], people: dict[str, User]
) -> None:
    response = open_request(
        client,
        setup["a"],
        people["riya"],
        proposed_body="Sessions shall time out after [TBD — confirm].",
    )
    assert (response.status_code, response.json()["error"]["code"]) == (400, "tbd_unfilled")


def test_a_post_supersedes_ones_own_proposal(
    client: TestClient, db_session: Session, setup: dict[str, Any], people: dict[str, User]
) -> None:
    setup["a"].state = RequirementState.PROPOSED
    db_session.commit()
    prefill = accept(client, setup["suggestion"], people["riya"])
    assert prefill["kind"] == "post"

    response = client.post(
        f"/api/v1/projects/{setup['a'].project_id}/requirements",
        json={"fields": FIELDS, "supersedes": prefill["requirement_id"],
              "source_suggestion_id": prefill["source_suggestion_id"]},
        headers=headers_for(people["riya"]),
    )  # fmt: skip

    assert response.status_code == 201, response.text
    db_session.refresh(setup["a"])
    assert setup["a"].state is RequirementState.REJECTED


def test_only_the_owner_supersedes_a_proposal(
    client: TestClient, db_session: Session, setup: dict[str, Any], people: dict[str, User]
) -> None:
    setup["a"].state = RequirementState.PROPOSED
    db_session.commit()
    response = client.post(
        f"/api/v1/projects/{setup['a'].project_id}/requirements",
        json={"fields": FIELDS, "supersedes": str(setup["a"].id)},
        headers=headers_for(people["arjun"]),
    )
    assert response.status_code == 403


def test_a_post_cannot_supersede_a_requirement_in_another_project(
    client: TestClient,
    db_session: Session,
    setup: dict[str, Any],
    people: dict[str, User],
    make_project: Callable[..., Project],
) -> None:
    author = people["riya"]
    other = Requirement(
        project_id=make_project().id,
        owner_id=author.id,
        origin=RequirementOrigin.POST,
        body="An unrelated proposal.",
    )
    db_session.add(other)
    db_session.commit()

    response = client.post(
        f"/api/v1/projects/{setup['a'].project_id}/requirements",
        json={"fields": FIELDS, "supersedes": str(other.id)},
        headers=headers_for(author),
    )

    assert (response.status_code, response.json()["error"]["code"]) == (400, "unknown_requirement")
    assert other.state == RequirementState.PROPOSED


def test_a_channel_post_supersedes_too(
    client: TestClient, db_session: Session, setup: dict[str, Any], people: dict[str, User]
) -> None:
    setup["a"].state = RequirementState.PROPOSED
    db_session.commit()
    prefill = accept(client, setup["suggestion"], people["riya"])
    channel = db_session.query(Channel).filter_by(project_id=setup["a"].project_id).one()

    response = client.post(
        f"/api/v1/channels/{channel.id}/requirement-posts",
        json={"fields": FIELDS, "supersedes": prefill["requirement_id"],
              "source_suggestion_id": prefill["source_suggestion_id"]},
        headers=headers_for(people["riya"]),
    )  # fmt: skip

    assert response.status_code == 201, response.text
    db_session.refresh(setup["a"])
    assert setup["a"].state is RequirementState.REJECTED
