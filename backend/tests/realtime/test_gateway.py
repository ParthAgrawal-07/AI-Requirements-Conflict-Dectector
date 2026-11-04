"""WebSocket gateway /ws (US-03, US-29): first-frame auth, membership-checked subscribe, fan-out
filtered by workspace and project, revocation closes the socket."""

import uuid
from collections.abc import Callable

import pytest
import redis
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from starlette.websockets import WebSocketDisconnect

from app.core import security
from app.core.permissions import DefaultRole
from app.models import Project, User, Workspace
from app.realtime import bus, gateway
from app.realtime.events import MEMBERSHIP_REVOKED, Event, analysis_progress


def _token(user: User) -> str:
    return security.create_access_token(user.id)[0]


def _progress(project: Project, percent: int = 10) -> Event:
    return analysis_progress(
        workspace_id=project.workspace_id,
        project_id=project.id,
        document_id=uuid.uuid4(),
        status="processing",
        progress_percent=percent,
    )


def test_a_socket_without_a_valid_first_frame_is_closed(
    client: TestClient, event_bus: bus.InProcessEventBus
) -> None:
    with client.websocket_connect("/ws") as socket:
        socket.send_json({"type": "auth", "token": "not-a-jwt"})
        with pytest.raises(WebSocketDisconnect) as closed:
            socket.receive_json()
    assert closed.value.code == gateway.CLOSE_UNAUTHENTICATED


def test_a_member_receives_progress_for_the_project_they_watch(
    client: TestClient, event_bus: bus.InProcessEventBus, user: User, project: Project
) -> None:
    with client.websocket_connect("/ws") as socket:
        socket.send_json({"type": "auth", "token": _token(user)})
        assert socket.receive_json()["type"] == "ready"
        socket.send_json({"type": "subscribe", "project_id": str(project.id)})
        assert socket.receive_json()["type"] == "subscribed"

        event_bus.publish(_progress(project, 60))

        frame = socket.receive_json()
        assert frame["type"] == "event"
        assert frame["event"]["data"]["progress_percent"] == 60


def test_events_of_another_project_in_the_same_workspace_are_not_forwarded(
    client: TestClient,
    event_bus: bus.InProcessEventBus,
    user: User,
    make_project: Callable[..., Project],
) -> None:
    watched, other = make_project(), make_project()
    with client.websocket_connect("/ws") as socket:
        socket.send_json({"type": "auth", "token": _token(user)})
        socket.receive_json()
        socket.send_json({"type": "subscribe", "project_id": str(watched.id)})
        socket.receive_json()

        event_bus.publish(_progress(other, 11))
        event_bus.publish(_progress(watched, 22))

        assert socket.receive_json()["event"]["data"]["progress_percent"] == 22


def test_subscribing_to_another_workspace_is_refused_like_an_unknown_id(
    client: TestClient,
    event_bus: bus.InProcessEventBus,
    user: User,
    make_workspace: Callable[..., Workspace],
    make_project: Callable[..., Project],
) -> None:
    foreign = make_project(workspace=make_workspace())
    with client.websocket_connect("/ws") as socket:
        socket.send_json({"type": "auth", "token": _token(user)})
        socket.receive_json()

        socket.send_json({"type": "subscribe", "project_id": str(foreign.id)})
        refused = socket.receive_json()
        socket.send_json({"type": "subscribe", "project_id": str(uuid.uuid4())})
        unknown = socket.receive_json()

    assert refused == unknown == {"type": "error", "code": "not_found"}


def test_revoking_the_membership_closes_the_socket(
    client: TestClient,
    event_bus: bus.InProcessEventBus,
    make_user: Callable[..., User],
    workspace: Workspace,
) -> None:
    member = make_user(role=DefaultRole.DEVELOPER)
    with client.websocket_connect("/ws") as socket:
        socket.send_json({"type": "auth", "token": _token(member)})
        socket.receive_json()
        socket.send_json({"type": "subscribe", "workspace_id": str(workspace.id)})
        socket.receive_json()

        event_bus.publish(
            Event(
                type=MEMBERSHIP_REVOKED,
                workspace_id=workspace.id,
                data={"user_id": str(member.id)},
            )
        )

        with pytest.raises(WebSocketDisconnect) as closed:
            socket.receive_json()
    assert closed.value.code == gateway.CLOSE_REVOKED


def test_ping_pong(client: TestClient, event_bus: bus.InProcessEventBus, user: User) -> None:
    with client.websocket_connect("/ws") as socket:
        socket.send_json({"type": "auth", "token": _token(user)})
        socket.receive_json()
        socket.send_json({"type": "ping"})
        assert socket.receive_json() == {"type": "pong"}


def test_an_idle_socket_does_not_hold_a_database_transaction(
    client: TestClient,
    event_bus: bus.InProcessEventBus,
    db_session: Session,
    user: User,
    project: Project,
) -> None:
    with client.websocket_connect("/ws") as socket:
        socket.send_json({"type": "auth", "token": _token(user)})
        socket.receive_json()
        assert not db_session.in_transaction()

        socket.send_json({"type": "subscribe", "project_id": str(project.id)})
        socket.receive_json()
        assert not db_session.in_transaction()


def test_a_redis_outage_on_subscribe_is_reported_not_fatal(
    client: TestClient,
    event_bus: bus.InProcessEventBus,
    monkeypatch: pytest.MonkeyPatch,
    user: User,
    project: Project,
) -> None:
    class DownFanout(gateway.MemoryFanout):
        async def add(self, workspace_id: uuid.UUID) -> None:
            raise redis.ConnectionError("down")

    monkeypatch.setattr(gateway, "make_fanout", lambda: DownFanout(event_bus))
    with client.websocket_connect("/ws") as socket:
        socket.send_json({"type": "auth", "token": _token(user)})
        socket.receive_json()

        socket.send_json({"type": "subscribe", "project_id": str(project.id)})
        assert socket.receive_json() == {"type": "error", "code": "unavailable"}
        socket.send_json({"type": "ping"})
        assert socket.receive_json() == {"type": "pong"}


def test_unsubscribe_stops_forwarding_that_project(
    client: TestClient,
    event_bus: bus.InProcessEventBus,
    user: User,
    make_project: Callable[..., Project],
) -> None:
    dropped, kept = make_project(), make_project()
    with client.websocket_connect("/ws") as socket:
        socket.send_json({"type": "auth", "token": _token(user)})
        socket.receive_json()
        for project in (dropped, kept):
            socket.send_json({"type": "subscribe", "project_id": str(project.id)})
            socket.receive_json()

        socket.send_json({"type": "unsubscribe", "project_id": str(dropped.id)})
        socket.send_json({"type": "unsubscribe", "project_id": "not-a-uuid"})
        socket.send_json({"type": "ping"})
        assert socket.receive_json() == {"type": "pong"}  # unsubscribes were handled, no reply

        event_bus.publish(_progress(dropped, 11))
        event_bus.publish(_progress(kept, 22))

        assert socket.receive_json()["event"]["data"]["progress_percent"] == 22
