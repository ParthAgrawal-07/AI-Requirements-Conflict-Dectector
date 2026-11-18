"""System messages (Dhavni — US-31 groundwork, migration 0006d): cards written by the app, with
no member as author, that members read, are notified by and cannot edit."""

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Channel, Message, MessageKind, Project, User
from app.realtime import bus
from app.realtime.events import MESSAGE_CREATED, MESSAGE_UPDATED
from app.services import messages as message_service
from tests.api.conftest import headers_for


@pytest.fixture
def events(monkeypatch: pytest.MonkeyPatch) -> Iterator[bus.InProcessEventBus]:
    test_bus = bus.InProcessEventBus()
    monkeypatch.setattr(bus, "get_bus", lambda: test_bus)
    yield test_bus


@pytest.fixture
def channel(db_session: Session, project: Project) -> Channel:
    channel = Channel(project_id=project.id, name="mobile-app")
    db_session.add(channel)
    db_session.commit()
    return channel


def test_a_card_has_no_author_mentions_who_it_names_and_is_announced(
    client: TestClient,
    db_session: Session,
    channel: Channel,
    user: User,
    make_user: Callable[..., User],
    events: bus.InProcessEventBus,
) -> None:
    owner = make_user()

    card = message_service.post_system_message(
        db_session,
        channel=channel,
        body=f"Analysis: 1 conflict. <@{owner.id}>",
        kind=MessageKind.ANALYSIS_CARD,
        payload={"run_id": "r-1"},
    )

    assert card.author_id is None and card.mentions == [str(owner.id)]
    (event,) = [e for e in events.published if e.type == MESSAGE_CREATED]
    assert event.data["author_id"] is None and event.data["mentions"] == [str(owner.id)]
    (read,) = client.get(
        f"/api/v1/channels/{channel.id}/messages", headers=headers_for(user)
    ).json()["items"]
    assert read["author"] is None
    assert read["kind"] == "analysis_card" and read["payload"] == {"run_id": "r-1"}


def test_a_card_counts_as_unread(
    client: TestClient, db_session: Session, channel: Channel, user: User
) -> None:
    message_service.post_system_message(
        db_session, channel=channel, body="Analysis finished.", kind=MessageKind.ANALYSIS_CARD
    )

    (listed,) = client.get(
        f"/api/v1/projects/{channel.project_id}/channels", headers=headers_for(user)
    ).json()
    assert listed["unread_count"] == 1


def test_members_cannot_edit_or_delete_a_card(
    client: TestClient, db_session: Session, channel: Channel, user: User
) -> None:
    card = message_service.post_system_message(
        db_session, channel=channel, body="Analysis finished.", kind=MessageKind.ANALYSIS_CARD
    )

    edited = client.patch(
        f"/api/v1/messages/{card.id}", json={"body": "verified!"}, headers=headers_for(user)
    )
    deleted = client.delete(f"/api/v1/messages/{card.id}", headers=headers_for(user))

    assert edited.status_code == 403 and deleted.status_code == 403


def test_the_app_rewrites_its_own_card(
    db_session: Session, channel: Channel, events: bus.InProcessEventBus
) -> None:
    card = message_service.post_system_message(
        db_session, channel=channel, body="Waiting for budget.", kind=MessageKind.ANALYSIS_CARD
    )

    message_service.update_system_message(
        db_session, message=card, body="Analysis finished.", payload={"status": "done"}
    )

    assert card.body == "Analysis finished." and card.payload == {"status": "done"}
    assert [e.type for e in events.published][-1] == MESSAGE_UPDATED


def test_only_system_kinds_may_lack_an_author(db_session: Session, channel: Channel) -> None:
    with pytest.raises(ValueError, match="not a system message kind"):
        message_service.post_system_message(
            db_session, channel=channel, body="hi", kind=MessageKind.CHAT
        )
    db_session.add(Message(channel_id=channel.id, author_id=None, kind=MessageKind.CHAT, body="x"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_a_members_message_is_never_rewritten_as_a_card(
    db_session: Session, channel: Channel, user: User
) -> None:
    mine = message_service.post_message(db_session, channel=channel, author=user, body="hello")

    with pytest.raises(ValueError):
        message_service.update_system_message(db_session, message=mine, body="x", payload=None)
