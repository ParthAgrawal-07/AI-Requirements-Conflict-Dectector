"""Automatic conflict issues (Dhavni — US-52, FR-87; design update §3.5)."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import DefaultRole
from app.graph import service as graph_service
from app.models import (
    AnalysisRun,
    AnalysisRunStatus,
    AnalysisScope,
    CandidatePair,
    Clarification,
    Comment,
    Finding,
    FindingCategory,
    Issue,
    Membership,
    Project,
    Requirement,
    Severity,
    User,
)
from app.realtime import bus
from app.services import issues
from app.services.issues import ConflictIssueOpener
from tests.api.conftest import headers_for


@pytest.fixture
def events(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    published: list[Any] = []
    monkeypatch.setattr(bus, "publish", published.append)
    return published


class Scenario:
    def __init__(
        self,
        db: Session,
        project: Project,
        make_user: Callable[..., User],
        make_requirement: Callable[..., Requirement],
    ) -> None:
        self.db, self.project = db, project
        self.asha = make_user(role=DefaultRole.BUSINESS_ANALYST)
        self.ravi = make_user(role=DefaultRole.DEVELOPER)
        self.a = make_requirement(
            "Sessions end after 30 minutes.", source_req_id="REQ-014", owner_id=self.asha.id
        )
        self.b = make_requirement(
            "Sessions end after 5 minutes.", source_req_id="REQ-031", owner_id=self.ravi.id
        )
        first, second = CandidatePair.ordered(self.a.id, self.b.id)
        self.pair = CandidatePair(
            requirement_a_id=first, requirement_b_id=second, similarity_score=0.9
        )
        db.add(self.pair)
        db.commit()

    def run_with(
        self,
        category: FindingCategory = FindingCategory.CONFLICTING,
        severity: Severity | None = Severity.HIGH,
    ) -> tuple[AnalysisRun, Finding]:
        run = AnalysisRun(
            project_id=self.project.id,
            scope=AnalysisScope.REQUIREMENT,
            subject_id=self.b.id,
            status=AnalysisRunStatus.DONE,
        )
        self.db.add(run)
        self.db.flush()
        finding = Finding(
            project_id=self.project.id,
            analysis_run_id=run.id,
            candidate_pair_id=self.pair.id,
            category=category,
            severity=severity,
            confidence=0.9,
            rationale="30 vs 5 minutes",
            explanation="REQ-014 and REQ-031 set different inactivity limits.",
            original_ai_output={},
        )
        self.db.add(finding)
        self.db.commit()
        return run, finding

    def auto_issues(self) -> list[Issue]:
        return list(self.db.scalars(select(Issue).where(Issue.auto.is_(True))))


@pytest.fixture
def s(
    db_session: Session,
    project: Project,
    make_user: Callable[..., User],
    make_requirement: Callable[..., Requirement],
) -> Scenario:
    return Scenario(db_session, project, make_user, make_requirement)


def test_a_conflict_between_two_owners_opens_an_issue_for_both(
    s: Scenario, events: list[Any]
) -> None:
    run, finding = s.run_with()

    [issue] = ConflictIssueOpener(s.db).on_run(run)

    item = issues.view(s.db, issue)
    assert issue.auto and issue.finding_id == finding.id and issue.author_id is None
    assert issue.title == "Conflict between REQ-014 and REQ-031"
    assert issue.labels == ["conflicting", "severity:high", "auto"]
    assert {u.id for u in item.assignees} == {s.asha.id, s.ravi.id}
    assert {r.id for r in item.requirements} == {s.a.id, s.b.id}
    [delta] = [e for e in events if e.type == "graph.delta"]
    assert delta.data["sentences"] == [
        "ISS-1 opened for the conflict between REQ-014 and REQ-031: assigned to Test User and Test User."
    ]


def test_one_issue_per_finding(s: Scenario) -> None:
    run, _ = s.run_with()
    opener = ConflictIssueOpener(s.db)
    opener.on_run(run)
    opener.on_run(run)
    assert len(s.auto_issues()) == 1


@pytest.mark.parametrize(
    ("category", "severity"),
    [
        (FindingCategory.CONFLICTING, Severity.LOW),
        (FindingCategory.CONFLICTING, None),
        (FindingCategory.DEPENDENT, Severity.HIGH),
    ],
)
def test_no_issue_below_medium_or_for_other_categories(
    s: Scenario, category: FindingCategory, severity: Severity | None
) -> None:
    run, _ = s.run_with(category, severity)
    assert ConflictIssueOpener(s.db).on_run(run) == []


def test_a_duplicate_of_medium_severity_qualifies(s: Scenario) -> None:
    run, _ = s.run_with(FindingCategory.DUPLICATE, Severity.MEDIUM)
    [issue] = ConflictIssueOpener(s.db).on_run(run)
    assert issue.title == "Possible duplicate between REQ-014 and REQ-031"


def test_one_owner_is_not_a_conflict_between_people(s: Scenario) -> None:
    s.b.owner_id = s.asha.id
    s.db.commit()
    run, _ = s.run_with()
    assert ConflictIssueOpener(s.db).on_run(run) == []


def test_the_question_becomes_the_first_comment(s: Scenario) -> None:
    run, finding = s.run_with()
    s.db.add(Clarification(finding_id=finding.id, question="5 or 30 minutes?"))
    s.db.commit()
    s.db.refresh(finding)

    [issue] = ConflictIssueOpener(s.db).on_run(run)
    issues.add_question(s.db, finding)  # the clarification task calling again adds nothing

    bodies = [c.body for c in issues.comments(s.db, issue.id)]
    assert bodies == ["Clarification question: 5 or 30 minutes?"]
    assert s.db.scalar(select(Comment.author_id).where(Comment.subject_id == issue.id)) is None


def test_dismissing_the_finding_closes_the_issue_and_reopening_brings_it_back(
    s: Scenario, client: TestClient
) -> None:
    run, finding = s.run_with()
    [issue] = ConflictIssueOpener(s.db).on_run(run)
    url = f"/api/v1/findings/{finding.id}/review"

    dismissed = client.post(
        url, json={"action": "dismiss", "reason": "Different apps"}, headers=headers_for(s.asha)
    )
    s.db.refresh(issue)
    closed = (issue.status, issue.close_reason)
    client.post(url, json={"action": "reopen"}, headers=headers_for(s.asha))
    s.db.refresh(issue)

    assert dismissed.status_code == 200
    assert closed == ("closed", "finding_resolved")
    assert (issue.status, issue.close_reason) == ("open", None)


def test_accepted_and_answered_closes_it(s: Scenario, client: TestClient) -> None:
    run, finding = s.run_with()
    question = Clarification(finding_id=finding.id, question="5 or 30 minutes?")
    s.db.add(question)
    s.db.commit()
    [issue] = ConflictIssueOpener(s.db).on_run(run)

    client.post(
        f"/api/v1/findings/{finding.id}/review",
        json={"action": "confirm"},
        headers=headers_for(s.asha),
    )
    s.db.refresh(issue)
    still_open = issue.status
    client.post(
        f"/api/v1/clarifications/{question.id}/answer",
        json={"resolution": "5 minutes for everyone"},
        headers=headers_for(s.ravi),
    )
    s.db.refresh(issue)

    assert still_open == "open"
    assert (issue.status, issue.close_reason) == ("closed", "finding_resolved")


def test_a_manual_close_is_not_undone_by_a_review(s: Scenario, client: TestClient) -> None:
    run, finding = s.run_with()
    [issue] = ConflictIssueOpener(s.db).on_run(run)
    issues.close(s.db, issue, "manual", actor=s.asha)

    client.post(
        f"/api/v1/findings/{finding.id}/review",
        json={"action": "confirm"},
        headers=headers_for(s.asha),
    )
    s.db.refresh(issue)
    assert issue.close_reason == "manual"


def test_the_same_conflict_found_again_reopens_the_same_issue(
    s: Scenario, events: list[Any]
) -> None:
    run, old = s.run_with()
    [issue] = ConflictIssueOpener(s.db).on_run(run)
    old.is_stale = True  # REQ-031 was edited: its findings are history
    s.db.commit()
    issues.on_finding_changed(s.db, old, actor=None)
    s.db.refresh(issue)
    closed = issue.status

    rerun, new = s.run_with()
    again = ConflictIssueOpener(s.db).on_run(rerun)

    s.db.refresh(issue)
    assert closed == "closed"
    assert again == [issue] and issue.finding_id == new.id and issue.status == "open"
    assert len(s.auto_issues()) == 1
    sentences = [x for e in events if e.type == "graph.delta" for x in e.data["sentences"]]
    assert "ISS-1 reopened: its conflict was found again." in sentences


def test_the_map_counts_open_issues(s: Scenario) -> None:
    run, _ = s.run_with()
    [issue] = ConflictIssueOpener(s.db).on_run(run)
    counts = {n.id: n.open_issues for n in graph_service.nodes(s.db, s.project.id)}
    issues.close(s.db, issue, "manual", actor=s.asha)
    after = {n.id: n.open_issues for n in graph_service.nodes(s.db, s.project.id)}
    assert counts[s.a.id] == counts[s.b.id] == 1
    assert after[s.a.id] == 0


def test_an_owner_who_left_is_not_assigned(s: Scenario, db_session: Session) -> None:
    membership = db_session.scalar(select(Membership).where(Membership.user_id == s.ravi.id))
    assert membership is not None
    membership.ended_at = membership.joined_at
    db_session.commit()
    run, _ = s.run_with()

    [issue] = ConflictIssueOpener(s.db).on_run(run)

    assert [u.id for u in issues.view(s.db, issue).assignees] == [s.asha.id]
