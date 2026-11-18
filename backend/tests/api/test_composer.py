"""The composer's *Propose* (Bansil — US-30, US-36, FR-55, FR-59, FR-60): a Proposed requirement
with a printed ID, posted as a card in the right channel, its owner and group defaulted, its live
analysis queued in the same transaction."""

from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import DefaultRole
from app.core.rate_limit import InMemoryRateLimiter, get_rate_limiter
from app.models import (
    AnalysisRun,
    AnalysisRunStatus,
    AnalysisScope,
    Channel,
    Membership,
    Message,
    Project,
    Requirement,
    User,
)
from app.services import analysis_orchestrator as orchestrator
from tests.api.conftest import headers_for

FIELDS: dict[str, Any] = {
    "template": "event_driven",
    "slots": {
        "trigger": "the user is inactive for 5 minutes",
        "system": "mobile app",
        "response": "log the user out",
    },
    "type": "functional",
    "priority": "must",
    "tags": ["session"],
    "rationale": "RBI guideline on idle sessions",
    "acceptance_criteria": [
        {"given": "a logged-in user", "when": "no input for 5 min", "then": "the session ends"}
    ],
}


@pytest.fixture(autouse=True)
def limiter(client: TestClient) -> Iterator[None]:
    from app.main import app

    app.dependency_overrides[get_rate_limiter] = InMemoryRateLimiter
    yield
    app.dependency_overrides.pop(get_rate_limiter, None)


@pytest.fixture
def general(db_session: Session, project: Project) -> Channel:
    channel = Channel(project_id=project.id, name="general", is_default=True)
    db_session.add(channel)
    db_session.commit()
    return channel


def propose(client: TestClient, project: Project, who: User, **fields: Any) -> Any:
    return client.post(
        f"/api/v1/projects/{project.id}/requirements",
        json={"fields": {**FIELDS, **fields}},
        headers=headers_for(who),
    )


def set_group(db: Session, user: User, group: str) -> None:
    membership = db.scalar(select(Membership).where(Membership.user_id == user.id))
    assert membership is not None
    membership.stakeholder_group = group
    db.commit()


def test_proposing_posts_a_card_with_a_numbered_requirement_and_queues_its_analysis(
    client: TestClient,
    db_session: Session,
    project: Project,
    general: Channel,
    make_user: Callable[..., User],
    followups: list[tuple[str, list[str]]],
) -> None:
    author = make_user(role=DefaultRole.STAKEHOLDER)

    response = propose(client, project, author)

    assert response.status_code == 201, response.text
    body = response.json()
    requirement = body["requirement"]
    assert requirement["source_req_id"] == "REQ-001"
    assert (requirement["state"], requirement["origin"]) == ("Proposed", "post")
    assert requirement["owner_id"] == str(author.id)
    assert body["message"]["channel_id"] == str(general.id)
    assert body["message"]["payload"] == {
        "requirement_id": requirement["requirement_id"],
        "label": "REQ-001",
    }
    run = db_session.get(AnalysisRun, body["analysis_run_id"])
    assert run is not None
    assert (run.scope, run.status) == (AnalysisScope.REQUIREMENT, AnalysisRunStatus.QUEUED)
    assert (orchestrator.RUN_REQUIREMENT, [str(run.id)]) in followups


def test_posts_continue_the_projects_numbering(
    client: TestClient,
    db_session: Session,
    project: Project,
    general: Channel,
    user: User,
    make_requirement: Callable[..., Requirement],
) -> None:
    make_requirement("x", source_req_id="REQ-060")
    make_requirement("y", source_req_id="FR-2.1")  # another scheme does not count

    first = propose(client, project, user).json()["requirement"]["source_req_id"]
    second = propose(client, project, user).json()["requirement"]["source_req_id"]

    assert (first, second) == ("REQ-061", "REQ-062")


def test_owner_and_group_default_to_the_author_and_can_be_chosen(
    client: TestClient,
    db_session: Session,
    project: Project,
    general: Channel,
    user: User,
    make_user: Callable[..., User],
) -> None:
    set_group(db_session, user, "Payments")
    colleague = make_user(role=DefaultRole.DEVELOPER)

    defaulted = propose(client, project, user).json()["requirement"]
    chosen = propose(
        client, project, user, owner_id=str(colleague.id), stakeholder_group="Security"
    ).json()["requirement"]

    assert (defaulted["owner_id"], defaulted["stakeholder_group"]) == (str(user.id), "Payments")
    assert (chosen["owner_id"], chosen["stakeholder_group"]) == (str(colleague.id), "Security")


def test_the_card_goes_to_the_groups_channel_when_there_is_one(
    client: TestClient,
    db_session: Session,
    project: Project,
    general: Channel,
    user: User,
) -> None:
    security = Channel(project_id=project.id, name="security")
    db_session.add(security)
    db_session.commit()

    response = propose(client, project, user, stakeholder_group="Security")

    assert response.json()["message"]["channel_id"] == str(security.id)


def test_a_chosen_channel_must_be_in_the_project(
    client: TestClient,
    db_session: Session,
    project: Project,
    general: Channel,
    user: User,
    make_project: Callable[..., Project],
) -> None:
    elsewhere = Channel(project_id=make_project().id, name="other")
    db_session.add(elsewhere)
    db_session.commit()

    response = propose(client, project, user, channel_id=str(elsewhere.id))

    assert response.status_code == 404
    assert (
        db_session.scalar(select(Requirement).where(Requirement.project_id == project.id)) is None
    )


def test_without_any_channel_the_composer_is_told_to_choose(
    client: TestClient, project: Project, user: User
) -> None:
    response = propose(client, project, user)

    assert response.status_code == 409 and response.json()["error"]["code"] == "no_channel"


@pytest.mark.parametrize("role", [DefaultRole.VIEWER, DefaultRole.COMPLIANCE_REVIEWER])
def test_members_who_cannot_propose_get_403_and_nothing_is_stored(
    client: TestClient,
    db_session: Session,
    project: Project,
    general: Channel,
    make_user: Callable[..., User],
    role: DefaultRole,
) -> None:
    response = propose(client, project, make_user(role=role))

    assert response.status_code == 403
    assert db_session.scalar(select(Message)) is None


def test_a_non_member_gets_404(
    client: TestClient,
    project: Project,
    general: Channel,
    make_user: Callable[..., User],
    make_workspace: Callable[..., Any],
) -> None:
    outsider = make_user(role=DefaultRole.OWNER, workspace=make_workspace())

    assert propose(client, project, outsider).status_code == 404


def test_imported_requirements_belong_to_their_uploader(
    db_session: Session, project: Project, user: User
) -> None:
    from app.ingestion import Requirement as ExtractedRequirement
    from app.models import Document, DocumentFormat
    from app.services.processing import _to_row

    document = Document(
        workspace_id=project.workspace_id,
        project_id=project.id,
        uploaded_by=user.id,
        filename="srs.docx",
        format=DocumentFormat.DOCX,
        size_bytes=1,
        sha256="2" * 64,
        storage_path="srs.docx",
    )

    item = ExtractedRequirement(
        id="REQ-001",
        source_req_id="REQ-001",
        raw_text="The system shall log logins.",
        source_document="srs.docx",
        location="paragraph 1",
    )

    row = _to_row(document, 0, item)

    assert row is not None and row.owner_id == user.id
