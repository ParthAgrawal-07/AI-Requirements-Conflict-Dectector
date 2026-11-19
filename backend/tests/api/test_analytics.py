"""Quality dashboard counts (Parth — US-13): the dashboard equals a direct database count."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.permissions import DefaultRole
from app.models import (
    CandidatePair,
    ChangeRequest,
    ConsequenceReport,
    Finding,
    FindingCategory,
    FindingStatus,
    Issue,
    IssueRequirement,
    Project,
    Requirement,
    RequirementState,
    Severity,
    User,
    Workspace,
)
from tests.api.conftest import headers_for


@pytest.fixture
def demo(
    db_session: Session,
    project: Project,
    make_requirement: Callable[..., Requirement],
    make_user: Callable[..., User],
) -> dict[str, Any]:
    riya = make_user(role=DefaultRole.DEVELOPER)
    reqs = [
        make_requirement(f"Requirement {n} shall hold.", source_req_id=f"REQ-{n}",
                         state=state, owner_id=riya.id if n % 2 else None,
                         stakeholder_group="Security" if n == 1 else None)
        for n, state in enumerate([RequirementState.APPROVED, RequirementState.APPROVED,
                                   RequirementState.PROPOSED, RequirementState.DEPRECATED], 1)
    ]  # fmt: skip
    first, second = CandidatePair.ordered(reqs[0].id, reqs[1].id)
    pair = CandidatePair(requirement_a_id=first, requirement_b_id=second, similarity_score=0.9)
    db_session.add(pair)
    db_session.flush()
    rows = [
        Finding(project_id=project.id, candidate_pair_id=pair.id, category=FindingCategory.CONFLICTING,
                confidence=0.9, rationale="r", original_ai_output={}, severity=Severity.HIGH),
        Finding(project_id=project.id, requirement_id=reqs[2].id, category=FindingCategory.AMBIGUOUS,
                confidence=0.6, rationale="r", original_ai_output={}, source="rule", rule_id="x"),
        Finding(project_id=project.id, requirement_id=reqs[1].id, category=FindingCategory.INCOMPLETE,
                confidence=0.6, rationale="r", original_ai_output={}, status=FindingStatus.DISMISSED),
        Finding(project_id=project.id, requirement_id=reqs[1].id, category=FindingCategory.AMBIGUOUS,
                confidence=0.6, rationale="r", original_ai_output={}, is_stale=True),
    ]  # fmt: skip
    db_session.add_all(rows)
    change = ChangeRequest(
        project_id=project.id,
        requirement_id=reqs[0].id,
        number=1,
        proposer_id=riya.id,
        base_version=1,
        proposed_body="x",
        reason="r",
    )
    old = ChangeRequest(project_id=project.id, requirement_id=reqs[1].id, number=2,
                        proposer_id=riya.id, base_version=1, proposed_body="y", reason="r",
                        status="merged")  # fmt: skip
    db_session.add_all([change, old])
    db_session.flush()
    db_session.add(ConsequenceReport(change_request_id=change.id, proposal_revision=1,
                                     base_version=1, baseline_revision=0, risk_level="high",
                                     risk_reasons=[], checks=[], affected=[], findings_delta={},
                                     llm_calls=0))  # fmt: skip
    issue = Issue(project_id=project.id, number=1, title="t", auto=True)
    closed = Issue(project_id=project.id, number=2, title="u", status="closed",
                   close_reason="manual")  # fmt: skip
    db_session.add_all([issue, closed])
    db_session.flush()
    db_session.add(IssueRequirement(issue_id=issue.id, requirement_id=reqs[0].id))
    db_session.commit()
    return {"riya": riya, "reqs": reqs}


def count(db: Session, sql: str, **params: object) -> int:
    return int(db.execute(text(sql), params).scalar_one())


def test_dashboard_counts_equal_database_counts(
    client: TestClient, db_session: Session, project: Project, demo: dict[str, Any]
) -> None:
    board = client.get(f"/api/v1/projects/{project.id}/analytics",
                       headers=headers_for(demo["riya"])).json()  # fmt: skip
    p = {"p": project.id}
    live = "FROM findings WHERE project_id = :p AND NOT is_stale"
    assert board["findings"]["total"] == count(db_session, f"SELECT count(*) {live}", **p) == 3
    assert board["findings"]["by_category"] == {"Ambiguous": 1, "Conflicting": 1, "Incomplete": 1}
    assert board["findings"]["by_status"] == {"dismissed": 1, "flagged": 2}
    assert board["findings"]["by_severity"] == {"high": 1, "unset": 2}
    assert board["findings"]["by_source"] == {"ai": 2, "rule": 1, "person": 0}
    assert (
        board["requirements"]["by_state"]["Approved"]
        == count(
            db_session,
            "SELECT count(*) FROM requirements WHERE project_id = :p AND state = 'Approved'",
            **p,
        )
        == 2
    )
    assert board["change_requests"] == {
        "open": 1, "by_risk": {"low": 0, "medium": 0, "high": 1, "unknown": 0}
    }  # fmt: skip
    assert (board["issues"]["open"], board["issues"]["closed"], board["issues"]["auto_open"]) == (
        1,
        1,
        1,
    )
    assert board["issues"]["closed_by_reason"] == {"manual": 1}


def test_filters_narrow_everything_to_those_requirements(
    client: TestClient, project: Project, demo: dict[str, Any]
) -> None:
    board = client.get(f"/api/v1/projects/{project.id}/analytics", params={"group": "security"},
                       headers=headers_for(demo["riya"])).json()  # fmt: skip
    assert board["filters"] == {"stakeholder_group": "security"}
    assert board["requirements"]["total"] == 1
    assert board["findings"]["by_category"] == {"Conflicting": 1}
    assert (board["change_requests"]["open"], board["issues"]["open"]) == (1, 1)


def test_role_appropriate_default_filters(
    client: TestClient, project: Project, demo: dict[str, Any], make_user: Callable[..., User]
) -> None:
    developer = client.get(f"/api/v1/projects/{project.id}/analytics",
                           headers=headers_for(demo["riya"])).json()  # fmt: skip
    assert developer["suggested_filters"] == {"owner": str(demo["riya"].id)}
    analyst = make_user(role=DefaultRole.BUSINESS_ANALYST)
    board = client.get(f"/api/v1/projects/{project.id}/analytics", headers=headers_for(analyst))
    assert board.json()["suggested_filters"] == {}


def test_the_workspace_dashboard_sums_projects(
    client: TestClient,
    project: Project,
    workspace: Workspace,
    demo: dict[str, Any],
    make_project: Callable[..., Project],
) -> None:
    make_project(name="Second")
    body = client.get(f"/api/v1/workspaces/{workspace.id}/analytics",
                      headers=headers_for(demo["riya"])).json()  # fmt: skip
    assert len(body["projects"]) == 2
    assert body["totals"]["requirements"] == 4 and body["totals"]["high_findings"] == 1


def test_another_workspace_is_404(
    client: TestClient,
    project: Project,
    make_workspace: Callable[..., Workspace],
    make_user: Callable[..., User],
) -> None:
    outsider = headers_for(make_user(role=DefaultRole.OWNER, workspace=make_workspace()))
    assert (
        client.get(f"/api/v1/projects/{project.id}/analytics", headers=outsider).status_code == 404
    )
