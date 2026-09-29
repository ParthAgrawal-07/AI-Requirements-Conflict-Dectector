"""System tasks (Role 5)."""

from app.core.celery_app import celery_app


@celery_app.task(name="system.ping")
def ping() -> str:
    """Round-trips API -> Redis -> worker; used by the smoke test to prove the queue works."""
    return "pong"
