"""System tasks (Role 5)."""

from app.core.celery_app import celery_app


@celery_app.task(name="system.ping")
def ping() -> str:
    """Round-trips API -> Redis -> worker; used by the smoke test to prove the queue works."""
    return "pong"


@celery_app.task(name="security.expire_join_codes")
def expire_join_codes() -> int:
    """Periodically transition stale active join codes past their expiry date to EXPIRED.

    Bounded transaction scope via session context manager; safe for repeat executions.
    """
    from app.core.database import get_sessionmaker
    from app.services.join_codes import JoinCodeService

    session_maker = get_sessionmaker()
    with session_maker() as db:
        return JoinCodeService.expire_stale_codes(db)
