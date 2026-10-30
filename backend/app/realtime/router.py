"""Authenticated WebSocket gateway for project events.

Client protocol: connect to /ws/projects/{project_id}; then send the first JSON message
{"type": "auth", "token": "<access-token>"}. This socket only delivers events; it does
not accept application writes. Redis Pub/Sub is not durable, so clients need REST recovery.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from contextlib import suppress

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings
from app.core.database import get_sessionmaker
from app.core.security import TokenError, decode_access_token
from app.models import Project
from app.realtime.events import project_channel
from app.services.access import active_membership
from app.services.users import get_user

logger = logging.getLogger(__name__)
router = APIRouter()
AUTH_TIMEOUT_SECONDS = 10
MAX_AUTH_MESSAGE_BYTES = 8192


def _is_authorised(project_id: uuid.UUID, token: str) -> bool:
    try:
        payload = decode_access_token(token)
    except (TokenError, ValueError):
        return False
    with get_sessionmaker()() as db:
        user = get_user(db, payload.subject)
        if user is None or not user.is_active:
            return False
        project = db.get(Project, project_id)
        if project is None:
            return False
        return active_membership(db, user.id, project.workspace_id) is not None


@router.websocket("/ws/projects/{project_id}")
async def project_events(websocket: WebSocket, project_id: uuid.UUID) -> None:
    settings = get_settings()
    origin = websocket.headers.get("origin")
    if origin and origin not in settings.cors_allowed_origins:
        await websocket.close(code=1008, reason="Origin not allowed")
        return

    await websocket.accept()
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=AUTH_TIMEOUT_SECONDS)
        if len(raw.encode("utf-8")) > MAX_AUTH_MESSAGE_BYTES:
            await websocket.close(code=1008, reason="Authentication message too large")
            return
        message = json.loads(raw)
        if not isinstance(message, dict) or message.get("type") != "auth":
            await websocket.close(code=1008, reason="Authentication required")
            return
        token = message.get("token")
        if not isinstance(token, str) or not _is_authorised(project_id, token):
            await websocket.close(code=1008, reason="Invalid authentication or project access")
            return
    except (TimeoutError, json.JSONDecodeError, WebSocketDisconnect, RuntimeError):
        with suppress(RuntimeError):
            await websocket.close(code=1008, reason="Invalid authentication message")
        return

    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    pubsub = redis.pubsub()
    channel = project_channel(project_id)
    try:
        await pubsub.subscribe(channel)
        await websocket.send_json({"type": "ready", "project_id": str(project_id)})
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and message.get("type") == "message":
                try:
                    payload = json.loads(message["data"])
                except (TypeError, json.JSONDecodeError):
                    logger.warning("Ignoring malformed Redis event for project %s", project_id)
                    continue
                await websocket.send_json(payload)
    except (WebSocketDisconnect, RedisError, RuntimeError):
        logger.debug("WebSocket closed for project %s", project_id)
    finally:
        with suppress(Exception):
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()
            await redis.aclose()
