"""Messages (US-29, FR-51, FR-52): post, history pages, threads, mentions, edit, delete, limits."""

import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.permissions import DefaultRole
from app.core.rate_limit import InMemoryRateLimiter, get_rate_limiter
from app.models import Channel, ChannelMember, Message, MessageKind, Project, User, Workspace
from app.realtime import bus
from app.realtime.events import MESSAGE_CREATED, MESSAGE_DELETED, MESSAGE_UPDATED
from tests.api.conftest import headers_for


@pytest.fixture(autouse=True)
def limiter(client: TestClient) -> Iterator[InMemoryRateLimiter]:
    from app.main import app

    in_memory = InMemoryRateLimiter()
    app.dependency_overrides[get_rate_limiter] = lambda: in_memory
    yield in_memory
    app.dependency_overrides.pop(get_rate_limiter, None)


@pytest.fixture
def events(monkeypatch: pytest.MonkeyPatch) -> Iterator[bus.InProcessEventBus]:
    test_bus = bus.InProcessEventBus()
    monkeypatch.setattr(bus, "get_bus", lambda: test_bus)
    yield test_bus


@pytest.fixture
def channel(db_session: Session, project: Project) -> Channel:
    channel = Channel(project_id=project.id, name="general", is_default=True)
    db_session.add(channel)
    db_session.commit()
    return channel


@pytest.fixture
def riya(make_user: Callable[..., User]) -> User:
    return make_user(role=DefaultRole.DEVELOPER)


def post(client: TestClient, channel: Channel, user: User, body: str, **extra: Any) -> Any:
    return client.post(
        f"/api/v1/channels/{channel.id}/messages",
        json={"body": body, **extra},
        headers=headers_for(user),
    )


def history(client: TestClient, channel: Channel, user: User, **params: Any) -> dict[str, Any]:
    response = client.get(
        f"/api/v1/channels/{channel.id}/messages", params=params, headers=headers_for(user)
    )
    assert response.status_code == 200, response.text
    return dict(response.json())


def bodies(page: dict[str, Any]) -> list[str]:
    return [item["body"] for item in page["items"]]


