"""WebSocket gateway ``/ws`` (Dhavni — US-03, US-29; protocol in ``docs/contracts/realtime.md``).

One socket per browser tab. The conversation is JSON frames::

    client  {"type": "auth", "token": "<JWT>"}                  first frame, within 10 s
    server  {"type": "ready", "user_id": "..."}
    client  {"type": "subscribe", "project_id": "..."}          or "workspace_id" or "channel_id"
    server  {"type": "subscribed", "workspace_id": "...", "project_id": "..."}
    client  {"type": "unsubscribe", "project_id": "..."}        or "workspace_id" or "channel_id"
    server  {"type": "event", "event": {...envelope...}}         from then on
    client  {"type": "ping"}  ->  server {"type": "pong"}

* The token travels in the first frame, not the URL, so it never lands in proxy logs.
* Each ``subscribe`` re-reads the membership (the same ``view`` check as REST): a non-member
  gets ``{"type": "error", "code": "not_found"}`` — the same answer as for an unknown id.
* A ``channel_id`` subscription receives that channel's events. Events of a **private** channel
  (``data.private``) reach only sockets subscribed to it by id, checked against the channel's
  member list; a ``channel.member_removed`` for this user ends that subscription at once.
* A ``membership.revoked`` event for this user closes the socket with code 4403.
* Events fan out through the bus (``app.realtime.bus``): Redis pub/sub between API processes,
  or in-process when ``REALTIME_BUS=memory``.
"""

import asyncio
import contextlib
import json
import logging
import uuid
from collections.abc import AsyncIterator, Callable, Generator
from typing import Annotated, Any, Protocol

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from redis.exceptions import RedisError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.core.database import get_db
from app.core.errors import AppError
from app.core.security import TokenError, decode_access_token
from app.models import User
from app.realtime import bus
from app.realtime.events import CHANNEL_MEMBER_REMOVED, MEMBERSHIP_REVOKED, Event
from app.services import channels as channel_service
from app.services.access import build_access_context, resolve_scope
from app.services.users import get_user

logger = logging.getLogger(__name__)

router = APIRouter()

AUTH_TIMEOUT_SECONDS = 10
CLOSE_UNAUTHENTICATED = 4401
CLOSE_REVOKED = 4403


# ── Fan-out: where a socket's events come from ──────────────────────────────────────────────
class Fanout(Protocol):
    async def add(self, workspace_id: uuid.UUID) -> None: ...
    def events(self) -> AsyncIterator[Event]: ...
    async def close(self) -> None: ...


class RedisFanout:
    def __init__(self, url: str) -> None:
        self._client = aioredis.Redis.from_url(url)
        self._pubsub = self._client.pubsub(ignore_subscribe_messages=True)

    async def add(self, workspace_id: uuid.UUID) -> None:
        await self._pubsub.subscribe(bus.channel_for(workspace_id))

    async def events(self) -> AsyncIterator[Event]:
        while True:
            if not self._pubsub.subscribed:
                await asyncio.sleep(0.2)
                continue
            message = await self._pubsub.get_message(timeout=1.0)
            if message is None:
                continue
            event = bus.decode(message["data"])
            if event is not None:
                yield event

    async def close(self) -> None:
        await self._pubsub.aclose()
        await self._client.aclose()


class MemoryFanout:
    def __init__(self, source: bus.InProcessEventBus) -> None:
        self._source = source
        self._queue: asyncio.Queue[Event] = asyncio.Queue()
        self._loop = asyncio.get_running_loop()
        self._unsubscribe: list[Callable[[], None]] = []

    async def add(self, workspace_id: uuid.UUID) -> None:
        def deliver(event: Event) -> None:  # may run on any thread
            self._loop.call_soon_threadsafe(self._queue.put_nowait, event)

        self._unsubscribe.append(self._source.subscribe(workspace_id, deliver))

    async def events(self) -> AsyncIterator[Event]:
        while True:
            yield await self._queue.get()

    async def close(self) -> None:
        for unsubscribe in self._unsubscribe:
            unsubscribe()


def make_fanout() -> Fanout:
    settings = get_settings()
    if settings.realtime_bus == "memory":
        return MemoryFanout(bus.memory_bus())
    return RedisFanout(settings.redis_url)


# ── The socket ──────────────────────────────────────────────────────────────────────────────
class _Session:
    """What one socket is subscribed to."""

    def __init__(self, user: User) -> None:
        self.user = user
        self.user_id = str(user.id)  # read without touching the DB from the forwarding task
        self.workspaces: set[uuid.UUID] = set()
        self.projects: set[uuid.UUID] = set()
        self.whole_workspaces: set[uuid.UUID] = set()
        self.channels: set[uuid.UUID] = set()

    def wants(self, event: Event) -> bool:
        if event.workspace_id not in self.workspaces:
            return False
        if event.channel_id is not None:
            if event.channel_id in self.channels:
                return True
            if event.data.get("private"):
                return False  # a private channel's events go to its checked subscribers only
        if event.project_id is None or event.workspace_id in self.whole_workspaces:
            return True
        return event.project_id in self.projects

    def unsubscribe(self, frame: dict[str, Any]) -> None:
        """Stop forwarding a project (or whole-workspace) subscription. Unknown ids are ignored.

        The workspace's bus channel stays subscribed: other projects in it may still be watched,
        and :meth:`wants` filters what is forwarded.
        """
        targets = (
            ("project_id", self.projects),
            ("workspace_id", self.whole_workspaces),
            ("channel_id", self.channels),
        )
        for key, subscriptions in targets:
            if frame.get(key) is None:
                continue
            with contextlib.suppress(ValueError):
                subscriptions.discard(uuid.UUID(str(frame[key])))


