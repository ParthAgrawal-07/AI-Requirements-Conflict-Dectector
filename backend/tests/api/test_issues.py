"""Issue routes (Dhavni — US-52, FR-86): open, list, edit, close, reopen, comment."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import DefaultRole
from app.models import AuditLog, Project, Requirement, RequirementOrigin, User, Workspace
from app.realtime import bus
from app.realtime.events import ISSUE_CLOSED, ISSUE_OPENED, ISSUE_REOPENED
from tests.api.conftest import headers_for


@pytest.fixture
def events(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    published: list[Any] = []
    monkeypatch.setattr(bus, "publish", published.append)
    return published


@pytest.fixture
def analyst(make_user: Callable[..., User]) -> User:
    return make_user(role=DefaultRole.BUSINESS_ANALYST)  # holds issue.manage


@pytest.fixture
def developer(make_user: Callable[..., User]) -> User:
    return make_user(role=DefaultRole.DEVELOPER)  # issue.open, not issue.manage


@pytest.fixture
def reqs(make_requirement: Callable[..., Requirement]) -> list[Requirement]:
    return [
        make_requirement("Sessions end after 30 minutes.", source_req_id="REQ-014"),
        make_requirement("Sessions end after 5 minutes.", source_req_id="REQ-031"),
    ]


def open_issue(
    client: TestClient, project: Project, user: User, reqs: list[Requirement], **extra: object
) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/projects/{project.id}/issues",
        json={
            "title": "Which timeout?",
            "body": "They disagree.",
            "requirement_ids": [str(r.id) for r in reqs],
            **extra,
        },
        headers=headers_for(user),
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def test_open_an_issue_numbers_it_and_announces_it(
    client: TestClient,
    project: Project,
    developer: User,
    analyst: User,
    reqs: list[Requirement],
    events: list[Any],
    db_session: Session,
) -> None:
    first = open_issue(
        client, project, developer, reqs, labels=[" UX ", "ux"], assignee_ids=[str(analyst.id)]
    )
    second = open_issue(client, project, developer, reqs[:1])

    assert (first["key"], second["key"]) == ("ISS-1", "ISS-2")
    assert first["labels"] == ["ux"] and first["author"]["id"] == str(developer.id)
    assert [a["id"] for a in first["assignees"]] == [str(analyst.id)]
    assert [r["label"] for r in first["requirements"]] == ["REQ-014", "REQ-031"]
    opened = [e for e in events if e.type == ISSUE_OPENED]
    assert opened[0].data["number"] == 1 and "title" not in opened[0].data  # ids only (CR-04)
    deltas = [e for e in events if e.type == "graph.delta"]
    assert deltas[0].data["sentences"] == ["Test User opened ISS-1 on REQ-014 and REQ-031."]
    assert {n["open_issues"] for n in deltas[0].data["changed"]["nodes"]} == {1}
    assert db_session.scalar(select(AuditLog).where(AuditLog.action == "issue_opened"))


def test_numbers_are_per_project(
    client: TestClient,
    project: Project,
    make_project: Callable[..., Project],
    developer: User,
    reqs: list[Requirement],
    db_session: Session,
) -> None:
    other = make_project()
    elsewhere = Requirement(project_id=other.id, body="x", origin=RequirementOrigin.POST)
    db_session.add(elsewhere)
    db_session.commit()
    open_issue(client, project, developer, reqs)
    assert open_issue(client, other, developer, [elsewhere])["number"] == 1


def test_requirements_and_assignees_must_belong_here(
    client: TestClient,
    project: Project,
    developer: User,
    reqs: list[Requirement],
    make_workspace: Callable[..., Workspace],
    make_user: Callable[..., User],
) -> None:
    stranger = make_user(role=DefaultRole.DEVELOPER, workspace=make_workspace())
    url = f"/api/v1/projects/{project.id}/issues"
    bad_requirement = client.post(
        url,
        json={"title": "Hmm", "requirement_ids": [str(uuid.uuid4())]},
        headers=headers_for(developer),
    )
    bad_assignee = client.post(
        url,
        json={
            "title": "Hmm",
            "requirement_ids": [str(reqs[0].id)],
            "assignee_ids": [str(stranger.id)],
        },
        headers=headers_for(developer),
    )
    assert bad_requirement.json()["error"]["code"] == "unknown_requirement"
    assert bad_assignee.json()["error"]["code"] == "unknown_assignee"


def test_list_filters(
    client: TestClient,
    project: Project,
    developer: User,
    analyst: User,
    reqs: list[Requirement],
) -> None:
    open_issue(client, project, developer, reqs, labels=["ux"], assignee_ids=[str(analyst.id)])
    second = open_issue(client, project, developer, reqs[1:])
    client.patch(
        f"/api/v1/issues/{second['id']}", json={"status": "closed"}, headers=headers_for(developer)
    )
    url = f"/api/v1/projects/{project.id}/issues"

    def numbers(**params: str) -> list[int]:
        page = client.get(url, params=params, headers=headers_for(developer)).json()
        return [i["number"] for i in page["items"]]

    assert numbers() == [2, 1]
    assert numbers(status="open") == [1]
    assert numbers(label="UX") == [1]
    assert numbers(assignee=str(analyst.id)) == [1]
    assert numbers(requirement=str(reqs[1].id)) == [2, 1]
    assert numbers(auto="true") == []


def test_who_may_edit_what(
    client: TestClient,
    project: Project,
    developer: User,
    analyst: User,
    make_user: Callable[..., User],
    reqs: list[Requirement],
) -> None:
    issue = open_issue(client, project, developer, reqs)
    other_dev = make_user(role=DefaultRole.DEVELOPER)
    url = f"/api/v1/issues/{issue['id']}"

    by_author = client.patch(
        url, json={"title": "Which timeout wins?"}, headers=headers_for(developer)
    )
    by_other = client.patch(url, json={"title": "Mine now"}, headers=headers_for(other_dev))
    labels_by_author = client.patch(url, json={"labels": ["x"]}, headers=headers_for(developer))
    labels_by_manager = client.patch(
        url,
        json={"labels": ["security"], "assignee_ids": [str(other_dev.id)]},
        headers=headers_for(analyst),
    )

    assert by_author.json()["title"] == "Which timeout wins?"
    assert by_other.status_code == 403 and labels_by_author.status_code == 403
    assert labels_by_manager.json()["labels"] == ["security"]
    assert [a["id"] for a in labels_by_manager.json()["assignees"]] == [str(other_dev.id)]


def test_an_assignee_may_close_and_the_author_may_reopen(
    client: TestClient,
    project: Project,
    developer: User,
    make_user: Callable[..., User],
    reqs: list[Requirement],
    analyst: User,
    events: list[Any],
) -> None:
    assignee = make_user(role=DefaultRole.DEVELOPER)
    bystander = make_user(role=DefaultRole.DEVELOPER)
    issue = open_issue(client, project, developer, reqs, assignee_ids=[str(assignee.id)])
    url = f"/api/v1/issues/{issue['id']}"

    refused = client.patch(url, json={"status": "closed"}, headers=headers_for(bystander))
    closed = client.patch(url, json={"status": "closed"}, headers=headers_for(assignee))
    reopened = client.patch(url, json={"status": "open"}, headers=headers_for(developer))

    assert refused.status_code == 403
    assert (closed.json()["status"], closed.json()["close_reason"]) == ("closed", "manual")
    assert (reopened.json()["status"], reopened.json()["close_reason"]) == ("open", None)
    kinds = [e.type for e in events if e.type in (ISSUE_CLOSED, ISSUE_REOPENED)]
    assert kinds == [ISSUE_CLOSED, ISSUE_REOPENED]
    sentences = [s for e in events if e.type == "graph.delta" for s in e.data["sentences"]]
    assert "Test User closed ISS-1." in sentences and "Test User reopened ISS-1." in sentences


def test_comments(
    client: TestClient, project: Project, developer: User, reqs: list[Requirement]
) -> None:
    issue = open_issue(client, project, developer, reqs)
    url = f"/api/v1/issues/{issue['id']}/comments"

    posted = client.post(url, json={"body": "  Ask the client.  "}, headers=headers_for(developer))
    empty = client.post(url, json={"body": "   "}, headers=headers_for(developer))
    listed = client.get(url, headers=headers_for(developer)).json()
    again = client.get(f"/api/v1/issues/{issue['id']}", headers=headers_for(developer)).json()

    assert posted.status_code == 201 and posted.json()["body"] == "Ask the client."
    assert empty.status_code == 400
    assert [c["body"] for c in listed] == ["Ask the client."]
    assert listed[0]["author"]["id"] == str(developer.id)
    assert again["comment_count"] == 1


def test_a_viewer_reads_but_cannot_open(
    client: TestClient,
    project: Project,
    developer: User,
    make_user: Callable[..., User],
    reqs: list[Requirement],
) -> None:
    open_issue(client, project, developer, reqs)
    viewer = make_user(role=DefaultRole.VIEWER)
    listed = client.get(f"/api/v1/projects/{project.id}/issues", headers=headers_for(viewer))
    refused = client.post(
        f"/api/v1/projects/{project.id}/issues",
        json={"title": "Nope", "requirement_ids": [str(reqs[0].id)]},
        headers=headers_for(viewer),
    )
    assert listed.json()["total"] == 1 and refused.status_code == 403


def test_another_workspace_gets_404(
    client: TestClient,
    project: Project,
    developer: User,
    reqs: list[Requirement],
    make_workspace: Callable[..., Workspace],
    make_user: Callable[..., User],
) -> None:
    issue = open_issue(client, project, developer, reqs)
    outsider = make_user(role=DefaultRole.OWNER, workspace=make_workspace())
    for method, path in (
        ("GET", f"/api/v1/issues/{issue['id']}"),
        ("PATCH", f"/api/v1/issues/{issue['id']}"),
        ("GET", f"/api/v1/issues/{issue['id']}/comments"),
        ("POST", f"/api/v1/issues/{issue['id']}/comments"),
    ):
        body = {"body": "hi"} if method == "POST" else {"status": "closed"}
        response = client.request(method, path, json=body, headers=headers_for(outsider))
        assert response.status_code == 404, (method, path)
