"""WebSocket gateway /ws (US-03, US-29): first-frame auth, membership-checked subscribe, fan-out
filtered by workspace and project, revocation closes the socket."""

import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
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
