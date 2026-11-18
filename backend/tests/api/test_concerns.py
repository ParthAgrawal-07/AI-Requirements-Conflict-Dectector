"""Raise a concern (Bansil — US-56, FR-97, NFR-37): a person's finding, its issue, AI misses."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.permissions import DefaultRole
from app.models import (
    CandidatePair,
    Finding,
    FindingCategory,
    Issue,
    Project,
    Requirement,
    User,
)
from app.realtime import bus
from tests.api.conftest import headers_for


@pytest.fixture
def events(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    published: list[Any] = []
    monkeypatch.setattr(bus, "publish", published.append)
    return published


@pytest.fixture
def people(make_user: Callable[..., User]) -> dict[str, User]:
    return {
        "raiser": make_user(role=DefaultRole.DEVELOPER),
        "asha": make_user(role=DefaultRole.BUSINESS_ANALYST),
        "ravi": make_user(role=DefaultRole.DEVELOPER),
    }


@pytest.fixture
def pair(
    make_requirement: Callable[..., Requirement], people: dict[str, User]
) -> list[Requirement]:
    return [
        make_requirement(
            "Statements are kept for 7 years.", source_req_id="REQ-020", owner_id=people["asha"].id
        ),
        make_requirement(
            "Statements are deleted after 5 years.",
            source_req_id="REQ-044",
            owner_id=people["ravi"].id,
        ),
    ]


def raise_(
    client: TestClient, project: Project, user: User, ids: list[Requirement], **extra: object
) -> Any:
    body: dict[str, object] = {
        "category": "Conflicting",
        "requirement_ids": [str(r.id) for r in ids],
        "explanation": "Seven years of retention cannot coexist with deletion after five.",
        "external_ref": "Contract §7.2",
        "severity": "high",
    }
    body.update(extra)
    return client.post(
        f"/api/v1/projects/{project.id}/concerns", json=body, headers=headers_for(user)
    )


def test_a_concern_is_a_person_finding_with_an_issue(
    client: TestClient,
    project: Project,
    people: dict[str, User],
    pair: list[Requirement],
    db_session: Session,
    events: list[Any],
) -> None:
    response = raise_(client, project, people["raiser"], pair)

    assert response.status_code == 201, response.text
    body = response.json()
    finding = body["finding"]
    assert (finding["source"], finding["category"], finding["severity"]) == (
        "Person",
        "Conflicting",
        "high",
    )
    assert finding["raised_by"] == str(people["raiser"].id)
    assert finding["external_ref"] == "Contract §7.2"
    assert body["ai_miss"] is True and finding["ai_miss"] is True
    assert body["issue_key"] == "ISS-1"
    issue = db_session.get(Issue, body["issue_id"])
    assert issue is not None and issue.finding_id is not None and not issue.auto
    assert issue.labels == ["concern", "conflicting", "severity:high"]
    assert "Reference: Contract §7.2" in issue.body
    edges = [e for ev in events if ev.type == "graph.delta" for e in ev.data["added"]["edges"]]
    assert [e["found_by"] for e in edges] == ["person"]
    sentences = [s for ev in events if ev.type == "graph.delta" for s in ev.data["sentences"]]
    assert "Test User raised a concern: conflict on REQ-020 and REQ-044." in sentences


def test_it_is_assigned_to_the_owners(
    client: TestClient, project: Project, people: dict[str, User], pair: list[Requirement]
) -> None:
    body = raise_(client, project, people["raiser"], pair).json()
    issue = client.get(
        f"/api/v1/issues/{body['issue_id']}", headers=headers_for(people["raiser"])
    ).json()
    assert {a["id"] for a in issue["assignees"]} == {str(people["asha"].id), str(people["ravi"].id)}


def test_not_an_ai_miss_when_the_analysis_already_flagged_the_pair(
    client: TestClient,
    project: Project,
    people: dict[str, User],
    pair: list[Requirement],
    db_session: Session,
) -> None:
    first, second = CandidatePair.ordered(pair[0].id, pair[1].id)
    candidate = CandidatePair(requirement_a_id=first, requirement_b_id=second, similarity_score=0.8)
    db_session.add(candidate)
    db_session.flush()
    db_session.add(
        Finding(
            project_id=project.id,
            candidate_pair_id=candidate.id,
            category=FindingCategory.DUPLICATE,
            confidence=0.7,
            rationale="r",
            original_ai_output={},
        )
    )
    db_session.commit()

    body = raise_(client, project, people["raiser"], pair).json()

    assert body["ai_miss"] is False
    # Both live on the same pair: the one-live-finding rule binds the analysis only.
    pairs = db_session.scalar(select(func.count()).select_from(CandidatePair))
    live = db_session.scalar(
        select(func.count()).select_from(Finding).where(Finding.candidate_pair_id == candidate.id)
    )
    assert (pairs, live) == (1, 2)


def test_a_single_requirement_concern(
    client: TestClient, project: Project, people: dict[str, User], pair: list[Requirement]
) -> None:
    body = raise_(
        client,
        project,
        people["raiser"],
        pair[:1],
        category="Ambiguous",
        explanation="'Statements' could mean monthly or yearly statements.",
        external_ref=None,
    ).json()
    assert body["finding"]["requirements"][0]["label"] == "REQ-020"
    assert body["finding"]["severity"] == "high"


@pytest.mark.parametrize(
    ("category", "count"), [("Conflicting", 1), ("Ambiguous", 2), ("Duplicate", 3)]
)
def test_the_number_of_requirements_must_fit_the_category(
    client: TestClient,
    project: Project,
    people: dict[str, User],
    pair: list[Requirement],
    category: str,
    count: int,
) -> None:
    ids = (pair * 2)[:count]
    response = raise_(client, project, people["raiser"], ids, category=category)
    assert response.status_code in (400, 422)


def test_a_viewer_cannot_raise_one(
    client: TestClient, project: Project, pair: list[Requirement], make_user: Callable[..., User]
) -> None:
    assert raise_(client, project, make_user(role=DefaultRole.VIEWER), pair).status_code == 403


def test_the_findings_list_filters_by_source(
    client: TestClient, project: Project, people: dict[str, User], pair: list[Requirement]
) -> None:
    raise_(client, project, people["raiser"], pair)
    url = f"/api/v1/projects/{project.id}/findings"
    person = client.get(
        url, params={"source": "person"}, headers=headers_for(people["raiser"])
    ).json()
    ai = client.get(url, params={"source": "ai,rule"}, headers=headers_for(people["raiser"])).json()
    bad = client.get(url, params={"source": "robot"}, headers=headers_for(people["raiser"]))
    assert (person["total"], ai["total"], bad.status_code) == (1, 0, 422)


def test_another_workspaces_project_is_not_found(
    client: TestClient,
    make_project: Callable[..., Project],
    make_workspace: Callable[..., object],
    people: dict[str, User],
    pair: list[Requirement],
) -> None:
    foreign = make_project(workspace=make_workspace())
    assert raise_(client, foreign, people["raiser"], pair).status_code == 404