@contextlib.contextmanager
def _released(db: Session) -> Generator[None, None, None]:
    """End the read transaction so the socket does not hold a pooled connection while idle.

    The session lives as long as the socket; without this, its first query leaves a connection
    checked out ("idle in transaction") until disconnect, and a few dozen open tabs exhaust the
    pool for REST. Commit rather than roll back: with ``expire_on_commit=False`` loaded objects
    (the user) stay usable without a reload.
    """
    try:
        yield
    finally:
        try:
            db.commit()
        except Exception:
            db.rollback()


def _load_active_user(db: Session, subject: uuid.UUID) -> User | None:
    with _released(db):
        user = get_user(db, subject)
        return user if user is not None and user.is_active else None


async def _authenticate(websocket: WebSocket, db: Session) -> User | None:
    try:
        frame = await asyncio.wait_for(websocket.receive_json(), AUTH_TIMEOUT_SECONDS)
    except (TimeoutError, ValueError, WebSocketDisconnect):
        return None
    if not isinstance(frame, dict) or frame.get("type") != "auth":
        return None
    try:
        payload = decode_access_token(str(frame.get("token", "")))
    except TokenError:
        return None
    return await run_in_threadpool(_load_active_user, db, payload.subject)


def _check_subscription(
    db: Session, user: User, frame: dict[str, Any]
) -> tuple[uuid.UUID, uuid.UUID | None, uuid.UUID | None]:
    """The (workspace, project, channel) the user may watch, or :class:`AppError` (404/403).

    A ``channel_id`` subscription also checks the channel itself: a private channel the user is
    not listed on is ``not_found``, exactly like an unknown id.
    """
    params = {
        key: frame[key]
        for key in ("workspace_id", "project_id", "channel_id")
        if frame.get(key) is not None
    }
    if not params:
        raise AppError(
            "Give workspace_id, project_id or channel_id", status_code=400, code="scope_required"
        )
    with _released(db):
        db.expire_all()  # re-read membership and role, as every REST request does
        scope = resolve_scope(db, params)
        context = build_access_context(db, user, scope)
        if not context.can("view"):
            raise AppError("Forbidden", status_code=403, code="forbidden")
        channel_id = None
        if "channel_id" in params:
            channel = channel_service.get_visible_channel(
                db, uuid.UUID(str(params["channel_id"])), user
            )
            channel_id = channel.id
        return scope.workspace_id, scope.project_id, channel_id


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, db: Annotated[Session, Depends(get_db)]) -> None:
    await websocket.accept()
    user = await _authenticate(websocket, db)
    if user is None:
        await websocket.close(code=CLOSE_UNAUTHENTICATED)
        return
    await websocket.send_json({"type": "ready", "user_id": str(user.id)})

    state = _Session(user)
    fanout = make_fanout()
    forward = asyncio.create_task(_forward(websocket, fanout, state))
    try:
        while True:
            frame = await websocket.receive_json()
            if not isinstance(frame, dict):
                continue
            if frame.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
            elif frame.get("type") == "subscribe":
                await _subscribe(websocket, db, fanout, state, frame)
            elif frame.get("type") == "unsubscribe":
                state.unsubscribe(frame)
    except (WebSocketDisconnect, json.JSONDecodeError, RuntimeError):
        pass
    finally:
        forward.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await forward
        await fanout.close()


async def _subscribe(
    websocket: WebSocket, db: Session, fanout: Fanout, state: _Session, frame: dict[str, Any]
) -> None:
    try:
        workspace_id, project_id, channel_id = await run_in_threadpool(
            _check_subscription, db, state.user, frame
        )
    except AppError as error:
        await websocket.send_json({"type": "error", "code": error.code})
        return
    except Exception:  # a malformed id and the like: same answer as "not there"
        await websocket.send_json({"type": "error", "code": "not_found"})
        return
    if workspace_id not in state.workspaces:
        try:
            await fanout.add(workspace_id)
        except RedisError:
            logger.warning("Could not subscribe to workspace %s: Redis unavailable", workspace_id)
            await websocket.send_json({"type": "error", "code": "unavailable"})
            return
        state.workspaces.add(workspace_id)
    if channel_id is not None:
        state.channels.add(channel_id)  # channel events only, not the whole project
    elif project_id is None:
        state.whole_workspaces.add(workspace_id)
    else:
        state.projects.add(project_id)
    await websocket.send_json(
        {
            "type": "subscribed",
            "workspace_id": str(workspace_id),
            "project_id": str(project_id) if project_id else None,
            "channel_id": str(channel_id) if channel_id else None,
        }
    )


async def _forward(websocket: WebSocket, fanout: Fanout, state: _Session) -> None:
    async for event in fanout.events():
        if event.type == MEMBERSHIP_REVOKED and event.data.get("user_id") == state.user_id:
            await websocket.close(code=CLOSE_REVOKED)
            return
        if state.wants(event):
            await websocket.send_json({"type": "event", "event": event.model_dump(mode="json")})
        if (
            event.type == CHANNEL_MEMBER_REMOVED
            and event.channel_id is not None
            and event.data.get("user_id") == state.user_id
        ):
            state.channels.discard(event.channel_id)  # taken off a private channel: stop at once
