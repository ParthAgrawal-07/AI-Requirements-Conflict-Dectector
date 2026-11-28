"""Checkpoint 1, item 4 (Affan — NFR-27, ADR-12, US-27): tenant isolation over REST and WebSocket
for everything Sprint 3 added, and a viewer has no composer.

* REST: a member of another workspace — even its Owner — gets **404** from every Sprint 3 route
  that names this workspace's requirement, finding, question, run, ownership request or project:
  the resources do not exist for them (never 403, which would confirm they do).
* WebSocket: a live-map delta and a result card in one workspace reach that workspace's map and
  thread, and never a socket subscribed elsewhere.
* A viewer is told it may not propose (the UI hides the composer from ``/me/permissions``) and is
  refused if it tries anyway.
"""

import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from starlette.testclient import WebSocketTestSession

from app.core import security
from app.core.permissions import DefaultRole
from app.embeddings.model import HashingEmbedder, get_embedder
from app.models import (
    AnalysisRun,
    AnalysisRunStatus,
    AnalysisScope,
    CandidatePair,
    Channel,
    Clarification,
    Finding,
    FindingCategory,
    MessageKind,
    OwnershipRequest,
    Project,
    Requirement,
    User,
    Workspace,
)
from app.realtime import bus
from app.realtime.events import GRAPH_DELTA, MESSAGE_CREATED
from app.services import messages as message_service
from tests.api.conftest import headers_for

STATEMENT = {
    "template": "free_text",
    "slots": {"statement": "The system shall keep audit logs for seven years."},
    "type": "functional",
    "priority": "must",
}


@dataclass
class Home:
    """Workspace A's Sprint 3 resources."""

    project: Project
    requirement: Requirement
    finding: Finding
    clarification: Clarification
    run: AnalysisRun
    ownership_request: OwnershipRequest
    channel: Channel
    member: User


@pytest.fixture
def home(
    db_session: Session,
    project: Project,
    make_user: Callable[..., User],
    make_requirement: Callable[..., Requirement],
) -> Home:
    member = make_user(role=DefaultRole.BUSINESS_ANALYST)
    a = make_requirement("Sessions end after 30 minutes.", source_req_id="REQ-014")
    b = make_requirement("Sessions end after 5 minutes.", source_req_id="REQ-031")
    first, second = CandidatePair.ordered(a.id, b.id)
    pair = CandidatePair(requirement_a_id=first, requirement_b_id=second, similarity_score=0.9)
    db_session.add(pair)
    db_session.flush()
    finding = Finding(
        project_id=project.id,
        document_id=a.document_id,
        candidate_pair_id=pair.id,
        category=FindingCategory.CONFLICTING,
        confidence=0.9,
        rationale="r",
        original_ai_output={},
    )
    run = AnalysisRun(
        project_id=project.id,
        scope=AnalysisScope.REQUIREMENT,
        subject_id=b.id,
        status=AnalysisRunStatus.DONE,
    )
    channel = Channel(project_id=project.id, name="general", is_default=True)
    db_session.add_all([finding, run, channel])
    db_session.flush()
    clarification = Clarification(finding_id=finding.id, question="5 or 30 minutes?")
    request = OwnershipRequest(requirement_id=a.id, requester_id=member.id)
    db_session.add_all([clarification, request])
    db_session.commit()
    return Home(project, a, finding, clarification, run, request, channel, member)


@pytest.fixture
def other_workspace(make_workspace: Callable[..., Workspace]) -> Workspace:
    return make_workspace()


@pytest.fixture
def outsider(make_user: Callable[..., User], other_workspace: Workspace) -> User:
    """The Owner of another workspace: every permission there, none here."""
    return make_user(role=DefaultRole.OWNER, workspace=other_workspace)


@pytest.fixture
def api(client: TestClient) -> Iterator[TestClient]:
    from app.main import app

    app.dependency_overrides[get_embedder] = HashingEmbedder
    yield client
    app.dependency_overrides.pop(get_embedder, None)


def sprint_3_routes(home: Home) -> list[tuple[str, str, dict[str, Any] | None]]:
    p, r, f = home.project.id, home.requirement.id, home.finding.id
    return [
        ("GET", f"/api/v1/requirements/{r}", None),
        ("PATCH", f"/api/v1/requirements/{r}", {"state": "Under_Review", "version": 1}),
        ("PATCH", f"/api/v1/requirements/{r}", {"stakeholder_group": "Security"}),
        ("POST", f"/api/v1/requirements/{r}/signoff", {"version": 1}),
        ("POST", f"/api/v1/requirements/{r}/ownership-requests", {}),
        ("GET", f"/api/v1/requirements/{r}/ownership-requests", None),
        ("POST", f"/api/v1/ownership-requests/{home.ownership_request.id}/decision", {"accept": True}),
        ("POST", f"/api/v1/findings/{f}/review", {"action": "dismiss", "reason": "not real"}),
        ("GET", f"/api/v1/findings/{f}/reviews", None),
        ("GET", f"/api/v1/findings/{f}/clarification", None),
        ("POST", f"/api/v1/findings/{f}/clarification", None),
        ("POST", f"/api/v1/clarifications/{home.clarification.id}/answer", {"resolution": "30"}),
        ("GET", f"/api/v1/analysis-runs/{home.run.id}", None),
        ("GET", f"/api/v1/projects/{p}/graph?revision=0", None),
        ("PUT", f"/api/v1/projects/{p}/graph/positions",
         {"positions": [{"requirement_id": str(r), "x": 0, "y": 0}]}),
        ("POST", f"/api/v1/projects/{p}/similar", {"text": "sessions"}),
        ("POST", f"/api/v1/projects/{p}/requirements", {"fields": STATEMENT}),
    ]  # fmt: skip


