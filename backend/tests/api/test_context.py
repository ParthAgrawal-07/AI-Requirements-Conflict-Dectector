"""Project context routes (US-60; design update §12.5)."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.permissions import DefaultRole
from app.models import (
    Document,
    DocumentFormat,
    DocumentSection,
    DocumentStatus,
    Project,
    ProjectStatus,
    User,
)

FULL = {
    "purpose": "Mobile banking for retail customers.",
    "scope_in": "Accounts and transfers.",
    "scope_out": "Loans.",
    "actors": ["Customer"],
    "environment": "Android and iOS.",
}

Headers = Callable[[DefaultRole], dict[str, str]]


def url(project: Project, suffix: str = "") -> str:
    return f"/api/v1/projects/{project.id}/context{suffix}"


@pytest.fixture
def setup_project(make_project: Callable[..., Project]) -> Project:
    return make_project(status=ProjectStatus.SETUP)


def test_a_new_project_shows_every_field_missing(
    client: TestClient, setup_project: Project, as_role: Headers
) -> None:
    response = client.get(url(setup_project), headers=as_role(DefaultRole.VIEWER))
    assert response.status_code == 200
    body = response.json()
    assert body["project_status"] == "setup" and body["latest"] is None
    assert body["required_confirmed"] == 0 and body["required_total"] == 4
    assert body["missing_fields"][0] == "Purpose and problem"
    assert [f["field"] for f in body["fields"] if f["required"]] == [
        "purpose",
        "scope",
        "actors",
        "environment",
    ]


def test_a_manager_confirms_the_brief_and_the_project_becomes_active(
    client: TestClient, setup_project: Project, as_role: Headers
) -> None:
    headers = as_role(DefaultRole.PROJECT_MANAGER)
    response = client.put(url(setup_project), json={"fields": FULL}, headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["activated"] is True and body["created"] is True
    assert body["context"]["project_status"] == "active"
    assert body["context"]["context_version"] == 1
    assert body["context"]["missing_fields"] == []

    project = client.get(f"/api/v1/projects/{setup_project.id}", headers=headers).json()
    assert project["analysis_enabled"] is True and project["context_version"] == 1


def test_editing_an_active_context_needs_a_reason_and_reports_open_findings(
    client: TestClient, setup_project: Project, as_role: Headers
) -> None:
    headers = as_role(DefaultRole.PROJECT_MANAGER)
    client.put(url(setup_project), json={"fields": FULL}, headers=headers)

    change = {"fields": {"environment": "Web too."}}
    refused = client.put(url(setup_project), json=change, headers=headers)
    assert refused.status_code == 400
    assert refused.json()["error"]["code"] == "context_reason_required"

    saved = client.put(
        url(setup_project), json={**change, "reason": "New channel"}, headers=headers
    )
    assert saved.status_code == 200
    assert saved.json()["open_findings_to_rerun"] == 0
    versions = client.get(url(setup_project, "/versions"), headers=headers).json()
    assert versions["total"] == 2
    assert [v["version"] for v in versions["items"]] == [2, 1]
    assert versions["items"][0]["reason"] == "New channel"


@pytest.mark.parametrize(
    "role", [DefaultRole.BUSINESS_ANALYST, DefaultRole.DEVELOPER, DefaultRole.VIEWER]
)
def test_only_holders_of_project_context_may_write(
    client: TestClient, setup_project: Project, as_role: Headers, role: DefaultRole
) -> None:
    response = client.put(url(setup_project), json={"fields": FULL}, headers=as_role(role))
    assert response.status_code == 403


def test_another_workspace_cannot_see_the_context(
    client: TestClient,
    make_workspace: Callable[..., object],
    make_project: Callable[..., Project],
    as_role: Headers,
) -> None:
    other = make_project(workspace=make_workspace(), status=ProjectStatus.SETUP)
    response = client.get(url(other), headers=as_role(DefaultRole.OWNER))
    assert response.status_code == 404


def test_unknown_brief_fields_are_rejected(
    client: TestClient, setup_project: Project, as_role: Headers
) -> None:
    response = client.put(
        url(setup_project),
        json={"fields": {"status": "active"}},
        headers=as_role(DefaultRole.PROJECT_MANAGER),
    )
    assert response.status_code == 422


def _document(db: Session, project: Project, user: User, status: DocumentStatus) -> Document:
    document = Document(
        workspace_id=project.workspace_id,
        project_id=project.id,
        uploaded_by=user.id,
        filename="srs.docx",
        format=DocumentFormat.DOCX,
        size_bytes=10,
        sha256="0" * 64,
        storage_path="x/srs.docx",
        status=status,
    )
    db.add(document)
    db.commit()
    return document


def test_a_manager_can_draft_the_brief_from_a_processed_document(
    client: TestClient,
    db_session: Session,
    setup_project: Project,
    make_user: Callable[..., User],
    as_role: Headers,
) -> None:
    document = _document(db_session, setup_project, make_user(), DocumentStatus.DONE)
    db_session.add(
        DocumentSection(
            document_id=document.id,
            project_id=setup_project.id,
            heading="1.1 Purpose",
            body="PayLite is a bank app.",
            order_index=0,
        )
    )
    db_session.commit()

    response = client.post(
        url(setup_project, "/draft"),
        json={"document_id": str(document.id)},
        headers=as_role(DefaultRole.PROJECT_MANAGER),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["drafted"] is True
    latest = body["context"]["latest"]
    assert latest["values"]["purpose"] == "PayLite is a bank app."
    assert latest["field_status"] == {"purpose": "ai_drafted"}
    assert latest["source_document_id"] == str(document.id)
    assert body["context"]["project_status"] == "setup"


def test_drafting_from_an_unprocessed_document_is_a_conflict(
    client: TestClient,
    db_session: Session,
    setup_project: Project,
    make_user: Callable[..., User],
    as_role: Headers,
) -> None:
    document = _document(db_session, setup_project, make_user(), DocumentStatus.PROCESSING)
    response = client.post(
        url(setup_project, "/draft"),
        json={"document_id": str(document.id)},
        headers=as_role(DefaultRole.PROJECT_MANAGER),
    )
    assert response.status_code == 409


def test_the_composer_templates_are_served_to_any_signed_in_user(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.get("/api/v1/composer/templates", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()[1]["pattern"] == "When {trigger}, the {system} shall {response}."
    assert client.get("/api/v1/composer/templates").status_code == 401
