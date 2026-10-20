"""Projects (US-24, FR-47, FR-103): create in Setup, list, read, edit settings."""

import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import DefaultRole, holders_of
from app.models import AuditAction, AuditLog, Project, ProjectMember, ProjectStatus, User, Workspace
from tests.api.conftest import headers_for


def projects_url(workspace: Workspace) -> str:
    return f"/api/v1/workspaces/{workspace.id}/projects"


def project_url(project: Project) -> str:
    return f"/api/v1/projects/{project.id}"


@pytest.fixture
def manager(make_user: Callable[..., User]) -> User:
    return make_user(role=DefaultRole.PROJECT_MANAGER)


class TestCreate:
    def test_a_new_project_starts_in_setup_with_analysis_disabled(
        self, client: TestClient, manager: User, workspace: Workspace
    ) -> None:
        response = client.post(
            projects_url(workspace), json={"name": "Payments SRS"}, headers=headers_for(manager)
        )

        assert response.status_code == 201
        project = response.json()
        assert response.headers["Location"] == f"/api/v1/projects/{project['id']}"
        assert project["status"] == "setup"
        assert project["analysis_enabled"] is False  # FR-103: nothing is analysed before context
        assert project["context_version"] == 0
        assert project["workspace_id"] == str(workspace.id)
        assert project["description"] is None
        # the defaults of FR-47
        assert (project["similarity_threshold"], project["confidence_threshold"]) == (0.75, 0.5)
        assert project["llm_budget_monthly_calls"] == 2000
        assert project["required_approvals"] == 1
        assert project["chat_detection_enabled"] is False

    def test_settings_can_be_set_at_creation(
        self, client: TestClient, manager: User, workspace: Workspace
    ) -> None:
        response = client.post(
            projects_url(workspace),
            json={
                "name": "Tuned",
                "description": "Core banking",
                "similarity_threshold": 0.9,
                "confidence_threshold": 0.6,
                "llm_budget_monthly_calls": 500,
                "required_approvals": 2,
                "chat_detection_enabled": True,
            },
            headers=headers_for(manager),
        )
        assert response.status_code == 201
        project = response.json()
        assert project["description"] == "Core banking"
        assert (project["similarity_threshold"], project["required_approvals"]) == (0.9, 2)
        assert (
            project["llm_budget_monthly_calls"] == 500 and project["chat_detection_enabled"] is True
        )

    def test_the_creator_joins_the_project_team_and_the_creation_is_audited(
        self, client: TestClient, manager: User, workspace: Workspace, db_session: Session
    ) -> None:
        project_id = client.post(
            projects_url(workspace), json={"name": "Team"}, headers=headers_for(manager)
        ).json()["id"]

        member = db_session.get(ProjectMember, (uuid.UUID(project_id), manager.id))
        assert member is not None and member.role_override_id is None
        created_by = db_session.get(Project, uuid.UUID(project_id)).created_by  # type: ignore[union-attr]
        assert created_by == manager.id
        audit = db_session.scalars(
            select(AuditLog).where(AuditLog.action == AuditAction.PROJECT_CREATED)
        ).one()
        assert audit.details == {"project_id": project_id} and audit.actor_id == manager.id

    @pytest.mark.parametrize("role", holders_of("project.manage"))
    def test_roles_holding_project_manage_may_create(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        workspace: Workspace,
        role: DefaultRole,
    ) -> None:
        response = client.post(
            projects_url(workspace),
            json={"name": f"By {role.value}"},
            headers=headers_for(make_user(role=role)),
        )
        assert response.status_code == 201

    @pytest.mark.parametrize(
        "role", [r for r in DefaultRole if r not in holders_of("project.manage")]
    )
    def test_other_roles_get_403_and_create_nothing(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        workspace: Workspace,
        db_session: Session,
        role: DefaultRole,
    ) -> None:
        response = client.post(
            projects_url(workspace),
            json={"name": "Nope"},
            headers=headers_for(make_user(role=role)),
        )
        assert response.status_code == 403
        assert db_session.scalars(select(Project).where(Project.name == "Nope")).all() == []

    def test_another_workspace_is_404(
        self, client: TestClient, manager: User, make_workspace: Callable[..., Workspace]
    ) -> None:
        response = client.post(
            projects_url(make_workspace()), json={"name": "Sneaky"}, headers=headers_for(manager)
        )
        assert response.status_code == 404

    def test_a_duplicate_name_in_the_workspace_is_409_but_fine_in_another(
        self,
        client: TestClient,
        manager: User,
        workspace: Workspace,
        project: Project,
        make_user: Callable[..., User],
        make_workspace: Callable[..., Workspace],
    ) -> None:
        clash = client.post(
            projects_url(workspace), json={"name": project.name}, headers=headers_for(manager)
        )
        assert clash.status_code == 409 and clash.json()["error"]["code"] == "conflict"

        other = make_workspace()
        other_manager = make_user(role=DefaultRole.PROJECT_MANAGER, workspace=other)
        fine = client.post(
            projects_url(other), json={"name": project.name}, headers=headers_for(other_manager)
        )
        assert fine.status_code == 201

    @pytest.mark.parametrize(
        "payload",
        [
            {"name": ""},
            {"name": "   "},
            {"name": "x" * 121},
            {"name": "P", "similarity_threshold": 1.5},
            {"name": "P", "confidence_threshold": -0.1},
            {"name": "P", "llm_budget_monthly_calls": -1},
            {"name": "P", "required_approvals": 0},
            {"name": "P", "required_approvals": 4},
            {"name": "P", "description": "d" * 2001},
            {"name": "P", "status": "active"},  # cannot skip the context requirement
            {"name": "P", "context_version": 3},
            {"name": "P", "workspace_id": str(uuid.uuid4())},
        ],
    )
    def test_invalid_input_is_a_422(
        self, client: TestClient, manager: User, workspace: Workspace, payload: dict[str, object]
    ) -> None:
        assert (
            client.post(
                projects_url(workspace), json=payload, headers=headers_for(manager)
            ).status_code
            == 422
        )

    def test_needs_authentication(self, client: TestClient, workspace: Workspace) -> None:
        assert client.post(projects_url(workspace), json={"name": "X"}).status_code == 401