def test_every_sprint_3_route_is_a_404_for_another_workspace(
    api: TestClient, db_session: Session, home: Home, outsider: User
) -> None:
    for method, path, body in sprint_3_routes(home):
        response = api.request(method, path, json=body, headers=headers_for(outsider))
        assert response.status_code == 404, f"{method} {path}: {response.status_code}"

    db_session.refresh(home.requirement)
    db_session.refresh(home.finding)
    assert home.requirement.stakeholder_group is None  # nothing changed on the way
    assert home.finding.status.value == "flagged"


def test_unknown_ids_look_exactly_like_other_tenants_ids(api: TestClient, home: Home) -> None:
    """An outsider cannot tell "exists elsewhere" from "does not exist"."""
    member = headers_for(home.member)
    for path in (
        f"/api/v1/requirements/{uuid.uuid4()}",
        f"/api/v1/analysis-runs/{uuid.uuid4()}",
        f"/api/v1/findings/{uuid.uuid4()}/reviews",
    ):
        assert api.get(path, headers=member).status_code == 404


# ── WebSocket ───────────────────────────────────────────────────────────────────────────────
def token(user: User) -> str:
    return security.create_access_token(user.id)[0]


def subscribe(socket: WebSocketTestSession, user: User, project_id: uuid.UUID) -> None:
    socket.send_json({"type": "auth", "token": token(user)})
    assert socket.receive_json()["type"] == "ready"
    socket.send_json({"type": "subscribe", "project_id": str(project_id)})
    assert socket.receive_json()["type"] == "subscribed"


def assert_nothing_arrived(socket: WebSocketTestSession) -> None:
    """The next frame is the answer to a ping: no event was queued before it."""
    socket.send_json({"type": "ping"})
    assert socket.receive_json() == {"type": "pong"}


def test_map_deltas_and_cards_stay_in_their_workspace(
    client: TestClient,
    event_bus: bus.InProcessEventBus,
    db_session: Session,
    home: Home,
    outsider: User,
    other_workspace: Workspace,
    make_project: Callable[..., Project],
) -> None:
    elsewhere = make_project(workspace=other_workspace)
    with client.websocket_connect("/ws") as inside, client.websocket_connect("/ws") as outside:
        subscribe(inside, home.member, home.project.id)
        subscribe(outside, outsider, elsewhere.id)

        moved = client.put(
            f"/api/v1/projects/{home.project.id}/graph/positions",
            json={"positions": [{"requirement_id": str(home.requirement.id), "x": 5, "y": 5}]},
            headers=headers_for(home.member),
        )
        message_service.post_system_message(
            db_session,
            channel=home.channel,
            body="Analysis of REQ-031:",
            kind=MessageKind.ANALYSIS_CARD,
        )

        assert moved.status_code == 204
        assert inside.receive_json()["event"]["type"] == GRAPH_DELTA
        assert inside.receive_json()["event"]["type"] == MESSAGE_CREATED
        assert_nothing_arrived(outside)


def test_an_outsider_cannot_subscribe_to_this_projects_map(
    client: TestClient, event_bus: bus.InProcessEventBus, home: Home, outsider: User
) -> None:
    with client.websocket_connect("/ws") as socket:
        socket.send_json({"type": "auth", "token": token(outsider)})
        socket.receive_json()
        socket.send_json({"type": "subscribe", "project_id": str(home.project.id)})
        assert socket.receive_json() == {"type": "error", "code": "not_found"}


# ── a viewer has no composer ────────────────────────────────────────────────────────────────
def test_a_viewer_is_told_it_cannot_propose_and_is_refused_if_it_tries(
    api: TestClient, home: Home, make_user: Callable[..., User]
) -> None:
    viewer = make_user(role=DefaultRole.VIEWER)

    permissions = api.get(
        "/api/v1/me/permissions",
        params={"project": str(home.project.id)},
        headers=headers_for(viewer),
    ).json()["permissions"]
    proposed = api.post(
        f"/api/v1/projects/{home.project.id}/requirements",
        json={"fields": STATEMENT},
        headers=headers_for(viewer),
    )
    hints = api.post(
        f"/api/v1/projects/{home.project.id}/similar",
        json={"text": "sessions"},
        headers=headers_for(viewer),
    )

    assert "req.propose" not in permissions and "view" in permissions
    assert proposed.status_code == 403 and hints.status_code == 403
