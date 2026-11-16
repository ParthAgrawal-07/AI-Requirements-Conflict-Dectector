"""Owners, groups and ownership requests (Bansil — US-36, FR-59): analysts reassign directly,
contributors ask, the owner or a manager decides, and every change is audited and on the map."""

from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import DefaultRole
from app.models import AuditAction, AuditLog, Project, Requirement, User, Workspace
from app.realtime import bus
from app.realtime.events import GRAPH_DELTA
from tests.analysis_helpers import make_post
from tests.api.conftest import headers_for


@pytest.fixture
def events(monkeypatch: pytest.MonkeyPatch) -> Iterator[bus.InProcessEventBus]:
    test_bus = bus.InProcessEventBus()
    monkeypatch.setattr(bus, "get_bus", lambda: test_bus)
    yield test_bus


@pytest.fixture
def owner(make_user: Callable[..., User]) -> User:
    return make_user(role=DefaultRole.DEVELOPER)


@pytest.fixture
def requirement(db_session: Session, project: Project, owner: User) -> Requirement:
    return make_post(db_session, project, owner, "Sessions end after 5 minutes.", label="REQ-031")


def ask(client: TestClient, requirement: Requirement, who: User, note: str | None = None) -> Any:
    return client.post(
        f"/api/v1/requirements/{requirement.id}/ownership-requests",
        json={"note": note},
        headers=headers_for(who),
    )


def decide(client: TestClient, request_id: str, who: User, accept: bool) -> Any:
    return client.post(
        f"/api/v1/ownership-requests/{request_id}/decision",
        json={"accept": accept},
        headers=headers_for(who),
    )


def test_the_owner_accepts_a_request_and_ownership_moves(
    client: TestClient,
    db_session: Session,
    requirement: Requirement,
    owner: User,
    make_user: Callable[..., User],
    events: bus.InProcessEventBus,
) -> None:
    asker = make_user(role=DefaultRole.QA_ENGINEER)
    request = ask(client, requirement, asker, note="I run the session tests").json()

    response = decide(client, request["id"], owner, accept=True)

    assert response.status_code == 200 and response.json()["status"] == "accepted"
    db_session.refresh(requirement)
    assert requirement.owner_id == asker.id
    changed = db_session.scalar(
        select(AuditLog).where(AuditLog.action == AuditAction.OWNER_CHANGED)
    )
    assert changed is not None and changed.details == {"from": str(owner.id), "to": str(asker.id)}
    (delta,) = [e for e in events.published if e.type == GRAPH_DELTA]
    assert delta.data["sentences"] == ["Test User made Test User the owner of REQ-031."]
    assert delta.data["changed"]["nodes"][0]["owner_id"] == str(asker.id)


def test_a_declined_request_changes_nothing(
    client: TestClient,
    db_session: Session,
    requirement: Requirement,
    owner: User,
    make_user: Callable[..., User],
) -> None:
    request = ask(client, requirement, make_user(role=DefaultRole.DEVELOPER)).json()

    response = decide(client, request["id"], owner, accept=False)
    again = decide(client, request["id"], owner, accept=True)

    assert response.json()["status"] == "declined"
    assert again.status_code == 409 and again.json()["error"]["code"] == "already_decided"
    db_session.refresh(requirement)
    assert requirement.owner_id == owner.id


def test_a_bystander_cannot_decide_but_an_analyst_can(
    client: TestClient,
    requirement: Requirement,
    make_user: Callable[..., User],
) -> None:
    request = ask(client, requirement, make_user(role=DefaultRole.DEVELOPER)).json()
    bystander = make_user(role=DefaultRole.DEVELOPER)
    analyst = make_user(role=DefaultRole.BUSINESS_ANALYST)

    assert decide(client, request["id"], bystander, accept=True).status_code == 403
    assert decide(client, request["id"], analyst, accept=True).status_code == 200


def test_one_pending_request_per_member_and_none_for_the_owner(
    client: TestClient,
    requirement: Requirement,
    owner: User,
    make_user: Callable[..., User],
) -> None:
    asker = make_user(role=DefaultRole.DEVELOPER)

    assert ask(client, requirement, asker).status_code == 201
    duplicate = ask(client, requirement, asker)
    own = ask(client, requirement, owner)

    assert duplicate.status_code == 409 and duplicate.json()["error"]["code"] == "already_requested"
    assert own.status_code == 409 and own.json()["error"]["code"] == "already_owner"
    listed = client.get(
        f"/api/v1/requirements/{requirement.id}/ownership-requests", headers=headers_for(owner)
    ).json()
    assert [r["requester_id"] for r in listed] == [str(asker.id)]


def test_a_viewer_cannot_ask_for_ownership(
    client: TestClient, requirement: Requirement, make_user: Callable[..., User]
) -> None:
    assert ask(client, requirement, make_user(role=DefaultRole.VIEWER)).status_code == 403


def test_an_analyst_reassigns_owner_and_group_directly(
    client: TestClient,
    db_session: Session,
    requirement: Requirement,
    make_user: Callable[..., User],
) -> None:
    analyst = make_user(role=DefaultRole.BUSINESS_ANALYST)
    new_owner = make_user(role=DefaultRole.DEVELOPER)
    url = f"/api/v1/requirements/{requirement.id}"

    moved = client.patch(
        url,
        json={"owner_id": str(new_owner.id), "stakeholder_group": "Security"},
        headers=headers_for(analyst),
    )
    cleared = client.patch(url, json={"stakeholder_group": None}, headers=headers_for(analyst))

    assert moved.status_code == 200
    assert (moved.json()["owner_id"], moved.json()["stakeholder_group"]) == (
        str(new_owner.id),
        "Security",
    )
    assert cleared.json()["stakeholder_group"] is None
    assert cleared.json()["owner_id"] == str(new_owner.id)  # not sent: unchanged
    actions = db_session.scalars(
        select(AuditLog.action).where(AuditLog.requirement_id == requirement.id)
    ).all()
    assert actions.count(AuditAction.GROUP_CHANGED) == 2
    assert actions.count(AuditAction.OWNER_CHANGED) == 1


def test_a_developer_cannot_reassign(
    client: TestClient, requirement: Requirement, make_user: Callable[..., User]
) -> None:
    developer = make_user(role=DefaultRole.DEVELOPER)

    response = client.patch(
        f"/api/v1/requirements/{requirement.id}",
        json={"owner_id": str(developer.id)},
        headers=headers_for(developer),
    )

    assert response.status_code == 403


def test_the_new_owner_must_be_a_member(
    client: TestClient,
    requirement: Requirement,
    make_user: Callable[..., User],
    make_workspace: Callable[..., Workspace],
) -> None:
    analyst = make_user(role=DefaultRole.BUSINESS_ANALYST)
    stranger = make_user(workspace=make_workspace())

    response = client.patch(
        f"/api/v1/requirements/{requirement.id}",
        json={"owner_id": str(stranger.id)},
        headers=headers_for(analyst),
    )

    assert response.status_code == 400 and response.json()["error"]["code"] == "unknown_owner"


def test_another_workspaces_requests_are_a_404(
    client: TestClient,
    requirement: Requirement,
    make_user: Callable[..., User],
    make_workspace: Callable[..., Workspace],
) -> None:
    request = ask(client, requirement, make_user(role=DefaultRole.DEVELOPER)).json()
    stranger = make_user(role=DefaultRole.OWNER, workspace=make_workspace())

    assert decide(client, request["id"], stranger, accept=True).status_code == 404
    assert ask(client, requirement, stranger).status_code == 404