class TestNamesAreTrimmed:
    """create and update must store the same form, or "Foo" and " Foo" could coexist."""

    def test_create_trims(self, client: TestClient, manager: User, workspace: Workspace) -> None:
        response = client.post(
            projects_url(workspace), json={"name": "  Padded  "}, headers=headers_for(manager)
        )
        assert response.json()["name"] == "Padded"

    def test_update_trims_too(self, client: TestClient, manager: User, project: Project) -> None:
        response = client.patch(
            project_url(project), json={"name": "  Renamed  "}, headers=headers_for(manager)
        )
        assert response.status_code == 200 and response.json()["name"] == "Renamed"

    def test_a_padded_name_cannot_duplicate_an_existing_one(
        self,
        client: TestClient,
        manager: User,
        project: Project,
        make_project: Callable[..., Project],
    ) -> None:
        other = make_project(name="Foo")
        headers = headers_for(manager)
        assert (
            client.patch(project_url(project), json={"name": " Foo "}, headers=headers).status_code
            == 409
        )
        assert (
            client.post(
                projects_url(other.workspace), json={"name": " Foo"}, headers=headers
            ).status_code
            == 409
        )

    def test_renaming_to_the_same_name_with_padding_is_a_no_op(
        self, client: TestClient, manager: User, project: Project, db_session: Session
    ) -> None:
        response = client.patch(
            project_url(project), json={"name": f"  {project.name}  "}, headers=headers_for(manager)
        )
        assert response.status_code == 200
        assert (
            db_session.scalars(
                select(AuditLog).where(AuditLog.action == AuditAction.PROJECT_UPDATED)
            ).all()
            == []
        )


class TestListAndGet:
    @pytest.mark.parametrize("role", list(DefaultRole))
    def test_every_member_may_list_and_read(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        workspace: Workspace,
        project: Project,
        role: DefaultRole,
    ) -> None:
        headers = headers_for(make_user(role=role))
        listed = client.get(projects_url(workspace), headers=headers)
        assert listed.status_code == 200 and listed.json()["items"][0]["id"] == str(project.id)
        assert client.get(project_url(project), headers=headers).json()["name"] == project.name

    def test_only_this_workspaces_projects_and_archived_ones_are_hidden_by_default(
        self,
        client: TestClient,
        user: User,
        workspace: Workspace,
        project: Project,
        make_project: Callable[..., Project],
        make_workspace: Callable[..., Workspace],
    ) -> None:
        make_project(workspace=make_workspace(), name="Elsewhere")
        archived = make_project(name="Old", status=ProjectStatus.ARCHIVED)
        setup = make_project(name="Fresh", status=ProjectStatus.SETUP)
        headers = headers_for(user)

        names = {
            p["name"] for p in client.get(projects_url(workspace), headers=headers).json()["items"]
        }
        with_archived = client.get(
            projects_url(workspace), params={"include_archived": "true"}, headers=headers
        ).json()

        assert names == {project.name, setup.name}
        assert archived.name in {p["name"] for p in with_archived["items"]}
        assert with_archived["total"] == 3

    def test_pagination(
        self,
        client: TestClient,
        user: User,
        workspace: Workspace,
        make_project: Callable[..., Project],
    ) -> None:
        for i in range(5):
            make_project(name=f"P{i}")
        page = client.get(
            projects_url(workspace), params={"limit": 2, "offset": 2}, headers=headers_for(user)
        ).json()
        assert len(page["items"]) == 2 and page["total"] == 5 and page["offset"] == 2

    @pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}])
    def test_bad_paging_is_422(
        self, client: TestClient, user: User, workspace: Workspace, params: dict[str, int]
    ) -> None:
        assert (
            client.get(
                projects_url(workspace), params=params, headers=headers_for(user)
            ).status_code
            == 422
        )

    def test_another_workspaces_project_and_list_are_404(
        self,
        client: TestClient,
        user: User,
        make_project: Callable[..., Project],
        make_workspace: Callable[..., Workspace],
    ) -> None:
        other_workspace = make_workspace()
        theirs = make_project(workspace=other_workspace)
        headers = headers_for(user)
        assert client.get(project_url(theirs), headers=headers).status_code == 404
        assert client.get(projects_url(other_workspace), headers=headers).status_code == 404

    def test_unknown_project_is_404_and_malformed_id_is_422(
        self, client: TestClient, user: User
    ) -> None:
        headers = headers_for(user)
        assert client.get(f"/api/v1/projects/{uuid.uuid4()}", headers=headers).status_code == 404
        assert client.get("/api/v1/projects/nope", headers=headers).status_code == 422


