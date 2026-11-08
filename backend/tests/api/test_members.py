"""Members (US-26, FR-45, FR-49, NFR-27): list, change role, remove, leave, needs reassignment."""

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.websockets import WebSocketDisconnect

from app.core import security
from app.core.permissions import DefaultRole
from app.models import (
    AuditAction,
    AuditLog,
    Channel,
    ChannelMember,
    Membership,
    Message,
    Project,
    ProjectMember,
    Requirement,
    User,
    Workspace,
)
from app.realtime import bus, gateway
from app.realtime.events import MEMBERSHIP_REVOKED
from app.services.membership import get_default_role
from tests.api.conftest import headers_for


@pytest.fixture
def events(monkeypatch: pytest.MonkeyPatch) -> Iterator[bus.InProcessEventBus]:
    test_bus = bus.InProcessEventBus()
    monkeypatch.setattr(bus, "get_bus", lambda: test_bus)
    monkeypatch.setattr(gateway, "make_fanout", lambda: gateway.MemoryFanout(test_bus))
    yield test_bus


@pytest.fixture
def owner(make_user: Callable[..., User]) -> User:
    return make_user(role=DefaultRole.OWNER)


def members_url(workspace: Workspace, user: User | None = None) -> str:
    base = f"/api/v1/workspaces/{workspace.id}/members"
    return f"{base}/{user.id}" if user else base


def role_id(db: Session, role: DefaultRole) -> str:
    return str(get_default_role(db, role).id)


def my_role(client: TestClient, workspace: Workspace, user: User) -> str:
    response = client.get(
        "/api/v1/me/permissions", params={"workspace": str(workspace.id)}, headers=headers_for(user)
    )
    assert response.status_code == 200, response.text
    return str(response.json()["role"]["name"])


class TestList:
    def test_every_member_sees_the_member_list(
        self, client: TestClient, workspace: Workspace, owner: User, make_user: Callable[..., User]
    ) -> None:
        viewer = make_user(role=DefaultRole.VIEWER)
        response = client.get(members_url(workspace), headers=headers_for(viewer))

        assert response.status_code == 200
        rows = {row["user"]["id"]: row["role"]["name"] for row in response.json()}
        assert rows == {str(owner.id): "Owner", str(viewer.id): "Viewer"}

    def test_another_workspace_is_a_404(
        self,
        client: TestClient,
        owner: User,
        make_workspace: Callable[..., Workspace],
    ) -> None:
        other = make_workspace()
        assert client.get(members_url(other), headers=headers_for(owner)).status_code == 404


