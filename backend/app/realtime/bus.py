"""Event bus (Dhavni — US-03, US-29; contract in ``docs/contracts/realtime.md``).

``publish(event)`` sends an :class:`~app.realtime.events.Event` to every API process; each
process's WebSocket gateway forwards it to the sockets subscribed to that workspace/project.

* **Redis pub/sub** in every real deployment: one channel per workspace
  (``rcd:events:<workspace_id>``), so an API process only receives traffic for workspaces its
  connected users belong to. Pub/sub is fire-and-forget — a browser that was offline re-syncs
  over REST on reconnect (the REST API is the source of truth; events are hints).
* **In-process** for tests and single-process development (``REALTIME_BUS=memory``).

Rules for producers:

* Publish **after** the commit that made the change visible, never inside a transaction —
  otherwise a client can re-read over REST before the data exists, or receive an event for a
  change that was rolled back.
* Publishing never raises: a Redis outage must not fail the request or task that caused the
  event. It is logged and the client catches up via REST.
"""

import json
import logging
import threading
import uuid
from collections import defaultdict
from collections.abc import Callable
from functools import lru_cache
from typing import Protocol

import redis

from app.core.config import get_settings
from app.realtime.events import Event

logger = logging.getLogger(__name__)

CHANNEL_PREFIX = "rcd:events:"

Listener = Callable[[Event], None]


def channel_for(workspace_id: uuid.UUID) -> str:
    return f"{CHANNEL_PREFIX}{workspace_id}"


class EventBus(Protocol):
    def publish(self, event: Event) -> None: ...


class RedisEventBus:
    def __init__(self, client: redis.Redis) -> None:
        self._client = client

    def publish(self, event: Event) -> None:
        try:
            self._client.publish(channel_for(event.workspace_id), event.model_dump_json())
        except redis.RedisError:
            logger.warning("Could not publish %s event: Redis unavailable", event.type)


class InProcessEventBus:
    """Delivers to listeners in this process. Tests read :attr:`published`."""

    def __init__(self) -> None:
        self.published: list[Event] = []
        self._listeners: dict[uuid.UUID, list[Listener]] = defaultdict(list)
        self._lock = threading.Lock()

    def publish(self, event: Event) -> None:
        with self._lock:
            self.published.append(event)
            listeners = list(self._listeners[event.workspace_id])
        for listener in listeners:
            try:
                listener(event)
            except Exception:
                logger.exception("Event listener failed for %s", event.type)

    def subscribe(self, workspace_id: uuid.UUID, listener: Listener) -> Callable[[], None]:
        with self._lock:
            self._listeners[workspace_id].append(listener)

        def unsubscribe() -> None:
            with self._lock:
                if listener in self._listeners[workspace_id]:
                    self._listeners[workspace_id].remove(listener)

        return unsubscribe

    def clear(self) -> None:
        with self._lock:
            self.published.clear()


def decode(raw: str | bytes) -> Event | None:
    """Parse a message read from Redis; ``None`` (and a log line) if it is not an event."""
    try:
        return Event.model_validate(json.loads(raw))
    except (ValueError, TypeError):
        logger.warning("Ignoring a malformed event on the bus")
        return None


_memory_bus = InProcessEventBus()


@lru_cache
def get_bus() -> EventBus:
    """The process-wide bus (Redis unless ``REALTIME_BUS=memory``). Tests override it."""
    settings = get_settings()
    if settings.realtime_bus == "memory":
        return _memory_bus
    client = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)
    return RedisEventBus(client)


def memory_bus() -> InProcessEventBus:
    return _memory_bus


def publish(event: Event) -> None:
    """Send ``event`` to every API process. Call it after the commit; never raises."""
    try:
        get_bus().publish(event)
    except Exception:
        logger.exception("Publishing %s failed", event.type)
