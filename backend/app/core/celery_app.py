"""Celery application (Role 5 — async orchestration, US-03).

Start a worker with::

    celery -A app.core.celery_app worker --loglevel=INFO

Each pipeline role adds its tasks in a ``tasks.py`` inside its own package
(``app/ingestion/tasks.py``, ``app/embeddings/tasks.py`` ...); they are discovered
automatically, so nothing here needs editing when a role ships its first task.
"""

from celery import Celery
from celery.signals import setup_logging

from app.core.config import get_settings
from app.core.logging import configure_logging

settings = get_settings()

celery_app = Celery("rcd", broker=settings.redis_url, backend=settings.redis_url)

celery_app.conf.update(
    # Serialisation: JSON only — never pickle (arbitrary code execution if Redis is reachable).
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Reliability: a task is acknowledged after it finishes, and re-queued if the worker dies.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,  # long LLM/embedding tasks: don't hoard queued work
    # Guard rails so a stuck LLM call can't wedge a worker forever.
    task_soft_time_limit=15 * 60,
    task_time_limit=20 * 60,
    result_expires=24 * 60 * 60,
    task_track_started=True,  # exposes the STARTED state for progress polling (US-03)
    broker_connection_retry_on_startup=True,
    worker_hijack_root_logger=False,
)

celery_app.autodiscover_tasks(
    ["app.core", "app.ingestion", "app.embeddings", "app.classification", "app.clarification"]
)


@setup_logging.connect
def _configure_worker_logging(**_: object) -> None:
    # Connecting to this signal stops Celery installing its own logging config.
    configure_logging(get_settings())
