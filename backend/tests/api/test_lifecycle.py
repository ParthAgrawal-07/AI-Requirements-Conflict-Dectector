"""Requirement lifecycle (Parth — US-37, FR-61, FR-98, FR-21): legal moves by permission, 409 for
illegal ones, the agreement rules for approval, the author's withdrawal and the sign-off."""

from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import DefaultRole
from app.models import (
    AuditAction,
    AuditLog,
    CandidatePair,
    ClassificationStatus,
    Finding,
    FindingCategory,
    FindingStatus,
    Project,
    Requirement,
    RequirementState,
    RequirementTransition,
    Severity,
    User,
    Workspace,
)
from app.realtime import bus
from app.realtime.events import GRAPH_DELTA
from tests.analysis_helpers import make_post
from tests.api.conftest import headers_for

S = RequirementState


@pytest.fixture
def events(monkeypatch: pytest.MonkeyPatch) -> Iterator[bus.InProcessEventBus]:
    test_bus = bus.InProcessEventBus()
    monkeypatch.setattr(bus, "get_bus", lambda: test_bus)
    yield test_bus


@pytest.fixture
def analyst(make_user: Callable[..., User]) -> User:
    return make_user(role=DefaultRole.BUSINESS_ANALYST)


@pytest.fixture
def author(make_user: Callable[..., User]) -> User:
    return make_user(role=DefaultRole.DEVELOPER)


@pytest.fixture
def requirement(db_session: Session, project: Project, author: User) -> Requirement:
    """A posted requirement whose analysis is current (checked, no pending comparisons)."""
    post = make_post(db_session, project, author, "Sessions end after 5 minutes.", label="REQ-031")
    post.single_checked_version = 1
    db_session.commit()
    return post


def patch(client: TestClient, requirement: Requirement, who: User, **body: Any) -> Any:
    return client.patch(
        f"/api/v1/requirements/{requirement.id}",
        json={"version": requirement.current_version, **body},
        headers=headers_for(who),
    )


def move(db: Session, requirement: Requirement, state: RequirementState) -> None:
    requirement.state = state
    db.commit()


def test_an_analyst_starts_the_review_and_approves_and_both_are_recorded(
    client: TestClient,
    db_session: Session,
    requirement: Requirement,
    analyst: User,
    events: bus.InProcessEventBus,
) -> None:
    started = patch(client, requirement, analyst, state="Under_Review")
    approved = patch(client, requirement, analyst, state="Approved")

    assert started.status_code == 200 and approved.status_code == 200
    detail = approved.json()
    assert detail["state"] == "Approved"
    assert [(t["from_state"], t["to_state"]) for t in detail["transitions"]] == [
        ("Proposed", "Under_Review"),
        ("Under_Review", "Approved"),
    ]
    actions = db_session.scalars(
        select(AuditLog.action).where(AuditLog.requirement_id == requirement.id)
    ).all()
    assert actions.count(AuditAction.STATE_CHANGED) == 2
    sentences = [e.data["sentences"] for e in events.published if e.type == GRAPH_DELTA]
    assert sentences[-1] == ["Test User approved REQ-031."]


@pytest.mark.parametrize(
    ("start", "target"),
    [
        (S.PROPOSED, S.APPROVED),  # skips the review
        (S.REJECTED, S.PROPOSED),  # terminal
        (S.UNDER_REVIEW, S.PROPOSED),
        (S.IMPLEMENTED, S.APPROVED),
    ],
)
def test_illegal_moves_are_a_409(
    client: TestClient,
    db_session: Session,
    requirement: Requirement,
    analyst: User,
    start: RequirementState,
    target: RequirementState,
) -> None:
    move(db_session, requirement, start)

    response = patch(client, requirement, analyst, state=target.value)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "illegal_transition"


def test_deprecation_waits_for_a_change_request(
    client: TestClient, db_session: Session, requirement: Requirement, analyst: User
) -> None:
    move(db_session, requirement, S.APPROVED)

    response = patch(client, requirement, analyst, state="Deprecated")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "needs_change_request"


def test_a_developer_cannot_approve_but_can_mark_implemented(
    client: TestClient,
    db_session: Session,
    requirement: Requirement,
    make_user: Callable[..., User],
) -> None:
    developer = make_user(role=DefaultRole.DEVELOPER)
    move(db_session, requirement, S.UNDER_REVIEW)
    assert patch(client, requirement, developer, state="Approved").status_code == 403

    move(db_session, requirement, S.APPROVED)
    assert patch(client, requirement, developer, state="Implemented").status_code == 200


def test_only_the_author_may_withdraw_a_proposal(
    client: TestClient,
    requirement: Requirement,
    author: User,
    make_user: Callable[..., User],
) -> None:
    other = make_user(role=DefaultRole.DEVELOPER)

    assert patch(client, requirement, other, state="Rejected").status_code == 403
    assert patch(client, requirement, author, state="Rejected").status_code == 200


def test_a_rejection_needs_a_reason(
    client: TestClient, db_session: Session, requirement: Requirement, analyst: User
) -> None:
    move(db_session, requirement, S.UNDER_REVIEW)

    missing = patch(client, requirement, analyst, state="Rejected")
    given = patch(client, requirement, analyst, state="Rejected", reason="Out of scope for v1")

    assert missing.status_code == 400 and missing.json()["error"]["code"] == "reason_required"
    assert given.status_code == 200
    transition = db_session.scalar(select(RequirementTransition))
    assert transition is not None and transition.reason == "Out of scope for v1"


def test_approval_needs_the_version_that_was_reviewed(
    client: TestClient, db_session: Session, requirement: Requirement, analyst: User
) -> None:
    move(db_session, requirement, S.UNDER_REVIEW)

    response = client.patch(
        f"/api/v1/requirements/{requirement.id}",
        json={"state": "Approved", "version": 2},
        headers=headers_for(analyst),
    )

    assert response.status_code == 409 and response.json()["error"]["code"] == "version_changed"


