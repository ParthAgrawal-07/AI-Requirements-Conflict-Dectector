"""Workspaces (US-24, FR-43, FR-46): creation, listing, renaming."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.permissions import DEFAULT_ROLE_PERMISSIONS, DefaultRole
from app.models import AuditAction, AuditLog, Membership, PlatformRole, User, Workspace
from tests.api.conftest import headers_for

WORKSPACES = "/api/v1/workspaces"


@pytest.fixture
def platform_admin(make_user: Callable[..., User]) -> User:
    return make_user(role=None, platform_role=PlatformRole.PLATFORM_ADMIN)


class TestCreate:
    def test_a_platform_admin_creates_a_workspace_and_becomes_its_owner(
        self, client: TestClient, platform_admin: User, db_session: Session
    ) -> None:
        response = client.post(
            WORKSPACES, json={"name": "Acme"}, headers=headers_for(platform_admin)
        )

        assert response.status_code == 201
        created = response.json()
        assert created["name"] == "Acme"

        # the creator is the Owner, and an Owner may do everything but compliance sign-off
        me = client.get(
            "/api/v1/me/permissions",
            params={"workspace": created["id"]},
            headers=headers_for(platform_admin),
        )
        assert me.status_code == 200
        assert me.json()["role"]["name"] == "Owner"
        assert set(me.json()["permissions"]) == DEFAULT_ROLE_PERMISSIONS[DefaultRole.OWNER]

    def test_the_creation_is_audited_with_identifiers_only(
        self, client: TestClient, platform_admin: User, db_session: Session
    ) -> None:
        workspace_id = client.post(
            WORKSPACES, json={"name": "Audited"}, headers=headers_for(platform_admin)
        ).json()["id"]

        actions = {
            row.action: row
            for row in db_session.scalars(
                select(AuditLog).where(AuditLog.workspace_id == workspace_id)
            )
        }
        assert set(actions) == {AuditAction.WORKSPACE_CREATED, AuditAction.MEMBER_ADDED}
        assert all(row.actor_id == platform_admin.id for row in actions.values())
        assert "Audited" not in str([row.details for row in actions.values()])

    def test_an_ordinary_user_may_not_create_workspaces_by_default(
        self, client: TestClient, user: User
    ) -> None:
        response = client.post(WORKSPACES, json={"name": "Mine"}, headers=headers_for(user))
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden"

    def test_any_user_may_when_the_deployment_allows_it(
        self, client: TestClient, user: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(get_settings(), "allow_user_workspace_creation", True)
        response = client.post(WORKSPACES, json={"name": "Mine"}, headers=headers_for(user))
        assert response.status_code == 201

    def test_a_user_can_belong_to_several_workspaces(
        self, client: TestClient, user: User, workspace: Workspace, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(get_settings(), "allow_user_workspace_creation", True)
        client.post(WORKSPACES, json={"name": "Second"}, headers=headers_for(user))

        listed = client.get(WORKSPACES, headers=headers_for(user)).json()

        assert {(w["name"], w["role"]["name"]) for w in listed} == {
            (workspace.name, "Business Analyst"),
            ("Second", "Owner"),
        }

    def test_names_are_not_unique_so_creating_one_never_reveals_another_tenant(
        self,
        client: TestClient,
        platform_admin: User,
        workspace: Workspace,
        db_session: Session,
    ) -> None:
        """A 409 on a taken name would tell this caller that someone else's workspace has it."""
        response = client.post(
            WORKSPACES, json={"name": workspace.name}, headers=headers_for(platform_admin)
        )
        assert response.status_code == 201
        assert response.json()["id"] != str(workspace.id)
        same_name = db_session.scalars(
            select(Workspace).where(Workspace.name == workspace.name)
        ).all()
        assert len(same_name) == 2

    @pytest.mark.parametrize("name", ["", "   ", "x" * 121])
    def test_invalid_names_are_422(
        self, client: TestClient, platform_admin: User, name: str
    ) -> None:
        assert (
            client.post(
                WORKSPACES, json={"name": name}, headers=headers_for(platform_admin)
            ).status_code
            == 422
        )

    def test_needs_authentication(self, client: TestClient) -> None:
        assert client.post(WORKSPACES, json={"name": "X"}).status_code == 401
        assert client.get(WORKSPACES).status_code == 401

    def test_the_name_is_trimmed(self, client: TestClient, platform_admin: User) -> None:
        response = client.post(
            WORKSPACES, json={"name": "  Padded  "}, headers=headers_for(platform_admin)
        )
        assert response.json()["name"] == "Padded"