class TestChangeRole:
    def test_an_owner_changes_a_role_and_it_applies_on_the_next_request(
        self,
        client: TestClient,
        db_session: Session,
        workspace: Workspace,
        owner: User,
        make_user: Callable[..., User],
    ) -> None:
        developer = make_user(role=DefaultRole.DEVELOPER)

        response = client.patch(
            members_url(workspace, developer),
            json={"role_id": role_id(db_session, DefaultRole.QA_ENGINEER)},
            headers=headers_for(owner),
        )

        assert response.status_code == 200
        assert response.json()["role"]["name"] == "QA Engineer"
        assert my_role(client, workspace, developer) == "QA Engineer"
        (row,) = db_session.scalars(
            select(AuditLog).where(AuditLog.action == AuditAction.MEMBER_ROLE_CHANGED)
        )
        assert set(row.details or {}) == {"user_id", "from_role_id", "to_role_id"}

    def test_a_project_manager_cannot_hand_out_admin(
        self,
        client: TestClient,
        db_session: Session,
        workspace: Workspace,
        make_user: Callable[..., User],
    ) -> None:
        manager, developer = make_user(role=DefaultRole.PROJECT_MANAGER), make_user()
        response = client.patch(
            members_url(workspace, developer),
            json={"role_id": role_id(db_session, DefaultRole.ADMIN)},
            headers=headers_for(manager),
        )
        assert response.status_code == 403

    def test_a_project_manager_cannot_demote_an_admin(
        self,
        client: TestClient,
        db_session: Session,
        workspace: Workspace,
        make_user: Callable[..., User],
    ) -> None:
        manager, admin = (
            make_user(role=DefaultRole.PROJECT_MANAGER),
            make_user(role=DefaultRole.ADMIN),
        )
        response = client.patch(
            members_url(workspace, admin),
            json={"role_id": role_id(db_session, DefaultRole.VIEWER)},
            headers=headers_for(manager),
        )
        assert response.status_code == 403
        assert my_role(client, workspace, admin) == "Admin"

    def test_only_an_owner_makes_owners(
        self,
        client: TestClient,
        db_session: Session,
        workspace: Workspace,
        owner: User,
        make_user: Callable[..., User],
    ) -> None:
        admin, developer = make_user(role=DefaultRole.ADMIN), make_user()
        body = {"role_id": role_id(db_session, DefaultRole.OWNER)}

        refused = client.patch(
            members_url(workspace, developer), json=body, headers=headers_for(admin)
        )
        allowed = client.patch(
            members_url(workspace, developer), json=body, headers=headers_for(owner)
        )

        assert (refused.status_code, allowed.status_code) == (403, 200)

    def test_the_last_owner_keeps_the_owner_role(
        self,
        client: TestClient,
        db_session: Session,
        workspace: Workspace,
        owner: User,
        make_user: Callable[..., User],
    ) -> None:
        demote = {"role_id": role_id(db_session, DefaultRole.ADMIN)}
        response = client.patch(
            members_url(workspace, owner), json=demote, headers=headers_for(owner)
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "last_owner"

        make_user(role=DefaultRole.OWNER)  # a second owner makes it possible
        again = client.patch(members_url(workspace, owner), json=demote, headers=headers_for(owner))
        assert again.status_code == 200

    def test_a_role_of_another_workspace_is_a_404(
        self,
        client: TestClient,
        workspace: Workspace,
        owner: User,
        make_user: Callable[..., User],
    ) -> None:
        developer = make_user()
        response = client.patch(
            members_url(workspace, developer),
            json={"role_id": "00000000-0000-0000-0000-000000000000"},
            headers=headers_for(owner),
        )
        assert response.status_code == 404


class TestRemove:
    def test_removal_ends_access_keeps_content_and_is_announced(
        self,
        client: TestClient,
        db_session: Session,
        workspace: Workspace,
        project: Project,
        owner: User,
        make_user: Callable[..., User],
        events: bus.InProcessEventBus,
    ) -> None:
        developer = make_user()
        channel = Channel(project_id=project.id, name="team", is_private=True)
        db_session.add(channel)
        db_session.flush()
        db_session.add_all(
            [
                ProjectMember(project_id=project.id, user_id=developer.id),
                ChannelMember(channel_id=channel.id, user_id=developer.id),
                Message(channel_id=channel.id, author_id=developer.id, body="my words"),
            ]
        )
        db_session.commit()

        response = client.delete(members_url(workspace, developer), headers=headers_for(owner))

        assert response.status_code == 204
        later = client.get(f"/api/v1/projects/{project.id}", headers=headers_for(developer))
        assert later.status_code == 404  # the very next request
        assert db_session.get(ProjectMember, (project.id, developer.id)) is None
        assert db_session.get(ChannelMember, (channel.id, developer.id)) is None
        assert (
            db_session.scalar(select(Message.body).where(Message.author_id == developer.id))
            == "my words"
        )
        history = db_session.scalar(select(Membership).where(Membership.user_id == developer.id))
        assert history is not None and history.ended_at is not None
        (event,) = [e for e in events.published if e.type == MEMBERSHIP_REVOKED]
        assert event.data == {"user_id": str(developer.id)}

    def test_the_removed_members_socket_closes(
        self,
        client: TestClient,
        workspace: Workspace,
        project: Project,
        owner: User,
        make_user: Callable[..., User],
        events: bus.InProcessEventBus,
    ) -> None:
        developer = make_user()
        with client.websocket_connect("/ws") as socket:
            socket.send_json(
                {"type": "auth", "token": security.create_access_token(developer.id)[0]}
            )
            assert socket.receive_json()["type"] == "ready"
            socket.send_json({"type": "subscribe", "project_id": str(project.id)})
            assert socket.receive_json()["type"] == "subscribed"

            assert (
                client.delete(
                    members_url(workspace, developer), headers=headers_for(owner)
                ).status_code
                == 204
            )

            with pytest.raises(WebSocketDisconnect) as closed:
                socket.receive_json()
        assert closed.value.code == gateway.CLOSE_REVOKED

    def test_you_cannot_remove_yourself(
        self, client: TestClient, workspace: Workspace, owner: User, make_user: Callable[..., User]
    ) -> None:
        make_user(role=DefaultRole.OWNER)
        response = client.delete(members_url(workspace, owner), headers=headers_for(owner))
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "use_leave"

    def test_without_members_manage_it_is_403(
        self, client: TestClient, workspace: Workspace, make_user: Callable[..., User]
    ) -> None:
        analyst, developer = make_user(), make_user(role=DefaultRole.DEVELOPER)
        response = client.delete(members_url(workspace, developer), headers=headers_for(analyst))
        assert response.status_code == 403

    def test_a_non_member_target_is_a_404(
        self,
        client: TestClient,
        workspace: Workspace,
        owner: User,
        make_user: Callable[..., User],
    ) -> None:
        outsider = make_user(role=None)
        response = client.delete(members_url(workspace, outsider), headers=headers_for(owner))
        assert response.status_code == 404


class TestLeave:
    def test_a_member_leaves(
        self, client: TestClient, workspace: Workspace, owner: User, make_user: Callable[..., User]
    ) -> None:
        developer = make_user()
        url = f"/api/v1/workspaces/{workspace.id}/leave"

        assert client.post(url, headers=headers_for(developer)).status_code == 204
        assert client.post(url, headers=headers_for(developer)).status_code == 404  # gone now

    def test_the_last_owner_cannot_leave(
        self, client: TestClient, workspace: Workspace, owner: User
    ) -> None:
        response = client.post(
            f"/api/v1/workspaces/{workspace.id}/leave", headers=headers_for(owner)
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "last_owner"


def test_requirements_of_former_members_need_reassignment(
    client: TestClient,
    workspace: Workspace,
    owner: User,
    make_user: Callable[..., User],
    make_requirement: Callable[..., Requirement],
) -> None:
    leaver, stayer = make_user(), make_user()
    orphaned = make_requirement(source_req_id="REQ-007", owner_id=leaver.id)
    make_requirement(source_req_id="REQ-008", owner_id=stayer.id)
    client.post(f"/api/v1/workspaces/{workspace.id}/leave", headers=headers_for(leaver))

    response = client.get(
        f"/api/v1/workspaces/{workspace.id}/needs-reassignment", headers=headers_for(owner)
    )

    assert response.status_code == 200
    assert [(r["id"], r["label"], r["former_owner_id"]) for r in response.json()] == [
        (str(orphaned.id), "REQ-007", str(leaver.id))
    ]
