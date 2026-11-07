"""Custom roles and project-level roles (US-49, FR-78, FR-79)."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.permissions import PERMISSIONS, DefaultRole
from app.models import Project, User, Workspace
from app.services import join_codes as join_code_service
from app.services.membership import get_default_role
from tests.api.conftest import headers_for

CLIENT_REVIEWER = ["view", "message.post", "req.comment", "rcr.review"]


@pytest.fixture
def owner(make_user: Callable[..., User]) -> User:
    return make_user(role=DefaultRole.OWNER)


def roles_url(workspace: Workspace) -> str:
    return f"/api/v1/workspaces/{workspace.id}/roles"


def create(
    client: TestClient,
    workspace: Workspace,
    user: User,
    name: str = "Client reviewer",
    permissions: list[str] | None = None,
) -> Any:
    return client.post(
        roles_url(workspace),
        json={"name": name, "permissions": permissions or CLIENT_REVIEWER},
        headers=headers_for(user),
    )


def permissions_of(client: TestClient, user: User, **scope: str) -> dict[str, Any]:
    response = client.get("/api/v1/me/permissions", params=scope, headers=headers_for(user))
    assert response.status_code == 200, response.text
    return dict(response.json())


def test_the_catalogue_lists_every_permission_with_its_group(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    response = client.get("/api/v1/permissions", headers=headers_for(make_user(role=None)))

    assert response.status_code == 200
    assert {row["name"] for row in response.json()} == set(PERMISSIONS)
    assert {row["group"] for row in response.json()} == {
        "Workspace",
        "Requirements",
        "Review",
        "Governance",
    }


class TestCustomRoles:
    def test_a_client_reviewer_can_review_but_not_propose(
        self,
        client: TestClient,
        workspace: Workspace,
        owner: User,
        make_user: Callable[..., User],
    ) -> None:
        created = create(client, workspace, owner)
        assert created.status_code == 201
        assert created.json()["is_default"] is False
        member = make_user(role=DefaultRole.VIEWER)
        client.patch(
            f"/api/v1/workspaces/{workspace.id}/members/{member.id}",
            json={"role_id": created.json()["id"]},
            headers=headers_for(owner),
        )

        held = set(permissions_of(client, member, workspace=str(workspace.id))["permissions"])

        assert "rcr.review" in held and "req.comment" in held
        assert "req.propose" not in held and "rcr.open" not in held

    def test_it_is_listed_after_the_nine_defaults(
        self, client: TestClient, workspace: Workspace, owner: User
    ) -> None:
        create(client, workspace, owner)
        names = [
            r["name"] for r in client.get(roles_url(workspace), headers=headers_for(owner)).json()
        ]
        assert len(names) == 10 and names[-1] == "Client reviewer"

    def test_a_project_manager_cannot_create_roles(
        self, client: TestClient, workspace: Workspace, make_user: Callable[..., User]
    ) -> None:
        manager = make_user(role=DefaultRole.PROJECT_MANAGER)
        assert create(client, workspace, manager).status_code == 403

    def test_no_one_grants_what_they_do_not_hold(
        self, client: TestClient, workspace: Workspace, make_user: Callable[..., User]
    ) -> None:
        admin = make_user(role=DefaultRole.ADMIN)
        response = create(client, workspace, admin, permissions=["view", "protected.signoff"])
        assert response.status_code == 403

    def test_ownership_is_never_part_of_a_custom_role(
        self, client: TestClient, workspace: Workspace, owner: User
    ) -> None:
        response = create(client, workspace, owner, permissions=["workspace.manage"])
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "ownership_not_grantable"

    def test_unknown_permissions_are_rejected(
        self, client: TestClient, workspace: Workspace, owner: User
    ) -> None:
        response = create(client, workspace, owner, permissions=["view", "req.delete_everything"])
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "unknown_permission"

    @pytest.mark.parametrize("name", ["Owner", "developer"])
    def test_default_names_are_taken(
        self, client: TestClient, workspace: Workspace, owner: User, name: str
    ) -> None:
        assert create(client, workspace, owner, name=name).status_code == 409

    def test_names_are_unique_in_the_workspace(
        self, client: TestClient, workspace: Workspace, owner: User
    ) -> None:
        create(client, workspace, owner)
        assert create(client, workspace, owner).status_code == 409

    def test_a_blank_rename_is_rejected(
        self, client: TestClient, workspace: Workspace, owner: User
    ) -> None:
        role = create(client, workspace, owner).json()
        response = client.patch(
            f"/api/v1/roles/{role['id']}", json={"name": "   "}, headers=headers_for(owner)
        )
        assert response.status_code == 422

    def test_default_roles_cannot_be_edited_or_deleted(
        self, client: TestClient, db_session: Session, owner: User
    ) -> None:
        developer = get_default_role(db_session, DefaultRole.DEVELOPER)
        url = f"/api/v1/roles/{developer.id}"
        assert (
            client.patch(url, json={"name": "Dev"}, headers=headers_for(owner)).status_code == 404
        )
        assert client.delete(url, headers=headers_for(owner)).status_code == 404

    def test_an_edit_applies_on_the_members_next_request(
        self,
        client: TestClient,
        workspace: Workspace,
        owner: User,
        make_user: Callable[..., User],
    ) -> None:
        role = create(client, workspace, owner).json()
        reviewer = make_user(role=DefaultRole.VIEWER)
        client.patch(
            f"/api/v1/workspaces/{workspace.id}/members/{reviewer.id}",
            json={"role_id": role["id"]},
            headers=headers_for(owner),
        )

        edited = client.patch(
            f"/api/v1/roles/{role['id']}",
            json={"permissions": [*CLIENT_REVIEWER, "req.vote"]},
            headers=headers_for(owner),
        )

        assert edited.status_code == 200
        assert (
            "req.vote"
            in permissions_of(client, reviewer, workspace=str(workspace.id))["permissions"]
        )

    def test_a_role_in_use_is_deleted_only_after_reassignment(
        self,
        client: TestClient,
        db_session: Session,
        workspace: Workspace,
        owner: User,
        make_user: Callable[..., User],
    ) -> None:
        role = create(client, workspace, owner).json()
        member = make_user(role=DefaultRole.VIEWER)
        member_url = f"/api/v1/workspaces/{workspace.id}/members/{member.id}"
        client.patch(member_url, json={"role_id": role["id"]}, headers=headers_for(owner))

        blocked = client.delete(f"/api/v1/roles/{role['id']}", headers=headers_for(owner))
        assert blocked.status_code == 409
        assert blocked.json()["error"]["code"] == "role_in_use"

        viewer = str(get_default_role(db_session, DefaultRole.VIEWER).id)
        client.patch(member_url, json={"role_id": viewer}, headers=headers_for(owner))
        assert (
            client.delete(f"/api/v1/roles/{role['id']}", headers=headers_for(owner)).status_code
            == 204
        )

        listed = [
            r["id"] for r in client.get(roles_url(workspace), headers=headers_for(owner)).json()
        ]
        assert role["id"] not in listed
        reassign = client.patch(
            member_url, json={"role_id": role["id"]}, headers=headers_for(owner)
        )
        assert reassign.status_code == 404  # a deleted role is never assigned again
        assert create(client, workspace, owner).status_code == 201  # and its name is free

    def test_a_role_a_join_code_grants_cannot_gain_privileged_permissions(
        self, client: TestClient, db_session: Session, workspace: Workspace, owner: User
    ) -> None:
        role = create(client, workspace, owner).json()
        join_code_service.create_code(
            db_session,
            workspace_id=workspace.id,
            creator=owner,
            role_id=role["id"],
            expires_in_days=7,
        )

        response = client.patch(
            f"/api/v1/roles/{role['id']}",
            json={"permissions": [*CLIENT_REVIEWER, "roles.manage"]},
            headers=headers_for(owner),
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "role_granted_by_code"

    def test_another_workspaces_role_is_a_404(
        self,
        client: TestClient,
        workspace: Workspace,
        owner: User,
        make_user: Callable[..., User],
        make_workspace: Callable[..., Workspace],
    ) -> None:
        role = create(client, workspace, owner).json()
        stranger = make_user(role=DefaultRole.OWNER, workspace=make_workspace())
        response = client.delete(f"/api/v1/roles/{role['id']}", headers=headers_for(stranger))
        assert response.status_code == 404


class TestProjectRoles:
    def team_url(self, project: Project, user: User) -> str:
        return f"/api/v1/projects/{project.id}/members/{user.id}"

    def test_a_pm_sets_a_project_level_role(
        self,
        client: TestClient,
        db_session: Session,
        workspace: Workspace,
        project: Project,
        make_user: Callable[..., User],
    ) -> None:
        manager, developer = (
            make_user(role=DefaultRole.PROJECT_MANAGER),
            make_user(role=DefaultRole.DEVELOPER),
        )
        viewer = str(get_default_role(db_session, DefaultRole.VIEWER).id)

        response = client.put(
            self.team_url(project, developer),
            json={"role_override_id": viewer},
            headers=headers_for(manager),
        )

        assert response.status_code == 200
        assert response.json()["role_override"]["name"] == "Viewer"
        assert (
            permissions_of(client, developer, project=str(project.id))["role"]["name"] == "Viewer"
        )
        assert (
            permissions_of(client, developer, workspace=str(workspace.id))["role"]["name"]
            == "Developer"
        )
        team = client.get(f"/api/v1/projects/{project.id}/members", headers=headers_for(developer))
        assert [m["user_id"] for m in team.json()] == [str(developer.id)]

        cleared = client.put(
            self.team_url(project, developer),
            json={"role_override_id": None},
            headers=headers_for(manager),
        )
        assert cleared.json()["role_override"] is None
        assert (
            permissions_of(client, developer, project=str(project.id))["role"]["name"]
            == "Developer"
        )

    def test_never_more_than_the_pm_holds(
        self,
        client: TestClient,
        db_session: Session,
        project: Project,
        make_user: Callable[..., User],
    ) -> None:
        manager, developer = (
            make_user(role=DefaultRole.PROJECT_MANAGER),
            make_user(role=DefaultRole.DEVELOPER),
        )
        for role in (DefaultRole.ADMIN, DefaultRole.COMPLIANCE_REVIEWER):
            response = client.put(
                self.team_url(project, developer),
                json={"role_override_id": str(get_default_role(db_session, role).id)},
                headers=headers_for(manager),
            )
            assert response.status_code == 403, role

    def test_ownership_is_never_per_project(
        self,
        client: TestClient,
        db_session: Session,
        project: Project,
        owner: User,
        make_user: Callable[..., User],
    ) -> None:
        developer = make_user(role=DefaultRole.DEVELOPER)
        response = client.put(
            self.team_url(project, developer),
            json={"role_override_id": str(get_default_role(db_session, DefaultRole.OWNER).id)},
            headers=headers_for(owner),
        )
        assert response.status_code == 409

    def test_someone_outside_the_workspace_cannot_join_the_team(
        self,
        client: TestClient,
        project: Project,
        owner: User,
        make_user: Callable[..., User],
    ) -> None:
        outsider = make_user(role=None)
        response = client.put(self.team_url(project, outsider), json={}, headers=headers_for(owner))
        assert response.status_code == 404
