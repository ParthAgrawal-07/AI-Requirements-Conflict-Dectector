"""The ContextGate: no analysis while a project is in Setup (FR-103, US-60, Sprint 1 task)."""

import pytest

from app.core.errors import ConflictError
from app.models import Project, ProjectStatus
from app.services.projects import ProjectInSetupError, ensure_project_active, is_analysis_enabled


def _project(status: ProjectStatus) -> Project:
    return Project(name="P", status=status)


def test_an_active_project_passes_the_gate() -> None:
    ensure_project_active(_project(ProjectStatus.ACTIVE))
    assert is_analysis_enabled(_project(ProjectStatus.ACTIVE))


@pytest.mark.parametrize("status", [ProjectStatus.SETUP, ProjectStatus.ARCHIVED])
def test_a_project_that_is_not_active_is_stopped(status: ProjectStatus) -> None:
    with pytest.raises(ProjectInSetupError) as raised:
        ensure_project_active(_project(status))
    assert not is_analysis_enabled(_project(status))
    assert raised.value.status_code == 409
    assert raised.value.code == "project_in_setup"


def test_the_error_is_a_conflict_so_callers_can_catch_the_family() -> None:
    assert issubclass(ProjectInSetupError, ConflictError)


def test_the_message_names_what_the_manager_still_has_to_do() -> None:
    with pytest.raises(ProjectInSetupError) as raised:
        ensure_project_active(
            _project(ProjectStatus.SETUP), missing_fields=["Domain", "Primary users"]
        )
    assert "Missing: Domain, Primary users." in str(raised.value)
    assert raised.value.missing_fields == ["Domain", "Primary users"]


def test_without_missing_fields_the_message_still_explains_setup() -> None:
    with pytest.raises(ProjectInSetupError) as raised:
        ensure_project_active(_project(ProjectStatus.SETUP))
    assert "Setup" in str(raised.value) and "Missing" not in str(raised.value)


def test_the_gate_error_renders_as_a_409_with_its_own_code() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.core.errors import install_exception_handlers

    app = FastAPI()
    install_exception_handlers(app)

    @app.get("/analyse")
    def analyse() -> None:
        ensure_project_active(_project(ProjectStatus.SETUP), missing_fields=["Domain"])

    response = TestClient(app).get("/analyse")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "project_in_setup"
    assert "Domain" in response.json()["error"]["message"]
