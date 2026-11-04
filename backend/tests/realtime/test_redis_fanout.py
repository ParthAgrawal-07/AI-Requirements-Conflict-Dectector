"""Sprint 0 spike check: an event published by one API process reaches a subscriber in another.

Uses the real Redis from ``REDIS_URL`` (two independent clients stand in for two processes).
Skipped when Redis is unreachable, unless ``REQUIRE_DB=1`` (CI), where that is a failure.
"""

import asyncio
import os
import uuid

import pytest
import redis

from app.core.config import get_settings
from app.realtime import bus, gateway
from app.realtime.events import analysis_progress


@pytest.fixture
def redis_url() -> str:
    url = get_settings().redis_url
    try:
        redis.Redis.from_url(url, socket_connect_timeout=1).ping()
    except redis.RedisError as exc:
        if os.environ.get("REQUIRE_DB") == "1":
            pytest.fail(f"Redis is not reachable: {exc}")
        pytest.skip(f"Redis is not reachable: {exc}")
    return url


def test_an_event_from_process_one_reaches_a_socket_on_process_two(redis_url: str) -> None:
    workspace_id = uuid.uuid4()
    event = analysis_progress(
        workspace_id=workspace_id,
        project_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        status="processing",
        progress_percent=42,
    )

    async def scenario() -> object:
        receiver = gateway.RedisFanout(redis_url)  # "API 2": the socket's side
        await receiver.add(workspace_id)
        await asyncio.sleep(0.1)  # let SUBSCRIBE reach the server before publishing
        publisher = bus.RedisEventBus(redis.Redis.from_url(redis_url))  # "API 1"
        publisher.publish(event)
        try:
            return await asyncio.wait_for(anext(receiver.events()), timeout=5)
        finally:
            await receiver.close()

    assert asyncio.run(scenario()) == event


def test_another_workspaces_channel_is_not_received(redis_url: str) -> None:
    mine, theirs = uuid.uuid4(), uuid.uuid4()

    async def scenario() -> bool:
        receiver = gateway.RedisFanout(redis_url)
        await receiver.add(mine)
        await asyncio.sleep(0.1)
        bus.RedisEventBus(redis.Redis.from_url(redis_url)).publish(
            analysis_progress(
                workspace_id=theirs,
                project_id=uuid.uuid4(),
                document_id=uuid.uuid4(),
                status="processing",
                progress_percent=1,
            )
        )
        try:
            await asyncio.wait_for(anext(receiver.events()), timeout=1.5)
        except TimeoutError:
            return False
        finally:
            await receiver.close()
        return True

    assert asyncio.run(scenario()) is False
