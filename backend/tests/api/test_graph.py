"""Graph API v0 (US-14 groundwork): ``GET /projects/{p}/graph`` from stored findings."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.permissions import DefaultRole
from app.models import (
    CandidatePair,
    Finding,
    FindingCategory,
    FindingStatus,
    Project,
    Requirement,
    Severity,
    User,
    Workspace,
)
from app.realtime import bus
from app.realtime.events import GRAPH_DELTA
from tests.api.conftest import headers_for


def _pair_finding(
    db: Session,
    a: Requirement,
    b: Requirement,
    category: FindingCategory,
    **extra: object,
) -> Finding:
    first, second = CandidatePair.ordered(a.id, b.id)
    pair = CandidatePair(requirement_a_id=first, requirement_b_id=second, similarity_score=0.9)
    db.add(pair)
    db.flush()
    finding = Finding(
        project_id=a.project_id,
        document_id=a.document_id,
        candidate_pair_id=pair.id,
        category=category,
        confidence=0.86,
        rationale="r",
        original_ai_output=extra.pop("output", {}),
        **extra,
    )
    db.add(finding)
    db.commit()
    return finding


def test_requirements_are_nodes_and_findings_are_edges(
    client: TestClient,
    db_session: Session,
    project: Project,
    user: User,
    make_requirement: Callable[..., Requirement],
) -> None:
    r14 = make_requirement("Sessions expire after 30 minutes.", source_req_id="REQ-014")
    r31 = make_requirement("Sessions expire after 5 minutes.", source_req_id="REQ-031")
    vague = make_requirement("The app shall be fast.", source_req_id="REQ-040")
    conflict = _pair_finding(
        db_session, r14, r31, FindingCategory.CONFLICTING, severity=Severity.HIGH
    )
    ambiguous = Finding(
        project_id=vague.project_id,
        document_id=vague.document_id,
        requirement_id=vague.id,
        category=FindingCategory.AMBIGUOUS,
        confidence=0.7,
        rationale="r",
        original_ai_output={},
    )
    db_session.add(ambiguous)
    db_session.commit()

    response = client.get(f"/api/v1/projects/{project.id}/graph", headers=headers_for(user))

    assert response.status_code == 200
    graph = response.json()
    assert graph["revision"] == 0
    assert {n["label"] for n in graph["nodes"]} == {"REQ-014", "REQ-031", "REQ-040"}
    edges = {e["id"]: e for e in graph["edges"]}
    assert edges[str(conflict.id)]["kind"] == "conflict"
    assert edges[str(conflict.id)]["severity"] == "high"
    assert {edges[str(conflict.id)]["source"], edges[str(conflict.id)]["target"]} == {
        str(r14.id),
        str(r31.id),
    }
    assert edges[str(ambiguous.id)]["source"] == edges[str(ambiguous.id)]["target"] == str(vague.id)
    assert "expire" not in response.text  # nodes carry printed IDs, not statements


def test_a_dependency_edge_points_from_the_dependant(
    client: TestClient,
    db_session: Session,
    project: Project,
    user: User,
    make_requirement: Callable[..., Requirement],
) -> None:
    a, b = make_requirement("A"), make_requirement("B")
    first, second = CandidatePair.ordered(a.id, b.id)
    finding = _pair_finding(
        db_session,
        a,
        b,
        FindingCategory.DEPENDENT,
        output={"dependency_direction": "B_depends_on_A"},
    )

    (edge,) = client.get(f"/api/v1/projects/{project.id}/graph", headers=headers_for(user)).json()[
        "edges"
    ]

    assert edge["id"] == str(finding.id)
    assert (edge["source"], edge["target"]) == (str(second), str(first))


def test_dismissed_findings_are_hidden_unless_asked_for(
    client: TestClient,
    db_session: Session,
    project: Project,
    user: User,
    make_requirement: Callable[..., Requirement],
) -> None:
    a, b = make_requirement("A"), make_requirement("B")
    _pair_finding(db_session, a, b, FindingCategory.DUPLICATE, status=FindingStatus.DISMISSED)
    url = f"/api/v1/projects/{project.id}/graph"

    assert client.get(url, headers=headers_for(user)).json()["edges"] == []
    shown = client.get(url, params={"include_dismissed": True}, headers=headers_for(user))
    assert len(shown.json()["edges"]) == 1


def test_another_workspaces_graph_is_a_404(
    client: TestClient,
    project: Project,
    make_user: Callable[..., User],
    make_workspace: Callable[..., Workspace],
) -> None:
    stranger = make_user(role=DefaultRole.OWNER, workspace=make_workspace())
    response = client.get(f"/api/v1/projects/{project.id}/graph", headers=headers_for(stranger))
    assert response.status_code == 404


# ── Sprint 3: revisions, hidden edges, positions (US-14) ───────────────────────────────────
def test_a_client_holding_the_current_revision_gets_304(
    client: TestClient, db_session: Session, project: Project, user: User
) -> None:
    project.graph_revision = 7
    db_session.commit()
    url = f"/api/v1/projects/{project.id}/graph"

    current = client.get(url, params={"revision": 7}, headers=headers_for(user))
    behind = client.get(url, params={"revision": 6}, headers=headers_for(user))

    assert current.status_code == 304 and current.content == b""
    assert behind.status_code == 200 and behind.json()["revision"] == 7


def test_stale_and_merged_findings_are_not_on_the_map(
    client: TestClient,
    db_session: Session,
    project: Project,
    user: User,
    make_requirement: Callable[..., Requirement],
) -> None:
    a, b, c = make_requirement("A"), make_requirement("B"), make_requirement("C")
    _pair_finding(db_session, a, b, FindingCategory.DUPLICATE, is_stale=True)
    _pair_finding(db_session, a, c, FindingCategory.DUPLICATE, status=FindingStatus.MERGED)
    url = f"/api/v1/projects/{project.id}/graph"

    shown = client.get(url, params={"include_dismissed": True}, headers=headers_for(user))

    assert shown.json()["edges"] == []


def test_saved_positions_come_back_in_the_snapshot_and_reach_other_maps(
    client: TestClient,
    db_session: Session,
    project: Project,
    make_user: Callable[..., User],
    make_requirement: Callable[..., Requirement],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_bus = bus.InProcessEventBus()
    monkeypatch.setattr(bus, "get_bus", lambda: test_bus)
    requirement = make_requirement("A", source_req_id="REQ-001")
    developer = make_user(role=DefaultRole.DEVELOPER)

    saved = client.put(
        f"/api/v1/projects/{project.id}/graph/positions",
        json={"positions": [{"requirement_id": str(requirement.id), "x": 12.5, "y": -40}]},
        headers=headers_for(developer),
    )

    assert saved.status_code == 204
    (node,) = client.get(
        f"/api/v1/projects/{project.id}/graph", headers=headers_for(developer)
    ).json()["nodes"]
    assert (node["x"], node["y"]) == (12.5, -40)
    (event,) = [e for e in test_bus.published if e.type == GRAPH_DELTA]
    assert event.data["sentences"] == []  # layout only: nothing to say in the feed
    assert event.data["changed"]["nodes"][0]["x"] == 12.5


def test_a_viewer_cannot_rearrange_the_shared_layout(
    client: TestClient,
    project: Project,
    make_user: Callable[..., User],
    make_requirement: Callable[..., Requirement],
) -> None:
    requirement = make_requirement("A")

    response = client.put(
        f"/api/v1/projects/{project.id}/graph/positions",
        json={"positions": [{"requirement_id": str(requirement.id), "x": 1, "y": 1}]},
        headers=headers_for(make_user(role=DefaultRole.VIEWER)),
    )

    assert response.status_code == 403


def test_positions_for_another_projects_requirements_are_refused(
    client: TestClient,
    db_session: Session,
    project: Project,
    user: User,
    make_project: Callable[..., Project],
    make_requirement: Callable[..., Requirement],
) -> None:
    other = make_project()
    requirement = make_requirement("A")

    response = client.put(
        f"/api/v1/projects/{other.id}/graph/positions",
        json={"positions": [{"requirement_id": str(requirement.id), "x": 1, "y": 1}]},
        headers=headers_for(user),
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unknown_requirement"


def test_positions_must_be_finite(
    client: TestClient, project: Project, user: User, make_requirement: Callable[..., Requirement]
) -> None:
    requirement = make_requirement("A")

    response = client.put(
        f"/api/v1/projects/{project.id}/graph/positions",
        json={"positions": [{"requirement_id": str(requirement.id), "x": 1e12, "y": 1}]},
        headers=headers_for(user),
    )

    assert response.status_code == 422