def test_approval_waits_for_analysis_of_the_current_text(
    client: TestClient,
    db_session: Session,
    project: Project,
    requirement: Requirement,
    analyst: User,
    author: User,
) -> None:
    other = make_post(db_session, project, author, "Sessions end after 30 minutes.")
    first, second = CandidatePair.ordered(requirement.id, other.id)
    db_session.add(
        CandidatePair(
            requirement_a_id=first,
            requirement_b_id=second,
            similarity_score=0.9,
            classification_status=ClassificationStatus.PENDING,
        )
    )
    move(db_session, requirement, S.UNDER_REVIEW)

    response = patch(client, requirement, analyst, state="Approved")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "analysis_not_current"
    detail = client.get(f"/api/v1/requirements/{requirement.id}", headers=headers_for(analyst))
    assert detail.json()["readiness"]["analysis_current"] is False


def test_an_open_high_finding_blocks_approval_unless_the_risk_is_accepted(
    client: TestClient, db_session: Session, requirement: Requirement, analyst: User
) -> None:
    finding = Finding(
        project_id=requirement.project_id,
        requirement_id=requirement.id,
        category=FindingCategory.AMBIGUOUS,
        confidence=0.9,
        rationale="r",
        original_ai_output={},
        severity=Severity.HIGH,
    )
    db_session.add(finding)
    move(db_session, requirement, S.UNDER_REVIEW)

    blocked = patch(client, requirement, analyst, state="Approved")
    no_reason = patch(client, requirement, analyst, state="Approved", accepted_risk=True)
    accepted = patch(
        client,
        requirement,
        analyst,
        state="Approved",
        accepted_risk=True,
        reason="Ops will tune the limit after the pilot",
    )

    assert blocked.json()["error"]["code"] == "open_high_severity"
    assert no_reason.json()["error"]["code"] == "reason_required"
    assert accepted.status_code == 200
    assert accepted.json()["transitions"][-1]["accepted_risk"] is True


def test_a_dismissed_high_finding_does_not_block(
    client: TestClient, db_session: Session, requirement: Requirement, analyst: User
) -> None:
    db_session.add(
        Finding(
            project_id=requirement.project_id,
            requirement_id=requirement.id,
            category=FindingCategory.AMBIGUOUS,
            confidence=0.9,
            rationale="r",
            original_ai_output={},
            severity=Severity.HIGH,
            status=FindingStatus.DISMISSED,
        )
    )
    move(db_session, requirement, S.UNDER_REVIEW)

    assert patch(client, requirement, analyst, state="Approved").status_code == 200


def test_a_protected_requirement_needs_a_sign_off_on_its_current_version(
    client: TestClient,
    db_session: Session,
    requirement: Requirement,
    analyst: User,
    make_user: Callable[..., User],
) -> None:
    reviewer = make_user(role=DefaultRole.COMPLIANCE_REVIEWER)
    requirement.is_protected = True
    move(db_session, requirement, S.UNDER_REVIEW)

    before = patch(client, requirement, analyst, state="Approved")
    signed = client.post(
        f"/api/v1/requirements/{requirement.id}/signoff",
        json={"version": 1},
        headers=headers_for(reviewer),
    )
    after = patch(client, requirement, analyst, state="Approved")

    assert before.json()["error"]["code"] == "signoff_required"
    assert signed.status_code == 200 and signed.json()["signed_off_version"] == 1
    assert after.status_code == 200
    audit = db_session.scalar(
        select(AuditLog).where(
            AuditLog.requirement_id == requirement.id, AuditLog.action == AuditAction.SIGNED_OFF
        )
    )
    assert audit is not None and audit.actor_id == reviewer.id


def test_an_analyst_cannot_sign_off(
    client: TestClient, db_session: Session, requirement: Requirement, analyst: User
) -> None:
    requirement.is_protected = True
    db_session.commit()

    response = client.post(
        f"/api/v1/requirements/{requirement.id}/signoff",
        json={"version": 1},
        headers=headers_for(analyst),
    )

    assert response.status_code == 403


def test_the_drawer_lists_only_the_moves_the_caller_may_make(
    client: TestClient,
    requirement: Requirement,
    analyst: User,
    author: User,
    make_user: Callable[..., User],
) -> None:
    viewer = make_user(role=DefaultRole.VIEWER)
    url = f"/api/v1/requirements/{requirement.id}"

    assert client.get(url, headers=headers_for(analyst)).json()["allowed_transitions"] == [
        "Under_Review"
    ]
    assert client.get(url, headers=headers_for(author)).json()["allowed_transitions"] == [
        "Rejected"
    ]
    viewed = client.get(url, headers=headers_for(viewer)).json()
    assert viewed["allowed_transitions"] == [] and viewed["source_req_id"] == "REQ-031"


def test_another_workspaces_requirement_is_a_404(
    client: TestClient,
    requirement: Requirement,
    make_user: Callable[..., User],
    make_workspace: Callable[..., Workspace],
) -> None:
    stranger = make_user(role=DefaultRole.OWNER, workspace=make_workspace())

    assert (
        client.get(
            f"/api/v1/requirements/{requirement.id}", headers=headers_for(stranger)
        ).status_code
        == 404
    )
    assert patch(client, requirement, stranger, state="Under_Review").status_code == 404


def test_a_patch_without_a_state_changes_nothing(
    client: TestClient, requirement: Requirement, analyst: User
) -> None:
    response = client.patch(
        f"/api/v1/requirements/{requirement.id}", json={}, headers=headers_for(analyst)
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "nothing_to_change"
