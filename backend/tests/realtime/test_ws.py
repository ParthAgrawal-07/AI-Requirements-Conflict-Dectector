"""WebSocket security (Affan — US-27, US-29, NFR-27): the token travels in the first frame only;
bad, late, expired or disabled credentials close the socket; revocation closes exactly the revoked
user's sockets; events carry ids, never message text."""

from collections.abc import Callable
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from starlette.testclient import WebSocketTestSession
from starlette.websockets import WebSocketDisconnect

from app.core import security
from app.core.permissions import DefaultRole
from app.models import Channel, Project, User, Workspace
from app.realtime import bus, gateway
from tests.api.conftest import headers_for


def token(user: User) -> str:
    return security.create_access_token(user.id)[0]


def closed_code(socket: WebSocketTestSession) -> int:
    with pytest.raises(WebSocketDisconnect) as closed:
        socket.receive_json()
    return closed.value.code


def test_a_token_in_the_url_is_not_accepted(
    client: TestClient, event_bus: bus.InProcessEventBus, user: User
) -> None:
    with client.websocket_connect(f"/ws?token={token(user)}") as socket:
        socket.send_json({"type": "subscribe", "workspace_id": "x"})  # no auth frame first
        assert closed_code(socket) == gateway.CLOSE_UNAUTHENTICATED


def test_a_socket_that_never_authenticates_is_closed(
    client: TestClient, event_bus: bus.InProcessEventBus, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gateway, "AUTH_TIMEOUT_SECONDS", 0.2)
    with client.websocket_connect("/ws") as socket:
        assert closed_code(socket) == gateway.CLOSE_UNAUTHENTICATED


def test_an_expired_token_is_refused(
    client: TestClient, event_bus: bus.InProcessEventBus, user: User
) -> None:
    expired, _ = security.create_access_token(
        user.id, expires_delta=timedelta(hours=-1)
    )  # beyond any leeway
    with client.websocket_connect("/ws") as socket:
        socket.send_json({"type": "auth", "token": expired})
        assert closed_code(socket) == gateway.CLOSE_UNAUTHENTICATED


def test_a_disabled_account_is_refused(
    client: TestClient, event_bus: bus.InProcessEventBus, make_user: Callable[..., User]
) -> None:
    disabled = make_user(is_active=False)
    with client.websocket_connect("/ws") as socket:
        socket.send_json({"type": "auth", "token": token(disabled)})
        assert closed_code(socket) == gateway.CLOSE_UNAUTHENTICATED


def test_revoking_one_member_leaves_other_sockets_open(
    client: TestClient,
    event_bus: bus.InProcessEventBus,
    workspace: Workspace,
    project: Project,
    make_user: Callable[..., User],
) -> None:
    owner, leaver, stayer = (
        make_user(role=DefaultRole.OWNER),
        make_user(role=DefaultRole.DEVELOPER),
        make_user(role=DefaultRole.DEVELOPER),
    )
    with client.websocket_connect("/ws") as gone, client.websocket_connect("/ws") as kept:
        for socket, member in ((gone, leaver), (kept, stayer)):
            socket.send_json({"type": "auth", "token": token(member)})
            assert socket.receive_json()["type"] == "ready"
            socket.send_json({"type": "subscribe", "project_id": str(project.id)})
            assert socket.receive_json()["type"] == "subscribed"

        removed = client.delete(
            f"/api/v1/workspaces/{workspace.id}/members/{leaver.id}", headers=headers_for(owner)
        )
        assert removed.status_code == 204

        assert closed_code(gone) == gateway.CLOSE_REVOKED
        # The others stay connected; they hear about the removal (ids only) for live member lists.
        notice = kept.receive_json()
        assert notice["event"]["type"] == "membership.revoked"
        assert notice["event"]["data"] == {"user_id": str(leaver.id)}
        kept.send_json({"type": "ping"})
        assert kept.receive_json()["type"] == "pong"


def test_a_removed_member_cannot_subscribe_again(
    client: TestClient,
    event_bus: bus.InProcessEventBus,
    workspace: Workspace,
    project: Project,
    make_user: Callable[..., User],
) -> None:
    owner, leaver = make_user(role=DefaultRole.OWNER), make_user()
    client.delete(
        f"/api/v1/workspaces/{workspace.id}/members/{leaver.id}", headers=headers_for(owner)
    )

    with client.websocket_connect("/ws") as socket:
        socket.send_json(
            {"type": "auth", "token": token(leaver)}
        )  # the token itself is still valid
        assert socket.receive_json()["type"] == "ready"
        socket.send_json({"type": "subscribe", "project_id": str(project.id)})
        assert socket.receive_json() == {"type": "error", "code": "not_found"}


def test_message_events_never_carry_the_text(
    client: TestClient,
    event_bus: bus.InProcessEventBus,
    db_session: Session,
    project: Project,
    make_user: Callable[..., User],
) -> None:
    writer, reader = make_user(role=DefaultRole.DEVELOPER), make_user(role=DefaultRole.VIEWER)
    channel = Channel(project_id=project.id, name="general", is_default=True)
    db_session.add(channel)
    db_session.commit()

    with client.websocket_connect("/ws") as socket:
        socket.send_json({"type": "auth", "token": token(reader)})
        socket.receive_json()
        socket.send_json({"type": "subscribe", "channel_id": str(channel.id)})
        assert socket.receive_json()["type"] == "subscribed"

        client.post(
            f"/api/v1/channels/{channel.id}/messages",
            json={"body": "the launch date is secret"},
            headers=headers_for(writer),
        )

        frame = socket.receive_json()
        assert frame["event"]["type"] == "message.created"
        assert "secret" not in str(frame)
