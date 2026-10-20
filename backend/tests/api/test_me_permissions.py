"""GET /me/permissions — what the UI uses to show or hide actions (US-27)."""

import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.permissions import DEFAULT_ROLE_PERMISSIONS, PERMISSIONS, DefaultRole
from app.models import Project, ProjectMember, User, Workspace
from app.services.membership import get_default_role
from tests.api.conftest import headers_for

URL = "/api/v1/me/permissions"


@pytest.mark.parametrize("role", list(DefaultRole))
def test_returns_the_role_and_its_permissions_for_a_project(
    client: TestClient, make_user: Callable[..., User], project: Project, role: DefaultRole
) -> None:
    response = client.get(
        URL, params={"project": str(project.id)}, headers=headers_for(make_user(role=role))
    )

    assert response.status_code == 200
    body = response.json()
    assert body["role"]["name"] == role.value and body["role"]["is_default"] is True
    assert body["project_id"] == str(project.id)
    assert body["workspace_id"] == str(project.workspace_id)
    assert body["permissions"] == sorted(DEFAULT_ROLE_PERMISSIONS[role])
    assert set(body["permissions"]) <= set(PERMISSIONS)


def test_workspace_scope_has_no_project_id(
    client: TestClient, user: User, workspace: Workspace
) -> None:
    body = client.get(
        URL, params={"workspace": str(workspace.id)}, headers=headers_for(user)
    ).json()
    assert body["project_id"] is None and body["workspace_id"] == str(workspace.id)


def test_compliance_reviewers_protected_only_permission_is_reported(
    client: TestClient, make_user: Callable[..., User], project: Project
) -> None:
    reviewer = make_user(role=DefaultRole.COMPLIANCE_REVIEWER)
    body = client.get(
        URL, params={"project": str(project.id)}, headers=headers_for(reviewer)
    ).json()
    assert body["protected_only"] == ["finding.review"]
    assert "finding.review" in body["permissions"]


def test_the_project_role_override_is_what_the_ui_gets(
    client: TestClient, make_user: Callable[..., User], project: Project, db_session: Session
) -> None:
    viewer = make_user(role=DefaultRole.VIEWER)
    db_session.add(
        ProjectMember(
            project_id=project.id,
            user_id=viewer.id,
            role_override_id=get_default_role(db_session, DefaultRole.BUSINESS_ANALYST).id,
        )
    )
    db_session.commit()
    headers = headers_for(viewer)

    in_project = client.get(URL, params={"project": str(project.id)}, headers=headers).json()
    in_workspace = client.get(
        URL, params={"workspace": str(project.workspace_id)}, headers=headers
    ).json()

    assert in_project["role"]["name"] == "Business Analyst"
    assert in_workspace["role"]["name"] == "Viewer"


def test_project_and_workspace_may_both_be_given_when_they_agree(
    client: TestClient, user: User, project: Project
) -> None:
    response = client.get(
        URL,
        params={"project": str(project.id), "workspace": str(project.workspace_id)},
        headers=headers_for(user),
    )
    assert response.status_code == 200


def test_a_project_from_another_workspace_than_the_one_named_is_404(
    client: TestClient, user: User, project: Project, make_workspace: Callable[..., Workspace]
) -> None:
    response = client.get(
        URL,
        params={"project": str(project.id), "workspace": str(make_workspace().id)},
        headers=headers_for(user),
    )
    assert response.status_code == 404


def test_neither_parameter_is_a_400_that_says_what_is_missing(
    client: TestClient, user: User
) -> None:
    response = client.get(URL, headers=headers_for(user))
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "scope_required"


def test_a_non_member_gets_404_not_an_empty_permission_list(
    client: TestClient,
    make_user: Callable[..., User],
    make_workspace: Callable[..., Workspace],
    project: Project,
) -> None:
    outsider = make_user(workspace=make_workspace())
    response = client.get(URL, params={"project": str(project.id)}, headers=headers_for(outsider))
    assert response.status_code == 404


def test_unknown_ids_are_404_and_malformed_ids_are_422(client: TestClient, user: User) -> None:
    headers = headers_for(user)
    assert (
        client.get(URL, params={"project": str(uuid.uuid4())}, headers=headers).status_code == 404
    )
    assert client.get(URL, params={"workspace": "nope"}, headers=headers).status_code == 422


def test_needs_authentication(client: TestClient, project: Project) -> None:
    assert client.get(URL, params={"project": str(project.id)}).status_code == 401