class TestUpdate:
    def test_a_manager_edits_settings_and_the_change_is_audited(
        self, client: TestClient, manager: User, project: Project, db_session: Session
    ) -> None:
        response = client.patch(
            project_url(project),
            json={"similarity_threshold": 0.8, "required_approvals": 3, "name": "Renamed"},
            headers=headers_for(manager),
        )
        assert response.status_code == 200
        body = response.json()
        assert (body["similarity_threshold"], body["required_approvals"], body["name"]) == (
            0.8,
            3,
            "Renamed",
        )
        assert body["status"] == "active"  # unchanged: PATCH never touches the status
        audit = db_session.scalars(
            select(AuditLog).where(AuditLog.action == AuditAction.PROJECT_UPDATED)
        ).one()
        assert audit.details == {
            "project_id": str(project.id),
            "changed": ["name", "required_approvals", "similarity_threshold"],
        }
        assert "Renamed" not in str(audit.details)  # names of things are not audit payload

    def test_a_partial_update_leaves_other_fields_alone(
        self, client: TestClient, manager: User, project: Project
    ) -> None:
        body = client.patch(
            project_url(project),
            json={"chat_detection_enabled": True},
            headers=headers_for(manager),
        ).json()
        assert body["chat_detection_enabled"] is True and body["name"] == project.name

    def test_description_can_be_cleared_with_null_but_other_fields_cannot(
        self, client: TestClient, manager: User, project: Project, db_session: Session
    ) -> None:
        project.description = "old"
        db_session.commit()
        headers = headers_for(manager)
        assert (
            client.patch(project_url(project), json={"description": None}, headers=headers).json()[
                "description"
            ]
            is None
        )
        for field in (
            "name",
            "similarity_threshold",
            "required_approvals",
            "chat_detection_enabled",
        ):
            assert (
                client.patch(project_url(project), json={field: None}, headers=headers).status_code
                == 422
            ), field

    def test_an_empty_or_unchanged_patch_changes_and_audits_nothing(
        self, client: TestClient, manager: User, project: Project, db_session: Session
    ) -> None:
        headers = headers_for(manager)
        assert client.patch(project_url(project), json={}, headers=headers).status_code == 200
        assert (
            client.patch(
                project_url(project), json={"name": project.name}, headers=headers
            ).status_code
            == 200
        )
        assert (
            db_session.scalars(
                select(AuditLog).where(AuditLog.action == AuditAction.PROJECT_UPDATED)
            ).all()
            == []
        )

    @pytest.mark.parametrize("field", ["status", "context_version", "workspace_id", "id"])
    def test_the_status_cannot_be_set_through_patch(
        self, client: TestClient, manager: User, project: Project, field: str
    ) -> None:
        response = client.patch(
            project_url(project), json={field: "active"}, headers=headers_for(manager)
        )
        assert response.status_code == 422

    def test_renaming_onto_another_project_is_409(
        self,
        client: TestClient,
        manager: User,
        project: Project,
        make_project: Callable[..., Project],
    ) -> None:
        other = make_project(name="Other")
        response = client.patch(
            project_url(project), json={"name": other.name}, headers=headers_for(manager)
        )
        assert response.status_code == 409

    @pytest.mark.parametrize(
        "role", [r for r in DefaultRole if r not in holders_of("project.manage")]
    )
    def test_other_roles_get_403(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        project: Project,
        role: DefaultRole,
    ) -> None:
        response = client.patch(
            project_url(project), json={"name": "Hijack"}, headers=headers_for(make_user(role=role))
        )
        assert response.status_code == 403

    def test_another_workspaces_project_is_404(
        self,
        client: TestClient,
        manager: User,
        make_project: Callable[..., Project],
        make_workspace: Callable[..., Workspace],
    ) -> None:
        theirs = make_project(workspace=make_workspace())
        assert (
            client.patch(
                project_url(theirs), json={"name": "X"}, headers=headers_for(manager)
            ).status_code
            == 404
        )

    @pytest.mark.parametrize(
        "payload",
        [
            {"similarity_threshold": 2},
            {"required_approvals": 9},
            {"llm_budget_monthly_calls": -5},
            {"name": " "},
        ],
    )
    def test_invalid_values_are_422(
        self, client: TestClient, manager: User, project: Project, payload: dict[str, object]
    ) -> None:
        assert (
            client.patch(
                project_url(project), json=payload, headers=headers_for(manager)
            ).status_code
            == 422
        )
