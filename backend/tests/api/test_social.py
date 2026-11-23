"""Discussion, votes, watch and links (Madhav — US-53, FR-80, FR-90, FR-91, DR-17, DR-19)."""

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.consequences.impact import ImpactAnalyzer
from app.core.permissions import DefaultRole
from app.graph import service as graph_service
from app.models import (
    AuditLog,
    ChangeRequest,
    GraphEvent,
    Issue,
    Notification,
    Project,
    Requirement,
    RequirementState,
    User,
    Workspace,
)
from app.realtime import bus
from app.realtime.events import REQUIREMENT_ACTIVITY
from app.search.relations import RelationKind
from tests.analysis_helpers import make_post
from tests.api.conftest import headers_for


@pytest.fixture
def events(monkeypatch: pytest.MonkeyPatch) -> Iterator[bus.InProcessEventBus]:
    test_bus = bus.InProcessEventBus()
    monkeypatch.setattr(bus, "get_bus", lambda: test_bus)
    yield test_bus


def url(*parts: object) -> str:
    return "/api/v1/" + "/".join(str(p) for p in parts)


def notifications(db: Session, user: User, kind: str) -> list[Notification]:
    return list(
        db.scalars(
            select(Notification).where(Notification.user_id == user.id, Notification.kind == kind)
        )  # fmt: skip
    )


# ── comments ────────────────────────────────────────────────────────────────────────────────
def test_a_comment_reaches_the_owner_the_watchers_and_the_people_it_mentions(
    client: TestClient,
    db_session: Session,
    project: Project,
    make_user: Callable[..., User],
    events: bus.InProcessEventBus,
) -> None:
    owner, author = make_user(), make_user(role=DefaultRole.STAKEHOLDER)
    watcher, mentioned = make_user(role=DefaultRole.DEVELOPER), make_user()
    requirement = make_post(db_session, project, owner, "Sessions end after 5 minutes.",
                            label="REQ-31")  # fmt: skip
    assert client.put(url("requirements", requirement.id, "watch"),
                      headers=headers_for(watcher)).json() == {"watching": True, "watchers": 1}  # fmt: skip

    response = client.post(
        url("requirements", requirement.id, "comments"),
        json={"body": "Five minutes is too short for clinicians.", "mentions": [str(mentioned.id)]},
        headers=headers_for(author),
    )

    assert response.status_code == 201, response.text
    thread = client.get(url("requirements", requirement.id, "comments"),
                        headers=headers_for(owner)).json()  # fmt: skip
    assert [(c["body"], c["author_id"]) for c in thread] == [
        ("Five minutes is too short for clinicians.", str(author.id))
    ]
    assert len(notifications(db_session, owner, "watching")) == 1
    assert len(notifications(db_session, watcher, "watching")) == 1
    (mention,) = notifications(db_session, mentioned, "mentioned")
    assert mention.payload["title"] == "Test User mentioned you on REQ-31"
    assert notifications(db_session, mentioned, "watching") == []  # told once, not twice
    assert notifications(db_session, author, "watching") == []  # never about your own comment
    assert "clinicians" not in str(mention.payload)  # CR-04
    activity = [e for e in events.published if e.type == REQUIREMENT_ACTIVITY]
    assert activity and activity[-1].data == {
        "requirement_id": str(requirement.id), "what": "comment", "actor_id": str(author.id)
    }  # fmt: skip


def test_a_viewer_reads_the_discussion_but_cannot_comment(
    client: TestClient, db_session: Session, project: Project, user: User,
    make_user: Callable[..., User],
) -> None:  # fmt: skip
    requirement = make_post(db_session, project, user, "x", label="REQ-1")
    viewer = headers_for(make_user(role=DefaultRole.VIEWER))
    assert (
        client.get(url("requirements", requirement.id, "comments"), headers=viewer).status_code
        == 200
    )
    denied = client.post(url("requirements", requirement.id, "comments"), json={"body": "hi"},
                         headers=viewer)  # fmt: skip
    assert denied.status_code == 403
    empty = client.post(url("requirements", requirement.id, "comments"), json={"body": ""},
                        headers=headers_for(user))  # fmt: skip
    assert empty.status_code == 422


