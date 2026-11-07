"""Channel subscriptions on /ws (US-29): two members chat live; private channels stay private;
being taken off a private channel stops its events at once."""

import uuid
from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core import security
from app.core.permissions import DefaultRole
from app.models import Channel, ChannelMember, Project, User, Workspace
from app.realtime import bus
from app.realtime.events import (
    CHANNEL_MEMBER_REMOVED,
    MESSAGE_CREATED,
    Event,
    analysis_progress,
    channel_event,
    message_event,
)
from tests.api.conftest import headers_for


def _connect(socket: Any, user: User, **subscribe: str) -> dict[str, Any]:
    socket.send_json({"type": "auth", "token": security.create_access_token(user.id)[0]})
    assert socket.receive_json()["type"] == "ready"
    socket.send_json({"type": "subscribe", **subscribe})
    return dict(socket.receive_json())


def _message(channel: Channel, project: Project) -> Event:
    return message_event(
        MESSAGE_CREATED,
        workspace_id=project.workspace_id,
        project_id=project.id,
        channel_id=channel.id,
        private=channel.is_private,
        message_id=uuid.uuid4(),
        parent_id=None,
        author_id=uuid.uuid4(),
        mentions=[],
    )


def _sentinel(project: Project) -> Event:
    return analysis_progress(
        workspace_id=project.workspace_id,
        project_id=project.id,
        document_id=uuid.uuid4(),
        status="processing",
        progress_percent=42,
    )


def _channel(
    db: Session, project: Project, *, private: bool = False, listed: tuple[User, ...] = ()
) -> Channel:
    channel = Channel(project_id=project.id, name=f"c-{uuid.uuid4().hex[:6]}", is_private=private)
    db.add(channel)
    db.flush()
    db.add_all(ChannelMember(channel_id=channel.id, user_id=user.id) for user in listed)
    db.commit()
    return channel


def test_two_members_chat_live(
    client: TestClient,
    event_bus: bus.InProcessEventBus,
    db_session: Session,
    project: Project,
    make_user: Callable[..., User],
) -> None:
    riya, arjun = make_user(role=DefaultRole.DEVELOPER), make_user(role=DefaultRole.DEVELOPER)
    channel = _channel(db_session, project)

    with client.websocket_connect("/ws") as socket:
        subscribed = _connect(socket, arjun, channel_id=str(channel.id))
        assert subscribed["channel_id"] == str(channel.id)

        posted = client.post(
            f"/api/v1/channels/{channel.id}/messages",
            json={"body": "Is the 30-minute timeout final?"},
            headers=headers_for(riya),
        )
        assert posted.status_code == 201

        frame = socket.receive_json()
        assert frame["event"]["type"] == MESSAGE_CREATED
        message_id = frame["event"]["data"]["message_id"]
        assert message_id == posted.json()["id"]
        # The event carries ids; Arjun's client re-reads the message over REST.
        reread = client.get(f"/api/v1/messages/{message_id}", headers=headers_for(arjun))
        assert reread.json()["body"] == "Is the 30-minute timeout final?"


def test_a_private_channel_cannot_be_subscribed_by_someone_not_listed(
    client: TestClient,
    event_bus: bus.InProcessEventBus,
    db_session: Session,
    project: Project,
    make_user: Callable[..., User],
) -> None:
    listed, admin = make_user(), make_user(role=DefaultRole.ADMIN)
    private = _channel(db_session, project, private=True, listed=(listed,))

    with client.websocket_connect("/ws") as socket:
        assert _connect(socket, admin, channel_id=str(private.id)) == {
            "type": "error",
            "code": "not_found",
        }


def test_private_channel_events_skip_project_subscribers(
    client: TestClient,
    event_bus: bus.InProcessEventBus,
    db_session: Session,
    project: Project,
    make_user: Callable[..., User],
) -> None:
    watcher = make_user()
    public, private = _channel(db_session, project), _channel(db_session, project, private=True)

    with client.websocket_connect("/ws") as socket:
        _connect(socket, watcher, project_id=str(project.id))
        event_bus.publish(_message(private, project))  # not for a mere project subscriber
        event_bus.publish(_message(public, project))  # public channel events reach the project

        assert socket.receive_json()["event"]["channel_id"] == str(public.id)


def test_being_taken_off_a_private_channel_stops_its_events(
    client: TestClient,
    event_bus: bus.InProcessEventBus,
    db_session: Session,
    project: Project,
    make_user: Callable[..., User],
) -> None:
    member = make_user()
    private = _channel(db_session, project, private=True, listed=(member,))

    with client.websocket_connect("/ws") as socket:
        _connect(socket, member, channel_id=str(private.id))
        socket.send_json({"type": "subscribe", "project_id": str(project.id)})
        assert socket.receive_json()["type"] == "subscribed"

        event_bus.publish(
            channel_event(
                CHANNEL_MEMBER_REMOVED,
                workspace_id=project.workspace_id,
                project_id=project.id,
                channel_id=private.id,
                private=True,
                user_id=str(member.id),
            )
        )
        assert socket.receive_json()["event"]["type"] == CHANNEL_MEMBER_REMOVED
        event_bus.publish(_message(private, project))  # no longer delivered
        event_bus.publish(_sentinel(project))

        assert socket.receive_json()["event"]["data"]["progress_percent"] == 42


def test_another_workspaces_channel_is_refused_like_an_unknown_id(
    client: TestClient,
    event_bus: bus.InProcessEventBus,
    db_session: Session,
    make_user: Callable[..., User],
    make_project: Callable[..., Project],
    make_workspace: Callable[..., Workspace],
) -> None:
    foreign = _channel(db_session, make_project(workspace=make_workspace()))
    member = make_user()

    with client.websocket_connect("/ws") as socket:
        assert _connect(socket, member, channel_id=str(foreign.id))["code"] == "not_found"
