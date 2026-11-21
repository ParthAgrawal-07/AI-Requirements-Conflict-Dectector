"""Inbox and notifications (Madhav — US-38, FR-69, FR-70, CR-04)."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.permissions import DefaultRole
from app.models import Channel, Issue, Message, Project, User, Workspace
from app.models.notification import ASSIGNED, MENTIONED, REVIEW_REQUESTED, Notification
from app.notifications import hooks
from app.notifications.service import NotificationService, Subject
from app.realtime import bus
from app.realtime.gateway import _Session
from app.services import issues as issue_service
from app.services import messages as message_service
from tests.api.conftest import headers_for


@pytest.fixture
def events(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    published: list[Any] = []
    monkeypatch.setattr(bus, "publish", published.append)
    return published


@pytest.fixture
def people(make_user: Callable[..., User]) -> dict[str, User]:
    return {
        "riya": make_user(role=DefaultRole.DEVELOPER),
        "arjun": make_user(role=DefaultRole.DEVELOPER),
        "pm": make_user(role=DefaultRole.PROJECT_MANAGER),
    }


def subject(key: str = "RCR-3") -> Subject:
    return Subject("change_request", uuid.uuid4(), key, f"Review requested: {key} on REQ-014",
                   "/w/x/p/y/changes/z")  # fmt: skip


def test_notify_stores_ids_and_titles_and_pushes_to_the_recipient_only(
    db_session: Session, project: Project, people: dict[str, User], events: list[Any]
) -> None:
    (row,) = NotificationService(db_session).notify(
        [people["riya"].id],
        REVIEW_REQUESTED,
        workspace_id=project.workspace_id,
        project_id=project.id,
        subject=subject(),
        actor_id=people["pm"].id,
    )
    assert row.payload == {
        "title": "Review requested: RCR-3 on REQ-014",
        "key": "RCR-3",
        "url": "/w/x/p/y/changes/z",
    }
    (event,) = events
    assert event.type == "notification.created"
    assert event.data["recipient_id"] == str(people["riya"].id)

    riya, arjun = _Session(people["riya"]), _Session(people["arjun"])
    for socket in (riya, arjun):
        socket.workspaces.add(project.workspace_id)
        socket.whole_workspaces.add(project.workspace_id)
    assert riya.wants(event) and not arjun.wants(event)


def test_no_self_notification_no_outsiders_and_no_text(
    db_session: Session,
    project: Project,
    people: dict[str, User],
    make_workspace: Callable[..., Workspace],
    make_user: Callable[..., User],
) -> None:
    outsider = make_user(workspace=make_workspace())
    rows = NotificationService(db_session).notify(
        [people["pm"].id, outsider.id, None],
        ASSIGNED,
        workspace_id=project.workspace_id,
        subject=subject("ISS-1"),
        actor_id=people["pm"].id,
    )
    assert rows == []
    with pytest.raises(ValueError, match="CR-04"):
        NotificationService(db_session).notify(
            [people["riya"].id], ASSIGNED, workspace_id=project.workspace_id,
            subject=subject(), body="The system shall …",
        )  # fmt: skip


def test_an_unread_repeat_is_refreshed_not_repeated(
    db_session: Session, project: Project, people: dict[str, User]
) -> None:
    service = NotificationService(db_session)
    about = subject()
    first = service.notify([people["riya"].id], REVIEW_REQUESTED,
                           workspace_id=project.workspace_id, subject=about)  # fmt: skip
    again = service.notify([people["riya"].id], REVIEW_REQUESTED,
                           workspace_id=project.workspace_id, subject=about)  # fmt: skip
    assert first[0].id == again[0].id
    service.mark_read(people["riya"].id)
    third = service.notify([people["riya"].id], REVIEW_REQUESTED,
                           workspace_id=project.workspace_id, subject=about)  # fmt: skip
    assert third[0].id != first[0].id


def test_inbox_groups_counts_and_read(
    client: TestClient, db_session: Session, project: Project, people: dict[str, User]
) -> None:
    service = NotificationService(db_session)
    for kind, key in ((REVIEW_REQUESTED, "RCR-1"), (ASSIGNED, "ISS-1"), (MENTIONED, "msg")):
        service.notify([people["riya"].id], kind, workspace_id=project.workspace_id,
                       subject=subject(key))  # fmt: skip
    headers = headers_for(people["riya"])

    counts = client.get("/api/v1/notifications/counts", headers=headers).json()
    assert (counts["review"], counts["assigned"], counts["mentioned"], counts["total"]) == (
        1,
        1,
        1,
        3,
    )
    review = client.get("/api/v1/notifications", params={"group": "review"}, headers=headers)
    assert [n["payload"]["key"] for n in review.json()] == ["RCR-1"]

    first = review.json()[0]["id"]
    marked = client.post("/api/v1/notifications/read", json={"ids": [first]}, headers=headers)
    assert marked.json() == {"marked": 1}
    assert client.get("/api/v1/notifications/counts", headers=headers).json()["total"] == 2
    client.post("/api/v1/notifications/read", json={"all": True}, headers=headers)
    unread = client.get("/api/v1/notifications", params={"unread": True}, headers=headers)
    assert unread.json() == []


def test_one_cannot_read_or_mark_another_persons_notifications(
    client: TestClient, db_session: Session, project: Project, people: dict[str, User]
) -> None:
    (row,) = NotificationService(db_session).notify(
        [people["riya"].id], ASSIGNED, workspace_id=project.workspace_id, subject=subject()
    )
    arjun = headers_for(people["arjun"])
    assert client.get("/api/v1/notifications", headers=arjun).json() == []
    assert client.post("/api/v1/notifications/read", json={"ids": [str(row.id)]},
                       headers=arjun).json() == {"marked": 0}  # fmt: skip
    db_session.refresh(row)
    assert row.read_at is None


def test_read_needs_ids_or_all(client: TestClient, people: dict[str, User]) -> None:
    response = client.post(
        "/api/v1/notifications/read", json={}, headers=headers_for(people["riya"])
    )
    assert response.status_code == 422


def test_a_removed_member_no_longer_sees_that_workspace(
    client: TestClient, db_session: Session, project: Project, people: dict[str, User]
) -> None:
    from datetime import UTC, datetime

    from app.services.access import active_membership

    NotificationService(db_session).notify(
        [people["riya"].id], ASSIGNED, workspace_id=project.workspace_id, subject=subject()
    )
    membership = active_membership(db_session, people["riya"].id, project.workspace_id)
    assert membership is not None
    membership.ended_at = datetime.now(UTC)
    db_session.commit()
    assert client.get("/api/v1/notifications", headers=headers_for(people["riya"])).json() == []


# ── producers ───────────────────────────────────────────────────────────────────────────────
def test_a_mention_notifies(
    db_session: Session, project: Project, people: dict[str, User], events: list[Any]
) -> None:
    channel = Channel(project_id=project.id, name="general", created_by=people["pm"].id)
    db_session.add(channel)
    db_session.commit()
    message_service.post_message(
        db_session, channel=channel, author=people["pm"], body=f"<@{people['riya'].id}> please look"
    )
    (row,) = db_session.query(Notification).filter_by(user_id=people["riya"].id).all()
    assert row.kind == MENTIONED and "mentioned you in #general" in row.payload["title"]
    assert "please look" not in str(row.payload)


def test_assignment_notifies_new_assignees_only(
    db_session: Session, project: Project, people: dict[str, User], events: list[Any]
) -> None:
    issue = issue_service.open_issue(
        db_session, project=project, author=people["pm"], title="Timeout clash",
        assignees=[people["riya"].id, people["pm"].id],
    )  # fmt: skip
    kinds = {(n.user_id, n.kind) for n in db_session.query(Notification).all()}
    assert kinds == {(people["riya"].id, ASSIGNED)}
    assert isinstance(issue, Issue)


def test_join_requests_reach_the_managers(
    db_session: Session, workspace: Workspace, people: dict[str, User], events: list[Any]
) -> None:
    from app.services import join_codes
    from app.services.membership import get_default_role
    from app.services.users import create_user

    code = join_codes.create_code(
        db_session, workspace_id=workspace.id, creator=people["pm"],
        role_id=get_default_role(db_session, DefaultRole.DEVELOPER).id, expires_in_days=7,
        requires_approval=True,
    )  # fmt: skip
    newcomer = create_user(db_session, email=f"n-{uuid.uuid4().hex[:6]}@example.com",
                           password="correct-horse-battery-staple", full_name="Neha")  # fmt: skip
    from app.models import JoinRequest

    request = join_codes.redeem(db_session, code.code, newcomer)
    assert isinstance(request, JoinRequest)
    db_session.commit()
    hooks.join_requested(db_session, request)

    recipients = {n.user_id for n in db_session.query(Notification).all()}
    assert people["pm"].id in recipients and people["riya"].id not in recipients


def test_message_text_never_reaches_the_payload(
    db_session: Session, project: Project, people: dict[str, User]
) -> None:
    channel = Channel(project_id=project.id, name="g", created_by=people["pm"].id)
    db_session.add(channel)
    db_session.commit()
    message = Message(channel_id=channel.id, author_id=people["pm"].id, body="secret wording",
                      mentions=[str(people["riya"].id)])  # fmt: skip
    db_session.add(message)
    db_session.commit()
    hooks.mentioned(db_session, project, channel, message)
    (row,) = db_session.query(Notification).all()
    assert "secret" not in str(row.payload)
