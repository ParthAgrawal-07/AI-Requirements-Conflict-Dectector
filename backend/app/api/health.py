"""Liveness and readiness probes (Role 5).

* ``/health``        — the process is up. Used by orchestrator *liveness* checks; touches nothing.
* ``/health/ready``  — dependencies (PostgreSQL, Redis) answer. Used by deploy/readiness checks
                       and the docker-compose smoke test. Returns 503 when degraded.
"""

import logging

import redis
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import get_engine

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
def liveness() -> dict[str, str]:
    return {"status": "ok"}


def _check_database() -> bool:
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        logger.exception("Readiness: database check failed")
        return False


def _check_redis() -> bool:
    client = redis.Redis.from_url(
        get_settings().redis_url, socket_connect_timeout=2, socket_timeout=2
    )
    try:
        return bool(client.ping())
    except Exception:
        logger.exception("Readiness: redis check failed")
        return False
    finally:
        client.close()


@router.get("/health/ready")
def readiness() -> JSONResponse:
    checks = {
        "database": "ok" if _check_database() else "error",
        "redis": "ok" if _check_redis() else "error",
    }
    healthy = all(value == "ok" for value in checks.values())
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={"status": "ready" if healthy else "degraded", "checks": checks},
    )
