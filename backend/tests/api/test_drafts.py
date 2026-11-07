"""Requirement drafts (FR-81): the composer's private autosave, and posting a requirement."""

from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import DefaultRole
from app.core.rate_limit import InMemoryRateLimiter, get_rate_limiter
from app.models import (
    AuditAction,
    AuditLog,
    Channel,
    Message,
    MessageKind,
    Project,
    Requirement,
    RequirementVersion,
    User,
    Workspace,
)
from app.realtime import bus
from app.realtime.events import MESSAGE_CREATED
from tests.api.conftest import headers_for

DRAFTS = "/api/v1/me/drafts"
EVENT_DRIVEN = {
    "template": "event_driven",
    "slots": {
        "trigger": "the user is inactive for 5 minutes",
        "system": "mobile app",
        "response": "log the user out",
    },
    "type": "functional",
    "priority": "must",
    "stakeholder_group": "Security",
    "acceptance_criteria": [
        {"given": "a logged-in user", "when": "no input for 5 min", "then": "the session ends"}
    ],
}
STATEMENT = "When the user is inactive for 5 minutes, the mobile app shall log the user out."


@pytest.fixture(autouse=True)
def limiter(client: TestClient) -> Iterator[InMemoryRateLimiter]:
    from app.main import app

    in_memory = InMemoryRateLimiter()
    app.dependency_overrides[get_rate_limiter] = lambda: in_memory
    yield in_memory
    app.dependency_overrides.pop(get_rate_limiter, None)


@pytest.fixture
def channel(db_session: Session, project: Project) -> Channel:
    channel = Channel(project_id=project.id, name="general", is_default=True)
    db_session.add(channel)
    db_session.commit()
    return channel


def _create(client: TestClient, user: User, project: Project, fields: dict[str, Any]) -> Any:
    return client.post(
        DRAFTS, json={"project_id": str(project.id), "fields": fields}, headers=headers_for(user)
    )


class TestDrafts:
    def test_autosave_round_trip(self, client: TestClient, project: Project, user: User) -> None:
        created = _create(client, user, project, {"template": "event_driven", "slots": {}})
        assert created.status_code == 201
        draft = created.json()
        assert draft["preview"] is None  # slots still empty

        saved = client.patch(
            f"{DRAFTS}/{draft['id']}", json={"fields": EVENT_DRIVEN}, headers=headers_for(user)
        )

        assert saved.status_code == 200
        assert saved.json()["preview"] == STATEMENT
        reread = client.get(f"{DRAFTS}/{draft['id']}", headers=headers_for(user)).json()
        assert reread["fields"]["slots"] == EVENT_DRIVEN["slots"]
        assert reread["fields"]["acceptance_criteria"][0]["then"] == "the session ends"
        listed = client.get(DRAFTS, params={"project": str(project.id)}, headers=headers_for(user))
        assert [d["id"] for d in listed.json()] == [draft["id"]]

        assert (
            client.delete(f"{DRAFTS}/{draft['id']}", headers=headers_for(user)).status_code == 204
        )
        assert client.get(f"{DRAFTS}/{draft['id']}", headers=headers_for(user)).status_code == 404

    def test_drafts_are_private(
        self, client: TestClient, project: Project, user: User, make_user: Callable[..., User]
    ) -> None:
        draft = _create(client, user, project, {}).json()
        colleague = make_user(role=DefaultRole.OWNER)

        assert (
            client.get(f"{DRAFTS}/{draft['id']}", headers=headers_for(colleague)).status_code == 404
        )
        assert client.get(DRAFTS, headers=headers_for(colleague)).json() == []

    def test_unknown_fields_are_rejected(
        self, client: TestClient, project: Project, user: User
    ) -> None:
        assert _create(client, user, project, {"colour": "red"}).status_code == 422

    def test_a_project_of_another_workspace_is_a_404(
        self,
        client: TestClient,
        user: User,
        make_project: Callable[..., Project],
        make_workspace: Callable[..., Workspace],
    ) -> None:
        foreign = make_project(workspace=make_workspace())
        assert _create(client, user, foreign, {}).status_code == 404

    def test_a_former_member_loses_access_to_their_drafts(
        self,
        client: TestClient,
        workspace: Workspace,
        project: Project,
        user: User,
    ) -> None:
        draft = _create(client, user, project, {}).json()
        client.post(f"/api/v1/workspaces/{workspace.id}/leave", headers=headers_for(user))
        assert client.get(f"{DRAFTS}/{draft['id']}", headers=headers_for(user)).status_code == 404