class TestListAndGet:
    def test_lists_only_the_callers_workspaces(
        self,
        client: TestClient,
        user: User,
        workspace: Workspace,
        make_workspace: Callable[..., Workspace],
    ) -> None:
        make_workspace("Not mine")
        listed = client.get(WORKSPACES, headers=headers_for(user)).json()
        assert [w["id"] for w in listed] == [str(workspace.id)]
        assert listed[0]["role"]["name"] == "Business Analyst"

    def test_a_removed_membership_disappears_from_the_list(
        self, client: TestClient, user: User, db_session: Session
    ) -> None:
        from datetime import UTC, datetime

        membership = db_session.scalars(
            select(Membership).where(Membership.user_id == user.id)
        ).one()
        membership.ended_at = datetime.now(UTC)
        db_session.commit()
        assert client.get(WORKSPACES, headers=headers_for(user)).json() == []

    def test_a_member_can_read_their_workspace(
        self, client: TestClient, user: User, workspace: Workspace
    ) -> None:
        response = client.get(f"{WORKSPACES}/{workspace.id}", headers=headers_for(user))
        assert response.status_code == 200 and response.json()["name"] == workspace.name

    def test_another_workspace_is_404(
        self, client: TestClient, user: User, make_workspace: Callable[..., Workspace]
    ) -> None:
        other = make_workspace()
        assert client.get(f"{WORKSPACES}/{other.id}", headers=headers_for(user)).status_code == 404


class TestRename:
    def test_the_owner_renames(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        workspace: Workspace,
        db_session: Session,
    ) -> None:
        owner = make_user(role=DefaultRole.OWNER)
        response = client.patch(
            f"{WORKSPACES}/{workspace.id}", json={"name": "Renamed"}, headers=headers_for(owner)
        )
        assert response.status_code == 200 and response.json()["name"] == "Renamed"
        audit = db_session.scalars(
            select(AuditLog).where(AuditLog.action == AuditAction.WORKSPACE_UPDATED)
        ).one()
        assert audit.details == {"changed": ["name"]}

    @pytest.mark.parametrize("role", [r for r in DefaultRole if r is not DefaultRole.OWNER])
    def test_nobody_else_holds_workspace_manage(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        workspace: Workspace,
        role: DefaultRole,
    ) -> None:
        response = client.patch(
            f"{WORKSPACES}/{workspace.id}",
            json={"name": "Hijacked"},
            headers=headers_for(make_user(role=role)),
        )
        assert response.status_code == 403

    def test_renaming_to_another_workspaces_name_is_allowed_and_reveals_nothing(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        workspace: Workspace,
        make_workspace: Callable[..., Workspace],
    ) -> None:
        other = make_workspace("Somebody else's name")
        owner = make_user(role=DefaultRole.OWNER)
        response = client.patch(
            f"{WORKSPACES}/{workspace.id}", json={"name": other.name}, headers=headers_for(owner)
        )
        assert response.status_code == 200 and response.json()["name"] == other.name

    def test_renaming_to_the_same_name_is_a_harmless_no_op(
        self, client: TestClient, make_user: Callable[..., User], workspace: Workspace
    ) -> None:
        owner = make_user(role=DefaultRole.OWNER)
        response = client.patch(
            f"{WORKSPACES}/{workspace.id}",
            json={"name": workspace.name},
            headers=headers_for(owner),
        )
        assert response.status_code == 200

    def test_another_workspace_is_404_even_for_an_owner_elsewhere(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        make_workspace: Callable[..., Workspace],
        workspace: Workspace,
    ) -> None:
        elsewhere = make_user(role=DefaultRole.OWNER, workspace=make_workspace())
        response = client.patch(
            f"{WORKSPACES}/{workspace.id}", json={"name": "X"}, headers=headers_for(elsewhere)
        )
        assert response.status_code == 404
