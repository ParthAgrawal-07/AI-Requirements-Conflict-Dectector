"""Event envelope and bus (US-03): delivery, isolation per workspace, failure never raises."""

import uuid
from unittest.mock import MagicMock

import redis

from app.realtime import bus
from app.realtime.events import ANALYSIS_PROGRESS, Event, analysis_progress


def _progress(workspace_id: uuid.UUID) -> Event:
    return analysis_progress(
        workspace_id=workspace_id,
        project_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        status="processing",
        progress_percent=10,
        stage="extraction",
    )


def test_the_envelope_carries_ids_and_numbers_only() -> None:
    event = _progress(uuid.uuid4())
    payload = event.model_dump(mode="json")
    assert payload["type"] == ANALYSIS_PROGRESS
    assert set(payload) == {
        "type", "workspace_id", "project_id", "channel_id", "entity_id", "at", "data",
    }  # fmt: skip
    assert payload["data"]["progress_percent"] == 10


def test_listeners_receive_only_their_workspaces_events() -> None:
    test_bus = bus.InProcessEventBus()
    mine, other = uuid.uuid4(), uuid.uuid4()
    received: list[Event] = []
    test_bus.subscribe(mine, received.append)

    test_bus.publish(_progress(mine))
    test_bus.publish(_progress(other))

    assert [event.workspace_id for event in received] == [mine]


def test_unsubscribe_stops_delivery() -> None:
    test_bus = bus.InProcessEventBus()
    workspace = uuid.uuid4()
    received: list[Event] = []
    unsubscribe = test_bus.subscribe(workspace, received.append)
    unsubscribe()

    test_bus.publish(_progress(workspace))

    assert received == []


def test_redis_publishes_to_the_workspace_channel() -> None:
    client = MagicMock()
    event = _progress(uuid.uuid4())

    bus.RedisEventBus(client).publish(event)

    channel, payload = client.publish.call_args.args
    assert channel == f"rcd:events:{event.workspace_id}"
    assert bus.decode(payload) == event


def test_a_redis_outage_never_reaches_the_caller() -> None:
    client = MagicMock()
    client.publish.side_effect = redis.ConnectionError("down")

    bus.RedisEventBus(client).publish(_progress(uuid.uuid4()))  # does not raise


def test_garbage_on_the_channel_is_ignored() -> None:
    assert bus.decode(b"not json") is None
    assert bus.decode('{"type": "x"}') is None
