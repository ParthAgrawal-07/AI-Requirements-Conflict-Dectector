"""Leaving Setup analyses what was uploaded meanwhile (FR-103; orchestration, Parth)."""

import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.permissions import DefaultRole
from app.models import Project, ProjectStatus
from app.services import analysis_orchestrator
from tests.api.test_context import FULL, url

Headers = Callable[[DefaultRole], dict[str, str]]


def test_confirming_the_brief_queues_the_projects_analysis(
    client: TestClient,
    db_session: Session,
    make_project: Callable[..., Project],
    as_role: Headers,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = make_project(status=ProjectStatus.SETUP)
    queued: list[uuid.UUID] = []
    monkeypatch.setattr(
        analysis_orchestrator,
        "analyse_project",
        lambda db, project_id: queued.append(project_id) or 0,
    )
    headers = as_role(DefaultRole.PROJECT_MANAGER)

    first = client.put(url(project), json={"fields": FULL}, headers=headers)
    assert first.json()["activated"] is True
    again = client.put(
        url(project), json={"fields": {"purpose": "Changed."}, "reason": "typo"}, headers=headers
    )
    assert again.status_code == 200

    assert queued == [project.id]  # only when the project becomes active