# ── votes ───────────────────────────────────────────────────────────────────────────────────
def test_one_vote_per_member_and_votes_never_change_state(
    client: TestClient, db_session: Session, project: Project, user: User,
    make_user: Callable[..., User],
) -> None:  # fmt: skip
    requirement = make_post(db_session, project, user, "x", label="REQ-1")
    client_rep = make_user(role=DefaultRole.STAKEHOLDER)
    developer = make_user(role=DefaultRole.DEVELOPER)
    path = url("requirements", requirement.id, "vote")

    client.put(path, json={"stance": "support"}, headers=headers_for(client_rep))
    again = client.put(path, json={"stance": "oppose", "reason": "Too strict for night shifts"},
                       headers=headers_for(client_rep)).json()  # fmt: skip
    tally = client.put(path, json={"stance": "support"}, headers=headers_for(developer)).json()

    assert (again["support"], again["oppose"], again["mine"]) == (0, 1, "oppose")
    assert (tally["support"], tally["oppose"], tally["mine"]) == (1, 1, "support")
    assert tally["decides"] is False
    reasons = {v["reason"] for v in tally["votes"]}
    assert "Too strict for night shifts" in reasons
    db_session.refresh(requirement)
    assert requirement.state is RequirementState.PROPOSED  # DR-17

    withdrawn = client.delete(path, headers=headers_for(developer)).json()
    assert (withdrawn["support"], withdrawn["mine"]) == (0, None)
    viewer = headers_for(make_user(role=DefaultRole.VIEWER))
    assert client.put(path, json={"stance": "support"}, headers=viewer).status_code == 403


def test_reviewers_see_the_tally_on_a_change_request(
    client: TestClient, db_session: Session, project: Project, user: User,
    make_user: Callable[..., User],
) -> None:  # fmt: skip
    requirement = make_post(db_session, project, user, "x", label="REQ-1")
    change_request = ChangeRequest(project_id=project.id, requirement_id=requirement.id, number=1,
                                   proposer_id=user.id, base_version=1, proposed_body="y",
                                   reason="r")  # fmt: skip
    db_session.add(change_request)
    db_session.commit()
    stakeholder = make_user(role=DefaultRole.STAKEHOLDER)
    client.put(url("change-requests", change_request.id, "vote"), json={"stance": "oppose"},
               headers=headers_for(stakeholder))  # fmt: skip
    tally = client.get(url("change-requests", change_request.id, "votes"),
                       headers=headers_for(user)).json()  # fmt: skip
    assert (tally["support"], tally["oppose"], tally["mine"]) == (0, 1, None)
    db_session.refresh(change_request)
    assert change_request.status == "open"  # a vote is not a review


# ── watch ───────────────────────────────────────────────────────────────────────────────────
def test_watchers_of_an_issue_hear_about_its_comments(
    client: TestClient, db_session: Session, project: Project, user: User,
    make_user: Callable[..., User],
) -> None:  # fmt: skip
    issue = Issue(project_id=project.id, number=1, title="Timeout", author_id=user.id)
    db_session.add(issue)
    db_session.commit()
    watcher = make_user(role=DefaultRole.VIEWER)  # a viewer may follow what it can see
    assert (
        client.put(url("issues", issue.id, "watch"), headers=headers_for(watcher)).status_code
        == 200
    )

    client.post(url("issues", issue.id, "comments"), json={"body": "Any news?"},
                headers=headers_for(user))  # fmt: skip

    (note,) = notifications(db_session, watcher, "watching")
    assert note.payload["title"] == "Test User commented on ISS-1"
    client.delete(url("issues", issue.id, "watch"), headers=headers_for(watcher))
    assert client.get(url("issues", issue.id, "watch"),
                      headers=headers_for(watcher)).json() == {"watching": False, "watchers": 0}  # fmt: skip


# ── links ───────────────────────────────────────────────────────────────────────────────────
def test_a_link_is_drawn_as_a_human_edge_logged_and_used_by_impact_analysis(
    client: TestClient, db_session: Session, project: Project, user: User,
    make_requirement: Callable[..., Requirement], events: bus.InProcessEventBus,
) -> None:  # fmt: skip
    login = make_requirement("Users log in with SSO.", source_req_id="REQ-1")
    audit = make_requirement("Logins are audited.", source_req_id="REQ-2")

    response = client.post(url("requirements", audit.id, "links"),
                           json={"target_id": str(login.id), "kind": "depends_on",
                                 "note": "Needs a login to audit"},
                           headers=headers_for(user))  # fmt: skip

    assert response.status_code == 201, response.text
    link = response.json()
    assert (link["direction"], link["kind"], link["target_label"]) == (
        "outgoing", "depends_on", "REQ-1"
    )  # fmt: skip
    edges = [e for e in graph_service.snapshot(db_session, project.id).edges if e.kind == "link"]
    assert [(e.source, e.target, e.found_by, e.link_kind, e.status) for e in edges] == [
        (audit.id, login.id, "person", "depends_on", "confirmed")
    ]
    event = db_session.scalars(select(GraphEvent).where(GraphEvent.kind == "link")).one()
    assert event.sentence == "Test User linked REQ-2 to REQ-1 (depends on)."
    impact = ImpactAnalyzer(db_session).analyse(login)
    (affected,) = impact.affected
    assert (affected.requirement_id, affected.relation, affected.status) == (
        audit.id, RelationKind.REQUIRED_BY, "confirmed"
    )  # fmt: skip
    incoming = client.get(url("requirements", login.id, "links"), headers=headers_for(user)).json()
    assert [l["direction"] for l in incoming] == ["incoming"]  # noqa: E741

    duplicate = client.post(url("requirements", audit.id, "links"),
                            json={"target_id": str(login.id), "kind": "depends_on"},
                            headers=headers_for(user))  # fmt: skip
    assert (duplicate.status_code, duplicate.json()["error"]["code"]) == (409, "link_exists")
    itself = client.post(url("requirements", audit.id, "links"),
                         json={"target_id": str(audit.id), "kind": "related_to"},
                         headers=headers_for(user))  # fmt: skip
    assert itself.status_code == 400