class TestPost:
    def test_a_member_posts_and_the_event_carries_ids_only(
        self, client: TestClient, channel: Channel, riya: User, events: bus.InProcessEventBus
    ) -> None:
        response = post(client, channel, riya, "  Session timeout is 30 minutes?  ")

        assert response.status_code == 201
        message = response.json()
        assert message["body"] == "Session timeout is 30 minutes?"
        assert message["author"] == {
            "id": str(riya.id),
            "full_name": "Test User",
            "is_member": True,
        }
        (event,) = [e for e in events.published if e.type == MESSAGE_CREATED]
        assert event.channel_id == channel.id and event.entity_id == uuid.UUID(message["id"])
        assert "timeout" not in str(event.model_dump())  # CR-04

    def test_a_viewer_reads_but_cannot_post(
        self, client: TestClient, channel: Channel, make_user: Callable[..., User]
    ) -> None:
        viewer = make_user(role=DefaultRole.VIEWER)
        assert post(client, channel, viewer, "hi").status_code == 403
        assert history(client, channel, viewer)["items"] == []

    @pytest.mark.parametrize("body", ["   ", "x" * 4001])
    def test_empty_and_overlong_messages_are_refused(
        self, client: TestClient, channel: Channel, riya: User, body: str
    ) -> None:
        assert post(client, channel, riya, body).status_code == 400

    def test_html_is_stored_as_plain_text(
        self, client: TestClient, channel: Channel, riya: User
    ) -> None:
        payload = "<img src=x onerror=alert(1)>"
        assert post(client, channel, riya, payload).json()["body"] == payload

    def test_an_archived_channel_is_read_only(
        self, client: TestClient, db_session: Session, project: Project, riya: User
    ) -> None:
        archived = Channel(project_id=project.id, name="old")
        db_session.add(archived)
        db_session.commit()
        archived.archived_at = archived.created_at
        db_session.commit()

        response = post(client, archived, riya, "anyone?")
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "channel_archived"

    def test_posting_is_rate_limited(
        self,
        client: TestClient,
        channel: Channel,
        riya: User,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(get_settings(), "messages_per_minute", 3)
        codes = [post(client, channel, riya, f"m{i}").status_code for i in range(4)]
        assert codes == [201, 201, 201, 429]


class TestHistory:
    def test_pages_go_back_in_time_and_after_catches_up(
        self, client: TestClient, channel: Channel, riya: User
    ) -> None:
        for i in range(5):
            assert post(client, channel, riya, f"m{i}").status_code == 201

        newest = history(client, channel, riya, limit=2)
        assert bodies(newest) == ["m3", "m4"]
        older = history(client, channel, riya, limit=2, before=newest["next_cursor"])
        assert bodies(older) == ["m1", "m2"]
        oldest = history(client, channel, riya, limit=2, before=older["next_cursor"])
        assert bodies(oldest) == ["m0"] and oldest["next_cursor"] is None

        # After a reconnect the client asks for what is newer than the last message it holds.
        held = newest["items"][0]["cursor"]  # m3
        assert bodies(history(client, channel, riya, after=held)) == ["m4"]
        post(client, channel, riya, "m5")
        assert bodies(history(client, channel, riya, after=held)) == ["m4", "m5"]

    def test_a_bad_cursor_is_a_400(self, client: TestClient, channel: Channel, riya: User) -> None:
        response = client.get(
            f"/api/v1/channels/{channel.id}/messages",
            params={"before": "not-a-cursor"},
            headers=headers_for(riya),
        )
        assert response.status_code == 400


class TestThreads:
    def test_replies_form_a_thread_and_are_counted(
        self, client: TestClient, channel: Channel, riya: User, make_user: Callable[..., User]
    ) -> None:
        arjun = make_user(role=DefaultRole.DEVELOPER)
        root = post(client, channel, riya, "Which timeout applies?").json()
        post(client, channel, arjun, "30 minutes", parent_id=root["id"])
        post(client, channel, riya, "Thanks", parent_id=root["id"])

        page = history(client, channel, riya)
        assert bodies(page) == ["Which timeout applies?"]  # replies stay in the thread
        assert page["items"][0]["reply_count"] == 2
        thread = client.get(f"/api/v1/messages/{root['id']}/thread", headers=headers_for(riya))
        assert [m["body"] for m in thread.json()] == [
            "Which timeout applies?",
            "30 minutes",
            "Thanks",
        ]

    def test_threads_are_one_level_deep(
        self, client: TestClient, channel: Channel, riya: User
    ) -> None:
        root = post(client, channel, riya, "root").json()
        reply = post(client, channel, riya, "reply", parent_id=root["id"]).json()
        response = post(client, channel, riya, "deeper", parent_id=reply["id"])
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "nested_thread"

    def test_a_parent_from_another_channel_is_a_404(
        self,
        client: TestClient,
        db_session: Session,
        project: Project,
        channel: Channel,
        riya: User,
    ) -> None:
        other = Channel(project_id=project.id, name="other")
        db_session.add(other)
        db_session.commit()
        root = post(client, other, riya, "elsewhere").json()
        assert post(client, channel, riya, "reply", parent_id=root["id"]).status_code == 404


class TestMentions:
    def test_mentions_are_parsed_to_members_who_can_see_the_channel(
        self,
        client: TestClient,
        channel: Channel,
        riya: User,
        make_user: Callable[..., User],
        make_workspace: Callable[..., Workspace],
        events: bus.InProcessEventBus,
    ) -> None:
        meera = make_user(role=DefaultRole.COMPLIANCE_REVIEWER)
        stranger = make_user(workspace=make_workspace())
        body = f"<@{meera.id}> and <@{stranger.id}> and <@{meera.id}>, please check"

        message = post(client, channel, riya, body).json()

        assert message["mentions"] == [str(meera.id)]
        (event,) = [e for e in events.published if e.type == MESSAGE_CREATED]
        assert event.data["mentions"] == [str(meera.id)]

    def test_in_a_private_channel_only_listed_people_are_mentioned(
        self,
        client: TestClient,
        db_session: Session,
        project: Project,
        riya: User,
        make_user: Callable[..., User],
    ) -> None:
        listed, unlisted = make_user(), make_user()
        private = Channel(project_id=project.id, name="core", is_private=True)
        db_session.add(private)
        db_session.flush()
        db_session.add_all(
            ChannelMember(channel_id=private.id, user_id=u.id) for u in (riya, listed)
        )
        db_session.commit()

        message = post(client, private, riya, f"<@{listed.id}> <@{unlisted.id}>").json()
        assert message["mentions"] == [str(listed.id)]


class TestEditAndDelete:
    def test_the_author_edits_and_it_is_marked_edited(
        self, client: TestClient, channel: Channel, riya: User, events: bus.InProcessEventBus
    ) -> None:
        message = post(client, channel, riya, "typo").json()
        response = client.patch(
            f"/api/v1/messages/{message['id']}", json={"body": "fixed"}, headers=headers_for(riya)
        )
        assert response.status_code == 200
        assert response.json()["body"] == "fixed" and response.json()["edited_at"] is not None
        assert events.published[-1].type == MESSAGE_UPDATED

    def test_someone_else_cannot_edit_or_delete(
        self, client: TestClient, channel: Channel, riya: User, make_user: Callable[..., User]
    ) -> None:
        other = make_user(role=DefaultRole.ADMIN)
        message = post(client, channel, riya, "mine").json()
        url = f"/api/v1/messages/{message['id']}"
        assert client.patch(url, json={"body": "x"}, headers=headers_for(other)).status_code == 403
        assert client.delete(url, headers=headers_for(other)).status_code == 403

    def test_delete_is_soft_and_keeps_the_thread(
        self, client: TestClient, channel: Channel, riya: User, events: bus.InProcessEventBus
    ) -> None:
        root = post(client, channel, riya, "secret plan").json()
        post(client, channel, riya, "a reply", parent_id=root["id"])

        assert (
            client.delete(f"/api/v1/messages/{root['id']}", headers=headers_for(riya)).status_code
            == 204
        )

        thread = client.get(
            f"/api/v1/messages/{root['id']}/thread", headers=headers_for(riya)
        ).json()
        assert thread[0]["deleted"] is True and thread[0]["body"] == ""
        assert thread[1]["body"] == "a reply"
        assert events.published[-1].type == MESSAGE_DELETED
        again = client.patch(
            f"/api/v1/messages/{root['id']}", json={"body": "x"}, headers=headers_for(riya)
        )
        assert again.status_code == 409

    def test_a_requirement_post_is_never_edited(
        self, client: TestClient, db_session: Session, channel: Channel, riya: User
    ) -> None:
        card = Message(
            channel_id=channel.id, author_id=riya.id, body="REQ", kind=MessageKind.REQUIREMENT_POST
        )
        db_session.add(card)
        db_session.commit()
        response = client.patch(
            f"/api/v1/messages/{card.id}", json={"body": "x"}, headers=headers_for(riya)
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "not_editable"


class TestAccess:
    def test_a_private_channels_messages_are_a_404_for_others(
        self,
        client: TestClient,
        db_session: Session,
        project: Project,
        riya: User,
        make_user: Callable[..., User],
    ) -> None:
        outsider = make_user(role=DefaultRole.ADMIN)
        private = Channel(project_id=project.id, name="hr", is_private=True)
        db_session.add(private)
        db_session.flush()
        db_session.add(ChannelMember(channel_id=private.id, user_id=riya.id))
        db_session.commit()
        message = post(client, private, riya, "private").json()

        assert (
            client.get(
                f"/api/v1/channels/{private.id}/messages", headers=headers_for(outsider)
            ).status_code
            == 404
        )
        assert (
            client.get(
                f"/api/v1/messages/{message['id']}", headers=headers_for(outsider)
            ).status_code
            == 404
        )
        assert post(client, private, outsider, "let me in").status_code == 404

    def test_another_workspace_is_a_404(
        self,
        client: TestClient,
        channel: Channel,
        riya: User,
        make_user: Callable[..., User],
        make_workspace: Callable[..., Workspace],
    ) -> None:
        stranger = make_user(role=DefaultRole.OWNER, workspace=make_workspace())
        assert post(client, channel, stranger, "hi").status_code == 404

    def test_a_former_members_messages_stay_attributed_to_them(
        self,
        client: TestClient,
        workspace: Workspace,
        channel: Channel,
        riya: User,
        make_user: Callable[..., User],
    ) -> None:
        owner = make_user(role=DefaultRole.OWNER)
        post(client, channel, riya, "my last words")
        client.delete(
            f"/api/v1/workspaces/{workspace.id}/members/{riya.id}", headers=headers_for(owner)
        )

        (item,) = history(client, channel, owner)["items"]
        assert item["body"] == "my last words"
        assert item["author"]["id"] == str(riya.id) and item["author"]["is_member"] is False
