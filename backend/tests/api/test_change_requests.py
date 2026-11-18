"""Change-request intake (Bansil — US-33, FR-62, FR-89): RCR-n with its base version."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import DefaultRole
from app.graph import deltas
from app.models import (
    AuditLog,
    ChangeRequest,
    ChangeRequestRevision,
    Issue,
    Project,
    ProjectStatus,
    Requirement,
    RequirementState,
    RequirementVersion,
    User,
)
from app.realtime import bus
from app.realtime.events import CHANGE_REQUEST_OPENED
from tests.api.conftest import headers_for

TEXT = "Sessions shall expire after 30 minutes of inactivity."
PROPOSED = "Sessions shall expire after 15 minutes of inactivity."


@pytest.fixture
def events(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    published: list[Any] = []
    monkeypatch.setattr(bus, "publish", published.append)
    return published


@pytest.fixture
def developer(make_user: Callable[..., User]) -> User:
    return make_user(role=DefaultRole.DEVELOPER)


@pytest.fixture
def approved(make_requirement: Callable[..., Requirement], db_session: Session) -> Requirement:
    requirement = make_requirement(TEXT, source_req_id="REQ-014", state=RequirementState.APPROVED)
    db_session.add(
        RequirementVersion(requirement_id=requirement.id, version_no=1, body_snapshot=TEXT)
    )
    db_session.commit()
    return requirement


def propose(client: TestClient, requirement: Requirement, user: User, **body: object) -> Any:
    payload: dict[str, object] = {"proposed_body": PROPOSED, "reason": "The bank asks for 15."}
    payload.update(body)
    return client.post(
        f"/api/v1/requirements/{requirement.id}/change-requests",
        json=payload,
        headers=headers_for(user),
    )


def test_open_a_change_request(
    client: TestClient,
    approved: Requirement,
    developer: User,
    db_session: Session,
    events: list[Any],
) -> None:
    response = propose(client, approved, developer, base_version=1)

    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["key"], body["status"], body["kind"]) == ("RCR-1", "open", "modify")
    assert (body["base_version"], body["proposal_revision"]) == (1, 1)
    assert (body["base_body"], body["current_body"], body["proposed_body"]) == (
        TEXT,
        TEXT,
        PROPOSED,
    )
    assert body["proposer"]["id"] == str(developer.id)
    revision = db_session.scalar(select(ChangeRequestRevision))
    assert revision is not None and (revision.revision, revision.proposed_body) == (1, PROPOSED)
    assert db_session.scalar(select(AuditLog).where(AuditLog.action == "change_request_opened"))
    [opened] = [e for e in events if e.type == CHANGE_REQUEST_OPENED]
    assert opened.data["number"] == 1 and "proposed_body" not in opened.data  # never text
    sentences = [s for e in events if e.type == "graph.delta" for s in e.data["sentences"]]
    assert sentences == ["Test User proposed a change to REQ-014 (RCR-1)."]


def test_numbers_go_up_per_project(
    client: TestClient, approved: Requirement, developer: User
) -> None:
    propose(client, approved, developer)
    second = propose(
        client, approved, developer, proposed_body="Sessions shall end after 10 minutes."
    )
    assert second.json()["key"] == "RCR-2"  # competing requests are allowed


def test_a_moved_base_version_is_refused(
    client: TestClient, approved: Requirement, developer: User, db_session: Session
) -> None:
    approved.current_version = 2
    db_session.commit()
    response = propose(client, approved, developer, base_version=1)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "base_version_moved"


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ({"proposed_body": TEXT}, "no_change"),
        ({"proposed_body": "   "}, "proposed_body_required"),
        ({"kind": "deprecate", "proposed_body": "x"}, "unexpected_body"),
    ],
)
def test_bad_proposals(
    client: TestClient, approved: Requirement, developer: User, body: dict[str, object], code: str
) -> None:
    response = propose(client, approved, developer, **body)
    assert response.status_code == 400 and response.json()["error"]["code"] == code


def test_deprecation_has_no_text_and_needs_the_baseline(
    client: TestClient,
    approved: Requirement,
    developer: User,
    make_requirement: Callable[..., Requirement],
) -> None:
    proposed = make_requirement("A proposal.", state=RequirementState.PROPOSED)

    ok = propose(client, approved, developer, kind="deprecate", proposed_body=None)
    refused = propose(client, proposed, developer, kind="deprecate", proposed_body=None)

    assert ok.status_code == 201 and ok.json()["proposed_body"] is None
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "not_in_baseline"


def test_rejected_and_deprecated_requirements_take_no_changes(
    client: TestClient, make_requirement: Callable[..., Requirement], developer: User
) -> None:
    for state in (RequirementState.REJECTED, RequirementState.DEPRECATED):
        requirement = make_requirement("Old.", state=state)
        response = propose(client, requirement, developer)
        assert response.json()["error"]["code"] == "requirement_closed", state


def test_resolves_issues_named_in_the_reason_or_listed(
    client: TestClient,
    approved: Requirement,
    developer: User,
    project: Project,
    db_session: Session,
) -> None:
    issues = [Issue(project_id=project.id, number=n, title=f"Issue {n}") for n in (1, 2, 3)]
    issues[2].status, issues[2].close_reason = "closed", "manual"
    db_session.add_all(issues)
    db_session.commit()

    ok = propose(
        client, approved, developer, reason="Resolves ISS-1, agreed with the bank.", resolves=[2]
    )
    closed = propose(client, approved, developer, reason="Fixes ISS-3")
    unknown = propose(client, approved, developer, resolves=[9])

    assert [i["key"] for i in ok.json()["resolves"]] == ["ISS-1", "ISS-2"]
    assert closed.json()["error"]["code"] == "issue_not_open"
    assert unknown.json()["error"]["code"] == "unknown_issue"
    assert "9" not in unknown.json()["error"]["message"]  # never echoes submitted values


def test_a_draft_stays_quiet(
    client: TestClient, approved: Requirement, developer: User, events: list[Any]
) -> None:
    response = propose(client, approved, developer, draft=True)
    assert response.json()["status"] == "draft"
    assert not [e for e in events if e.type == "graph.delta"]


def test_list_and_get(
    client: TestClient,
    approved: Requirement,
    developer: User,
    project: Project,
    make_requirement: Callable[..., Requirement],
) -> None:
    other = make_requirement("Another.", state=RequirementState.APPROVED)
    first = propose(client, approved, developer).json()
    propose(client, other, developer, proposed_body="Another, changed.", draft=True)
    url = f"/api/v1/projects/{project.id}/change-requests"

    def keys(**params: str) -> list[str]:
        page = client.get(url, params=params, headers=headers_for(developer)).json()
        return [c["key"] for c in page["items"]]

    assert keys() == ["RCR-2", "RCR-1"]
    assert keys(status="open") == ["RCR-1"]
    assert keys(requirement=str(other.id)) == ["RCR-2"]
    one = client.get(f"/api/v1/change-requests/{first['id']}", headers=headers_for(developer))
    assert one.json()["requirement"]["label"] == "REQ-014"


def test_a_viewer_cannot_propose(
    client: TestClient, approved: Requirement, make_user: Callable[..., User]
) -> None:
    assert propose(client, approved, make_user(role=DefaultRole.VIEWER)).status_code == 403


def test_the_base_text_stays_when_the_requirement_moves_on(
    client: TestClient, approved: Requirement, developer: User, db_session: Session
) -> None:
    created = propose(client, approved, developer, base_version=1).json()
    approved.body, approved.current_version = "Sessions shall expire after 20 minutes.", 2
    db_session.add(
        RequirementVersion(requirement_id=approved.id, version_no=2, body_snapshot=approved.body)
    )
    db_session.commit()

    body = client.get(
        f"/api/v1/change-requests/{created['id']}", headers=headers_for(developer)
    ).json()

    assert (body["base_version"], body["base_body"]) == (1, TEXT)
    assert (body["requirement"]["current_version"], body["current_body"]) == (2, approved.body)


def test_a_project_in_setup_takes_no_change_requests(
    client: TestClient,
    approved: Requirement,
    developer: User,
    project: Project,
    db_session: Session,
) -> None:
    project.status = ProjectStatus.SETUP
    db_session.commit()
    response = propose(client, approved, developer)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "project_in_setup"
    assert db_session.scalar(select(ChangeRequest)) is None


@pytest.mark.parametrize("reason", ["   ", "ok\x00"])
def test_a_blank_or_unstorable_reason_is_refused(
    client: TestClient, approved: Requirement, developer: User, reason: str
) -> None:
    assert propose(client, approved, developer, reason=reason).status_code == 422


def test_reading_a_protected_requirement_s_request_is_audited(
    client: TestClient,
    approved: Requirement,
    developer: User,
    project: Project,
    db_session: Session,
) -> None:
    created = propose(client, approved, developer).json()
    approved.is_protected = True
    db_session.commit()

    client.get(f"/api/v1/change-requests/{created['id']}", headers=headers_for(developer))
    client.get(f"/api/v1/projects/{project.id}/change-requests", headers=headers_for(developer))

    audits = db_session.scalars(
        select(AuditLog).where(
            AuditLog.action == "viewed_protected", AuditLog.requirement_id == approved.id
        )
    ).all()
    assert len(audits) == 2 and all(a.details in (None, {}) for a in audits)  # ids only


def test_a_failed_announcement_does_not_fail_the_request(
    client: TestClient,
    approved: Requirement,
    developer: User,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken(*_: object, **__: object) -> None:
        raise RuntimeError("map down")

    monkeypatch.setattr(deltas, "publish", broken)
    response = propose(client, approved, developer)
    assert response.status_code == 201, response.text
    assert len(db_session.scalars(select(ChangeRequest)).all()) == 1  # a retry is not needed


def test_non_members_get_404_on_every_route(
    client: TestClient,
    approved: Requirement,
    developer: User,
    project: Project,
    make_user: Callable[..., User],
) -> None:
    created = propose(client, approved, developer).json()
    outsider = make_user(role=None)

    responses = [
        propose(client, approved, outsider),
        client.get(f"/api/v1/projects/{project.id}/change-requests", headers=headers_for(outsider)),
        client.get(f"/api/v1/change-requests/{created['id']}", headers=headers_for(outsider)),
    ]

    assert [r.status_code for r in responses] == [404, 404, 404]
