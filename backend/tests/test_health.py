"""Liveness/readiness probes."""

import pytest
from fastapi.testclient import TestClient


def test_liveness_needs_no_dependencies(plain_client: TestClient) -> None:
    response = plain_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_reports_ok_when_dependencies_are_up(client: TestClient) -> None:
    response = client.get("/health/ready")
    body = response.json()
    if body["checks"]["redis"] != "ok":
        pytest.skip("Redis not available in this environment")
    assert response.status_code == 200
    assert body == {"status": "ready", "checks": {"database": "ok", "redis": "ok"}}


@pytest.mark.parametrize(("db_ok", "redis_ok"), [(False, True), (True, False), (False, False)])
def test_readiness_returns_503_when_a_dependency_is_down(
    plain_client: TestClient, monkeypatch: pytest.MonkeyPatch, db_ok: bool, redis_ok: bool
) -> None:
    monkeypatch.setattr("app.api.health._check_database", lambda: db_ok)
    monkeypatch.setattr("app.api.health._check_redis", lambda: redis_ok)

    response = plain_client.get("/health/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"]["database"] == ("ok" if db_ok else "error")
    assert body["checks"]["redis"] == ("ok" if redis_ok else "error")
