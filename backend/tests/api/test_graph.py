"""Graph API v0 (US-14 groundwork): ``GET /projects/{p}/graph`` from stored findings."""

from collections.abc import Callable

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
