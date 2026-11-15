"""``POST /projects/{p}/similar`` (Heet — FR-83): similar-requirement hints for the composer."""

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.permissions import DefaultRole
from app.embeddings.model import HashingEmbedder, get_embedder
from app.embeddings.store import embed_document
from app.models import Project, Requirement, User, Workspace
from tests.api.conftest import headers_for

TIMEOUT = "API requests shall time out after 2 seconds."


@pytest.fixture
def api(client: TestClient) -> Iterator[TestClient]:
    from app.main import app

    app.dependency_overrides[get_embedder] = HashingEmbedder
    yield client
    app.dependency_overrides.pop(get_embedder, None)


@pytest.fixture
def embedded(db_session: Session, make_requirement: Callable[..., Requirement]) -> Requirement:
    requirement = make_requirement(TIMEOUT, source_req_id="REQ-014")
    assert requirement.document_id is not None
    embed_document(db_session, requirement.document_id, HashingEmbedder())
    return requirement


def url(project: Project) -> str:
    return f"/api/v1/projects/{project.id}/similar"


def test_a_contributor_gets_the_closest_requirements_with_a_preview(
    api: TestClient, project: Project, embedded: Requirement, make_user: Callable[..., User]
) -> None:
    developer = make_user(role=DefaultRole.DEVELOPER)

    response = api.post(
        url(project),
        json={"text": "API requests shall time out after 10 seconds."},
        headers=headers_for(developer),
    )

    assert response.status_code == 200
    (hint,) = response.json()["hints"]
    assert hint["requirement_id"] == str(embedded.id)
    assert hint["label"] == "REQ-014"
    assert hint["preview"] == TIMEOUT
    assert hint["state"] == "Proposed"


@pytest.mark.parametrize("role", [DefaultRole.VIEWER, DefaultRole.COMPLIANCE_REVIEWER])
def test_members_who_cannot_propose_are_refused(
    api: TestClient, project: Project, make_user: Callable[..., User], role: DefaultRole
) -> None:
    response = api.post(
        url(project), json={"text": TIMEOUT}, headers=headers_for(make_user(role=role))
    )

    assert response.status_code == 403


def test_a_non_member_gets_404(
    api: TestClient,
    project: Project,
    make_user: Callable[..., User],
    make_workspace: Callable[..., Workspace],
) -> None:
    outsider = make_user(workspace=make_workspace())

    response = api.post(url(project), json={"text": TIMEOUT}, headers=headers_for(outsider))

    assert response.status_code == 404


def test_empty_text_is_rejected(api: TestClient, project: Project, user: User) -> None:
    response = api.post(url(project), json={"text": ""}, headers=headers_for(user))

    assert response.status_code == 422


def test_hints_never_come_from_another_project(
    api: TestClient,
    db_session: Session,
    make_project: Callable[..., Project],
    embedded: Requirement,
    user: User,
) -> None:
    other = make_project()

    response = api.post(url(other), json={"text": TIMEOUT}, headers=headers_for(user))

    assert response.status_code == 200
    assert response.json()["hints"] == []
