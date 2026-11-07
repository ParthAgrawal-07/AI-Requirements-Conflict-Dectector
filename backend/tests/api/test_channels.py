"""Channels (US-28, FR-50): create, list with unread counts, rename, archive, private members."""

import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import DefaultRole
from app.models import AuditLog, Channel, Message, Project, User, Workspace
from app.realtime import bus
from app.realtime.events import CHANNEL_CREATED, CHANNEL_MEMBER_REMOVED, CHANNEL_UPDATED
from tests.api.conftest import headers_for


def channels_url(project: Project) -> str:
    return f"/api/v1/projects/{project.id}/channels"


@pytest.fixture
def events(monkeypatch: pytest.MonkeyPatch) -> Iterator[bus.InProcessEventBus]:
    test_bus = bus.InProcessEventBus()
    monkeypatch.setattr(bus, "get_bus", lambda: test_bus)
    yield test_bus


@pytest.fixture
def analyst(make_user: Callable[..., User]) -> User:
    return make_user(role=DefaultRole.BUSINESS_ANALYST)


@pytest.fixture
def developer(make_user: Callable[..., User]) -> User:
    return make_user(role=DefaultRole.DEVELOPER)


def _create(client: TestClient, project: Project, user: User, **body: object) -> dict[str, object]:
    response = client.post(channels_url(project), json=body, headers=headers_for(user))
    assert response.status_code == 201, response.text
    return response.json()


def _post_message(db: Session, channel_id: object, author: User, body: str = "hello") -> Message:
    # The whole test is one transaction, so now() would equal the membership's joined_at.
    message = Message(
        channel_id=uuid.UUID(str(channel_id)),
        author_id=author.id,
        body=body,
        created_at=datetime.now(UTC),
    )
    db.add(message)
    db.commit()
    return message


class TestCreate:
    def test_an_analyst_creates_a_public_channel_with_a_normalised_name(
        self, client: TestClient, project: Project, analyst: User, events: bus.InProcessEventBus
    ) -> None:
        created = _create(client, project, analyst, name="  #Mobile App ", topic="Login flows")

        assert created["name"] == "mobile-app"
        assert created["is_private"] is False and created["is_default"] is False
        (event,) = [e for e in events.published if e.type == CHANNEL_CREATED]
        assert event.channel_id == uuid.UUID(str(created["id"]))
        assert "mobile" not in str(event.data)  # ids and flags only (CR-04)

    def test_a_developer_cannot_create_channels(
        self, client: TestClient, project: Project, developer: User
    ) -> None:
        response = client.post(
            channels_url(project), json={"name": "x"}, headers=headers_for(developer)
        )
        assert response.status_code == 403

    def test_names_are_unique_in_the_project(
        self, client: TestClient, project: Project, analyst: User
    ) -> None:
        _create(client, project, analyst, name="security")
        response = client.post(
            channels_url(project), json={"name": "Security"}, headers=headers_for(analyst)
        )
        assert response.status_code == 409

    @pytest.mark.parametrize("name", ["", "   ", "-lead", "a/b", "x" * 81])
    def test_bad_names_are_rejected(
        self, client: TestClient, project: Project, analyst: User, name: str
    ) -> None:
        response = client.post(
            channels_url(project), json={"name": name}, headers=headers_for(analyst)
        )
        assert response.status_code == 422

    def test_a_new_project_gets_general(
        self, client: TestClient, make_user: Callable[..., User]
    ) -> None:
        owner = make_user(role=DefaultRole.OWNER)
        workspace_id = client.get("/api/v1/workspaces", headers=headers_for(owner)).json()[0]["id"]
        project = client.post(
            f"/api/v1/workspaces/{workspace_id}/projects",
            json={"name": "Has general"},
            headers=headers_for(owner),
        ).json()

        listed = client.get(
            f"/api/v1/projects/{project['id']}/channels", headers=headers_for(owner)
        ).json()
        assert [(c["name"], c["is_default"]) for c in listed] == [("general", True)]

    def test_creation_is_audited_with_ids_only(
        self, client: TestClient, project: Project, analyst: User, db_session: Session
    ) -> None:
        created = _create(client, project, analyst, name="secret-plans", topic="Top secret")
        rows = db_session.scalars(
            select(AuditLog).where(AuditLog.action == "channel_created")
        ).all()
        assert [row.details for row in rows] == [
            {"project_id": str(project.id), "channel_id": created["id"]}
        ]