def test_only_a_person_removes_a_link_and_both_moves_are_audited(
    client: TestClient, db_session: Session, project: Project, user: User,
    make_requirement: Callable[..., Requirement], events: bus.InProcessEventBus,
) -> None:  # fmt: skip
    a = make_requirement("a", source_req_id="REQ-1")
    b = make_requirement("b", source_req_id="REQ-2")
    link = client.post(url("requirements", a.id, "links"),
                       json={"target_id": str(b.id), "kind": "refines"},
                       headers=headers_for(user)).json()  # fmt: skip

    response = client.delete(
        url("requirements", b.id, "links", link["id"]), headers=headers_for(user)
    )

    assert response.status_code == 204
    assert client.get(url("requirements", a.id, "links"), headers=headers_for(user)).json() == []
    actions = [row.action for row in db_session.scalars(
        select(AuditLog).where(AuditLog.action.in_(["link_added", "link_removed"]))
        .order_by(AuditLog.at))]  # fmt: skip
    assert sorted(actions) == ["link_added", "link_removed"]
    assert all(row != "a" for row in actions)


def test_links_stay_inside_the_project_and_need_req_link(
    client: TestClient, db_session: Session, project: Project, user: User,
    make_requirement: Callable[..., Requirement], make_project: Callable[..., Project],
    make_user: Callable[..., User], make_workspace: Callable[..., Workspace],
) -> None:  # fmt: skip
    mine = make_requirement("a", source_req_id="REQ-1")
    elsewhere = make_post(db_session, make_project(), user, "b", label="REQ-9")
    across = client.post(url("requirements", mine.id, "links"),
                         json={"target_id": str(elsewhere.id), "kind": "related_to"},
                         headers=headers_for(user))  # fmt: skip
    assert across.status_code == 404
    stakeholder = headers_for(make_user(role=DefaultRole.STAKEHOLDER))
    denied = client.post(url("requirements", mine.id, "links"),
                         json={"target_id": str(mine.id), "kind": "related_to"},
                         headers=stakeholder)  # fmt: skip
    assert denied.status_code == 403
    outsider = headers_for(make_user(role=DefaultRole.OWNER, workspace=make_workspace()))
    assert client.get(url("requirements", mine.id, "social"), headers=outsider).status_code == 404
    assert client.put(url("requirements", mine.id, "watch"), headers=outsider).status_code == 404


def test_the_drawer_summary_and_the_timeline_show_votes_and_links(
    client: TestClient, db_session: Session, project: Project, user: User,
    make_requirement: Callable[..., Requirement], events: bus.InProcessEventBus,
) -> None:  # fmt: skip
    a = make_requirement("a", source_req_id="REQ-1")
    b = make_requirement("b", source_req_id="REQ-2")
    headers = headers_for(user)
    client.put(url("requirements", a.id, "vote"), json={"stance": "support"}, headers=headers)
    client.put(url("requirements", a.id, "watch"), headers=headers)
    client.post(url("requirements", a.id, "comments"), json={"body": "ok"}, headers=headers)
    client.post(url("requirements", a.id, "links"),
                json={"target_id": str(b.id), "kind": "related_to"}, headers=headers)  # fmt: skip

    summary = client.get(url("requirements", a.id, "social"), headers=headers).json()
    assert summary["comments"] == 1 and summary["watching"] is True
    assert (summary["votes"]["support"], summary["votes"]["mine"]) == (1, "support")
    assert [l["target_label"] for l in summary["links"]] == ["REQ-2"]  # noqa: E741
    timeline = client.get(url("requirements", a.id, "timeline"),
                          params=[("kind", "vote"), ("kind", "link")], headers=headers).json()  # fmt: skip
    assert {e["title"] for e in timeline["entries"]} == {
        "Supports it",
        "Linked: REQ-1 is related to REQ-2",
    }
