"""Request context middleware (Role 5): request IDs, access log, basic response hardening."""

import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass

from fastapi import HTTPException, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import error_response
from app.core.logging import request_id_var

logger = logging.getLogger("app.access")

REQUEST_ID_HEADER = "X-Request-ID"
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
_QUIET_PATHS = frozenset({"/health", "/health/ready"})  # probes would drown real traffic


class RequestContextMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        request_id = incoming if _SAFE_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        request.state.request_id = request_id
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            elapsed_ms = (time.perf_counter() - started) * 1000
            request_id_var.reset(token)
        response.headers[REQUEST_ID_HEADER] = request_id
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        if request.url.path not in _QUIET_PATHS:
            logger.info(
                "%s %s -> %d (%.1f ms)",
                request.method,
                request.url.path,
                response.status_code,
                elapsed_ms,
                extra={"request_id": request_id},
            )
        return response


@dataclass(frozen=True)
class BodyLimit:
    max_bytes: int
    message: str


class MaxBodySizeMiddleware:
    """Reject oversized request bodies with 413 *before* they are read (pure ASGI).

    Why this exists: FastAPI parses a multipart body — spooling an uploaded file to disk —
    before the route function runs, so a size check inside the endpoint alone lets a client
    make the server write gigabytes first. This middleware stops that in two ways:

    * a ``Content-Length`` above the limit is refused immediately, reading nothing;
    * a body without ``Content-Length`` (chunked transfer) is counted as it streams in and
      aborted the moment it crosses the limit.

    Only the (method, path) pairs listed in ``limits`` are guarded, so it never surprises other
    endpoints. A path is either an exact string or a compiled regular expression that must match
    the whole path (needed for ``/projects/{id}/documents``). The limit should be the file limit
    plus multipart framing overhead; the endpoint still enforces the exact file size.
    """

    def __init__(
        self, app: ASGIApp, *, limits: Mapping[tuple[str, str | re.Pattern[str]], BodyLimit]
    ) -> None:
        self.app = app
        self.limits: dict[tuple[str, str], BodyLimit] = {}
        self.pattern_limits: list[tuple[str, re.Pattern[str], BodyLimit]] = []
        for (method, path), body_limit in limits.items():
            if isinstance(path, re.Pattern):
                self.pattern_limits.append((method, path, body_limit))
            else:
                self.limits[(method, path)] = body_limit

    def _limit_for(self, scope: Scope) -> BodyLimit | None:
        if scope["type"] != "http":
            return None
        method, path = scope["method"], scope["path"]
        exact = self.limits.get((method, path))
        if exact is not None:
            return exact
        for pattern_method, pattern, body_limit in self.pattern_limits:
            if pattern_method == method and pattern.fullmatch(path):
                return body_limit
        return None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        limit = self._limit_for(scope)
        if limit is None:
            await self.app(scope, receive, send)
            return

        declared = _declared_length(scope)
        if declared is not None and declared > limit.max_bytes:
            response = error_response(
                Request(scope),
                status_code=413,
                code="payload_too_large",
                message=limit.message,
                headers={"Connection": "close"},
            )
            await response(scope, receive, send)
            return

        received = 0

        async def counting_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit.max_bytes:
                    # FastAPI's HTTPException specifically: FastAPI re-raises it from body
                    # parsing as-is, whereas any other exception becomes a generic 400.
                    raise HTTPException(status_code=413, detail=limit.message)
            return message

        await self.app(scope, counting_receive, send)


def _declared_length(scope: Scope) -> int | None:
    for name, value in scope["headers"]:
        if name == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None
    return None
