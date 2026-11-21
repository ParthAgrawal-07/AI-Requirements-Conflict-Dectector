"""Requirement activity timeline (Dhavni — US-42, FR-72)."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.permissions import DefaultRole
from app.models import (
    AnalysisRun,
    AnalysisRunStatus,
    AnalysisScope,
    ChangeRequest,
    Comment,
    Finding,
    FindingCategory,
    Issue,
    IssueRequirement,
    Project,
    RequirementState,
    RequirementTransition,
    User,
    Workspace,
)
from tests.analysis_helpers import make_post
from tests.api.conftest import headers_for


def url(requirement_id: object) -> str:
    return f"/api/v1/requirements/{requirement_id}/timeline"


def test_the_timeline_gathers_everything_that_happened(
    client: TestClient, db_session: Session, project: Project, user: User
) -> None:
    post = make_post(db_session, project, user, "Sessions end after 5 minutes.", label="REQ-31")
    now = datetime.now(UTC)
    finding = Finding(project_id=project.id, requirement_id=post.id,
                      category=FindingCategory.AMBIGUOUS, confidence=0.7, rationale="r",
                      original_ai_output={})  # fmt: skip
    run = AnalysisRun(project_id=project.id, scope=AnalysisScope.REQUIREMENT, subject_id=post.id,
                      status=AnalysisRunStatus.DONE, finished_at=now)  # fmt: skip
    issue = Issue(project_id=project.id, number=4, title="t", author_id=user.id)
    change_request = ChangeRequest(project_id=project.id, requirement_id=post.id, number=2,
                                   proposer_id=user.id, base_version=1, proposed_body="x",
                                   reason="Clearer", merged_at=now + timedelta(minutes=5),
                                   merged_by=user.id, merged_version=2)  # fmt: skip
    db_session.add_all([finding, run, issue, change_request])
    db_session.flush()
    db_session.add_all(
        [
            IssueRequirement(issue_id=issue.id, requirement_id=post.id),
            Comment(subject_type="requirement", subject_id=post.id, author_id=user.id, body="+1"),
            RequirementTransition(
                requirement_id=post.id,
                from_state=RequirementState.PROPOSED,
                to_state=RequirementState.APPROVED,
                version=2,
                actor_id=user.id,
                reason="Agreed in the review",
            ),  # fmt: skip
        ]
    )
    db_session.commit()

    body = client.get(url(post.id), headers=headers_for(user)).json()

    titles = {(e["kind"], e["title"]) for e in body["entries"]}
    assert ("post", "REQ-31 was posted") in titles
    assert ("analysis", "Analysis finished") in titles
    assert ("finding", "Ambiguous found by the AI") in titles
    assert ("issue", "ISS-4 opened") in titles
    assert ("change_request", "RCR-2 opened, proposing a change") in titles
    assert ("merge", "RCR-2 merged (version 2)") in titles
    assert ("comment", "Commented in the discussion") in titles
    assert ("state", "Moved from Proposed to Approved") in titles
    state = next(e for e in body["entries"] if e["kind"] == "state")
    assert state["detail"] == "Agreed in the review" and state["actor_name"] == "Test User"
    assert body["entries"][0]["kind"] == "merge"  # newest first
    merge = body["entries"][0]
    assert (merge["link_type"], merge["link_id"]) == ("change_request", str(change_request.id))
    assert "Sessions end" not in str(body["entries"])  # titles never repeat the statement


def test_the_timeline_filters_by_kind_and_orders_oldest_first(
    client: TestClient, db_session: Session, project: Project, user: User
) -> None:
    post = make_post(db_session, project, user, "x", label="REQ-1")
    db_session.add(Comment(subject_type="requirement", subject_id=post.id, author_id=user.id,
                           body="first", created_at=datetime.now(UTC) + timedelta(minutes=1)))  # fmt: skip
    db_session.commit()
    headers = headers_for(user)

    only = client.get(url(post.id), params={"kind": "comment"}, headers=headers).json()
    assert [e["kind"] for e in only["entries"]] == ["comment"]
    oldest = client.get(url(post.id), params={"order": "asc"}, headers=headers).json()
    assert [e["kind"] for e in oldest["entries"]] == ["post", "comment"]
    assert client.get(url(post.id), params={"kind": "gossip"}, headers=headers).status_code == 422


def test_every_member_who_sees_the_requirement_sees_its_timeline_and_no_one_else(
    client: TestClient,
    db_session: Session,
    project: Project,
    user: User,
    make_user: Callable[..., User],
    make_workspace: Callable[..., Workspace],
) -> None:
    post = make_post(db_session, project, user, "x", label="REQ-1")
    viewer = headers_for(make_user(role=DefaultRole.VIEWER))
    assert client.get(url(post.id), headers=viewer).status_code == 200
    outsider = headers_for(make_user(role=DefaultRole.OWNER, workspace=make_workspace()))
    assert client.get(url(post.id), headers=outsider).status_code == 404