class TestPrivate:
    def test_a_private_channel_is_a_404_for_people_not_listed(
        self,
        client: TestClient,
        project: Project,
        analyst: User,
        make_user: Callable[..., User],
    ) -> None:
        listed, outsider = make_user(), make_user(role=DefaultRole.ADMIN)
        created = _create(
            client, project, analyst, name="board", is_private=True, member_ids=[str(listed.id)]
        )
        url = f"/api/v1/channels/{created['id']}"

        assert client.get(url, headers=headers_for(listed)).status_code == 200
        # an Admin holds channel.manage, but private means private (ADR-12)
        assert client.get(url, headers=headers_for(outsider)).status_code == 404
        assert (
            client.patch(url, json={"topic": "x"}, headers=headers_for(outsider)).status_code == 404
        )
        names = [
            c["name"]
            for c in client.get(channels_url(project), headers=headers_for(outsider)).json()
        ]
        assert "board" not in names

    def test_listing_someone_from_another_workspace_is_refused(
        self,
        client: TestClient,
        project: Project,
        analyst: User,
        make_user: Callable[..., User],
        make_workspace: Callable[..., Workspace],
    ) -> None:
        stranger = make_user(workspace=make_workspace())
        response = client.post(
            channels_url(project),
            json={"name": "x", "is_private": True, "member_ids": [str(stranger.id)]},
            headers=headers_for(analyst),
        )
        assert response.status_code == 404

    def test_members_can_be_added_and_removed_and_removal_is_announced(
        self,
        client: TestClient,
        project: Project,
        analyst: User,
        make_user: Callable[..., User],
        events: bus.InProcessEventBus,
    ) -> None:
        later = make_user()
        created = _create(client, project, analyst, name="core", is_private=True)
        members_url = f"/api/v1/channels/{created['id']}/members"

        added = client.post(
            members_url, json={"user_id": str(later.id)}, headers=headers_for(analyst)
        )
        assert added.status_code == 201
        assert {
            m["user_id"] for m in client.get(members_url, headers=headers_for(later)).json()
        } == {
            str(analyst.id),
            str(later.id),
        }

        removed = client.delete(f"{members_url}/{later.id}", headers=headers_for(analyst))
        assert removed.status_code == 204
        assert (
            client.get(f"/api/v1/channels/{created['id']}", headers=headers_for(later)).status_code
            == 404
        )
        (event,) = [e for e in events.published if e.type == CHANNEL_MEMBER_REMOVED]
        assert event.data == {
            "channel_id": created["id"],
            "private": True,
            "user_id": str(later.id),
        }

    def test_public_channels_have_no_member_list(
        self, client: TestClient, project: Project, analyst: User
    ) -> None:
        created = _create(client, project, analyst, name="open")
        response = client.get(
            f"/api/v1/channels/{created['id']}/members", headers=headers_for(analyst)
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "channel_public"


class TestChanges:
    def test_rename_and_topic(
        self, client: TestClient, project: Project, analyst: User, events: bus.InProcessEventBus
    ) -> None:
        created = _create(client, project, analyst, name="old")
        response = client.patch(
            f"/api/v1/channels/{created['id']}",
            json={"name": "New Name", "topic": "t"},
            headers=headers_for(analyst),
        )
        assert response.status_code == 200
        assert (response.json()["name"], response.json()["topic"]) == ("new-name", "t")
        assert [e.type for e in events.published][-1] == CHANNEL_UPDATED

    def test_archived_channels_are_read_only_and_hidden_by_default(
        self, client: TestClient, project: Project, analyst: User
    ) -> None:
        created = _create(client, project, analyst, name="done")
        url = f"/api/v1/channels/{created['id']}"

        archived = client.post(f"{url}/archive", headers=headers_for(analyst))
        assert archived.status_code == 200 and archived.json()["archived_at"] is not None

        renamed = client.patch(url, json={"name": "again"}, headers=headers_for(analyst))
        assert renamed.status_code == 409
        assert renamed.json()["error"]["code"] == "channel_archived"
        default = [
            c["name"]
            for c in client.get(channels_url(project), headers=headers_for(analyst)).json()
        ]
        everything = [
            c["name"]
            for c in client.get(
                channels_url(project),
                params={"include_archived": True},
                headers=headers_for(analyst),
            ).json()
        ]
        assert "done" not in default and "done" in everything

    def test_general_cannot_be_archived_or_renamed(
        self, client: TestClient, project: Project, analyst: User, db_session: Session
    ) -> None:
        general = Channel(project_id=project.id, name="general", is_default=True)
        db_session.add(general)
        db_session.commit()
        url = f"/api/v1/channels/{general.id}"

        assert client.post(f"{url}/archive", headers=headers_for(analyst)).status_code == 409
        assert (
            client.patch(url, json={"name": "lobby"}, headers=headers_for(analyst)).status_code
            == 409
        )


class TestUnread:
    def test_unread_counts_others_top_level_messages_until_read(
        self,
        client: TestClient,
        project: Project,
        analyst: User,
        developer: User,
        db_session: Session,
    ) -> None:
        created = _create(client, project, analyst, name="chat")
        root = _post_message(db_session, created["id"], developer, "one")
        _post_message(db_session, created["id"], developer, "two")
        _post_message(db_session, created["id"], analyst, "mine")  # own messages never count
        reply = Message(
            channel_id=root.channel_id,
            author_id=developer.id,
            body="r",
            parent_id=root.id,
            created_at=datetime.now(UTC),
        )
        db_session.add(reply)  # thread replies do not count towards the channel
        db_session.commit()

        def unread() -> int:
            listed = client.get(channels_url(project), headers=headers_for(analyst)).json()
            return next(c["unread_count"] for c in listed if c["id"] == created["id"])

        assert unread() == 2
        assert (
            client.post(
                f"/api/v1/channels/{created['id']}/read", headers=headers_for(analyst)
            ).status_code
            == 204
        )
        assert unread() == 0

    def test_a_viewer_can_read_but_not_manage(
        self,
        client: TestClient,
        project: Project,
        analyst: User,
        make_user: Callable[..., User],
    ) -> None:
        viewer = make_user(role=DefaultRole.VIEWER)
        created = _create(client, project, analyst, name="news")
        url = f"/api/v1/channels/{created['id']}"

        assert client.get(url, headers=headers_for(viewer)).status_code == 200
        assert client.post(f"{url}/read", headers=headers_for(viewer)).status_code == 204
        assert client.post(f"{url}/archive", headers=headers_for(viewer)).status_code == 403


def test_another_workspaces_channel_is_a_404(
    client: TestClient,
    project: Project,
    analyst: User,
    make_user: Callable[..., User],
    make_workspace: Callable[..., Workspace],
) -> None:
    created = _create(client, project, analyst, name="ours")
    stranger = make_user(role=DefaultRole.OWNER, workspace=make_workspace())

    response = client.get(f"/api/v1/channels/{created['id']}", headers=headers_for(stranger))
    assert response.status_code == 404