class TestRequirementPosts:
    def url(self, channel: Channel) -> str:
        return f"/api/v1/channels/{channel.id}/requirement-posts"

    def test_a_post_creates_a_card_and_a_proposed_requirement(
        self,
        client: TestClient,
        db_session: Session,
        project: Project,
        channel: Channel,
        make_user: Callable[..., User],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        events = bus.InProcessEventBus()
        monkeypatch.setattr(bus, "get_bus", lambda: events)
        developer = make_user(role=DefaultRole.DEVELOPER)
        draft = _create(client, developer, project, EVENT_DRIVEN).json()

        response = client.post(
            self.url(channel),
            json={"fields": EVENT_DRIVEN, "draft_id": draft["id"]},
            headers=headers_for(developer),
        )

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["message"]["kind"] == "requirement_post"
        assert body["message"]["body"] == STATEMENT
        requirement = body["requirement"]
        assert (requirement["state"], requirement["origin"]) == ("Proposed", "post")
        assert requirement["document_id"] is None and requirement["source_req_id"] is None
        assert requirement["owner_id"] == str(developer.id)
        assert requirement["stakeholder_group"] == "Security"

        row = db_session.get(Requirement, requirement["requirement_id"])
        assert row is not None
        assert str(row.origin_message_id) == body["message"]["id"]
        assert (row.req_type, row.priority) == ("functional", "must")
        assert row.composer_fields is not None and row.composer_fields["template"] == "event_driven"
        version = db_session.scalar(
            select(RequirementVersion).where(RequirementVersion.requirement_id == row.id)
        )
        assert version is not None and version.changed_by == developer.id
        audit = db_session.scalar(
            select(AuditLog).where(AuditLog.action == AuditAction.REQUIREMENT_POSTED)
        )
        assert audit is not None and audit.requirement_id == row.id
        assert "inactive" not in str(audit.details)
        assert (
            client.get(f"{DRAFTS}/{draft['id']}", headers=headers_for(developer)).status_code == 404
        )
        assert [e.type for e in events.published] == [MESSAGE_CREATED]

    def test_it_appears_in_the_requirements_list(
        self, client: TestClient, project: Project, channel: Channel, user: User
    ) -> None:
        client.post(self.url(channel), json={"fields": EVENT_DRIVEN}, headers=headers_for(user))
        listed = client.get(
            f"/api/v1/projects/{project.id}/requirements",
            params={"origin": "post"},
            headers=headers_for(user),
        ).json()
        assert [item["body"] for item in listed["items"]] == [STATEMENT]

    def test_the_card_cannot_be_edited(
        self, client: TestClient, db_session: Session, channel: Channel, user: User
    ) -> None:
        client.post(self.url(channel), json={"fields": EVENT_DRIVEN}, headers=headers_for(user))
        card = db_session.scalar(
            select(Message).where(Message.kind == MessageKind.REQUIREMENT_POST)
        )
        assert card is not None
        response = client.patch(
            f"/api/v1/messages/{card.id}", json={"body": "x"}, headers=headers_for(user)
        )
        assert response.status_code == 409

    def test_incomplete_slots_are_rejected(
        self, client: TestClient, channel: Channel, user: User
    ) -> None:
        fields = {**EVENT_DRIVEN, "slots": {"trigger": "x"}}
        assert (
            client.post(
                self.url(channel), json={"fields": fields}, headers=headers_for(user)
            ).status_code
            == 422
        )

    def test_a_compliance_reviewer_cannot_propose(
        self, client: TestClient, channel: Channel, make_user: Callable[..., User]
    ) -> None:
        reviewer = make_user(role=DefaultRole.COMPLIANCE_REVIEWER)
        response = client.post(
            self.url(channel), json={"fields": EVENT_DRIVEN}, headers=headers_for(reviewer)
        )
        assert response.status_code == 403

    def test_the_owner_must_be_a_member(
        self,
        client: TestClient,
        channel: Channel,
        user: User,
        make_user: Callable[..., User],
        make_workspace: Callable[..., Workspace],
    ) -> None:
        stranger = make_user(workspace=make_workspace())
        fields = {**EVENT_DRIVEN, "owner_id": str(stranger.id)}
        response = client.post(
            self.url(channel), json={"fields": fields}, headers=headers_for(user)
        )
        assert response.status_code == 404
