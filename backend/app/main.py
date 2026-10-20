"""FastAPI application entrypoint (Role 5 — Backend API & Orchestration)."""

import logging
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health
from app.api.router import api_router
from app.core.config import get_settings
from app.core.database import get_engine
from app.core.errors import install_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import (
    REQUEST_ID_HEADER,
    BodyLimit,
    MaxBodySizeMiddleware,
    RequestContextMiddleware,
)
from app.services.documents import too_large_message

logger = logging.getLogger(__name__)

# multipart framing (boundaries, part headers) on top of the file itself
MULTIPART_OVERHEAD_BYTES = 64 * 1024
# Uploads go to /api/v1/projects/{project_id}/documents (US-01).
UPLOAD_PATH = ("POST", re.compile(r"/api/v1/projects/[^/]+/documents"))


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logger.info("API starting (environment=%s)", settings.environment.value)
    yield
    get_engine().dispose()
    logger.info("API stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings)

    app = FastAPI(
        title="AI Requirements Conflict Detector API",
        version="0.1.0",
        lifespan=lifespan,
        # Interactive docs are handy in development but are attack surface in production.
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None if settings.is_production else "/redoc",
        openapi_url=None if settings.is_production else "/openapi.json",
    )

    # Middleware order: the last one added is outermost. The body-size guard is added first so
    # it sits *inside* CORS — its 413 responses still carry CORS headers and stay readable by
    # the browser — and request-id/logging (added last) wraps everything.
    app.add_middleware(
        MaxBodySizeMiddleware,
        limits={
            UPLOAD_PATH: BodyLimit(
                max_bytes=settings.max_upload_size_bytes + MULTIPART_OVERHEAD_BYTES,
                message=too_large_message(settings.max_upload_size_mb),
            )
        },
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", REQUEST_ID_HEADER],
        expose_headers=[REQUEST_ID_HEADER],
        allow_credentials=False,  # bearer tokens travel in a header, not cookies
    )
    app.add_middleware(RequestContextMiddleware)

    install_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(api_router)
    return app


app = create_app()
