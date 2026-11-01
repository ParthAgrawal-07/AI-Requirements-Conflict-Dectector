import asyncio
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import app.realtime.router as realtime_router


class FakeWebSocket:
    def __init__(self, messages: list[dict[str, str]]) -> None:
        self.messages = messages
        self.closed_with: dict[str, object] | None = None

    async def receive(self) -> dict[str, str]:
        return self.messages.pop(0)

    async def close(self, **kwargs: object) -> None:
        self.closed_with = kwargs


class FakePubSub:
    def __init__(self) -> None:
        self.subscribed_channel: str | None = None
        self.unsubscribed_channel: str | None = None
        self.unsubscribed = False
        self.closed = False
        self.event_sent = False

    async def subscribe(self, channel: str) -> None:
        self.subscribed_channel = channel

    async def get_message(
        self,
        ignore_subscribe_messages: bool = True,
        timeout: float = 1.0,
    ) -> dict[str, str] | None:
        if not self.event_sent:
            self.event_sent = True
            return {
                "type": "message",
                "data": '{"type": "graph.delta", "revision": 1}',
            }

        await asyncio.sleep(0.01)
        return None

    async def unsubscribe(self, channel: str) -> None:
        self.unsubscribed_channel = channel
        self.unsubscribed = True

    async def aclose(self) -> None:
        self.closed = True


class FakeRedis:
    def __init__(self) -> None:
        self.fake_pubsub = FakePubSub()
        self.closed = False

    def pubsub(self) -> FakePubSub:
        return self.fake_pubsub

    async def aclose(self) -> None:
        self.closed = True


def make_test_client() -> TestClient:
    app = FastAPI()
    app.include_router(realtime_router.router)
    return TestClient(app)


def configure_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        realtime_router,
        "get_settings",
        lambda: SimpleNamespace(
            redis_url="redis://localhost:6379/0",
            cors_allowed_origins=[],
        ),
    )


def test_watch_for_disconnect_returns_when_client_disconnects() -> None:
    websocket = FakeWebSocket([{"type": "websocket.disconnect"}])

    asyncio.run(
        realtime_router._watch_for_disconnect(websocket)  # type: ignore[arg-type]
    )

    assert websocket.closed_with is None


def test_watch_for_disconnect_rejects_client_messages() -> None:
    websocket = FakeWebSocket([{"type": "websocket.receive", "text": "unexpected"}])

    asyncio.run(
        realtime_router._watch_for_disconnect(websocket)  # type: ignore[arg-type]
    )

    assert websocket.closed_with == {
        "code": 1008,
        "reason": "Client messages are not supported",
    }


def test_websocket_rejects_unauthorised_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_settings(monkeypatch)
    monkeypatch.setattr(
        realtime_router,
        "_is_authorised",
        lambda project_id, token: False,
    )

    client = make_test_client()
    project_id = "12345678-1234-5678-1234-567812345678"

    with client.websocket_connect(f"/ws/projects/{project_id}") as websocket:
        websocket.send_json({"type": "auth", "token": "invalid-token"})

        with pytest.raises(WebSocketDisconnect) as error:
            websocket.receive_json()

        assert error.value.code == 1008


def test_websocket_authentication_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_settings(monkeypatch)
    monkeypatch.setattr(realtime_router, "AUTH_TIMEOUT_SECONDS", 0.01)

    client = make_test_client()
    project_id = "12345678-1234-5678-1234-567812345678"

    with client.websocket_connect(f"/ws/projects/{project_id}") as websocket:
        with pytest.raises(WebSocketDisconnect) as error:
            websocket.receive_json()

        assert error.value.code == 1008


def test_websocket_delivers_events_and_cleans_up_redis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_settings(monkeypatch)
    monkeypatch.setattr(
        realtime_router,
        "_is_authorised",
        lambda project_id, token: True,
    )

    fake_redis = FakeRedis()

    monkeypatch.setattr(
        realtime_router,
        "Redis",
        SimpleNamespace(from_url=lambda *args, **kwargs: fake_redis),
    )

    client = make_test_client()
    project_id = "12345678-1234-5678-1234-567812345678"

    with client.websocket_connect(f"/ws/projects/{project_id}") as websocket:
        websocket.send_json({"type": "auth", "token": "valid-token"})

        ready = websocket.receive_json()
        assert ready["type"] == "ready"
        assert ready["project_id"] == project_id

        event = websocket.receive_json()
        assert event == {"type": "graph.delta", "revision": 1}

    channel = realtime_router.project_channel(__import__("uuid").UUID(project_id))

    assert fake_redis.fake_pubsub.subscribed_channel == channel
    assert fake_redis.fake_pubsub.unsubscribed_channel == channel
    assert fake_redis.fake_pubsub.unsubscribed is True
    assert fake_redis.fake_pubsub.closed is True
    assert fake_redis.closed is True
