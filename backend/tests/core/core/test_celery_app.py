"""Celery configuration guard rails (no broker needed)."""

from app.core.celery_app import celery_app
from app.core.tasks import ping


def test_only_json_is_accepted() -> None:
    """Pickle would let anyone who can write to Redis execute code on the worker."""
    assert celery_app.conf.accept_content == ["json"]
    assert celery_app.conf.task_serializer == "json"
    assert celery_app.conf.result_serializer == "json"


def test_tasks_are_acked_late_and_time_limited() -> None:
    conf = celery_app.conf
    assert conf.task_acks_late is True
    assert conf.task_reject_on_worker_lost is True
    assert 0 < conf.task_soft_time_limit < conf.task_time_limit


def test_system_ping_is_registered_and_runs() -> None:
    assert "system.ping" in celery_app.tasks
    assert ping() == "pong"
