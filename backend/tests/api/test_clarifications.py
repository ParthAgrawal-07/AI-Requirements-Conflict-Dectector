"""Clarification routes (Madhav — US-09, FR-23): read a question, answer it once (recorded in the
history of every requirement involved), and ask for one on demand."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clarification.tasks import GENERATE_FOR_FINDING
from app.core.permissions import DefaultRole
from app.models import (
    AuditAction,
    AuditLog,
    CandidatePair,
    Clarification,
    Finding,
    FindingCategory,
    FindingStatus,
    Requirement,
    User,
    Workspace,
)
from tests.api.conftest import headers_for

QUESTION = "Should the limit be 2 seconds (REQ-014) or 10 seconds (REQ-015)?"


@pytest.fixture
def finding(db_session: Session, make_requirement: Callable[..., Requirement]) -> Finding:
    a = make_requirement("2 seconds.", source_req_id="REQ-014")
    b = make_requirement("10 seconds.", source_req_id="REQ-015")
    first, second = CandidatePair.ordered(a.id, b.id)
    pair = CandidatePair(requirement_a_id=first, requirement_b_id=second, similarity_score=0.9)
    db_session.add(pair)
    db_session.flush()
    finding = Finding(
        project_id=a.project_id,
        document_id=a.document_id,
        candidate_pair_id=pair.id,
        category=FindingCategory.CONFLICTING,
        confidence=0.9,
        rationale="r",
        original_ai_output={},
    )
    db_session.add(finding)
    db_session.commit()
    return finding


@pytest.fixture
def clarification(db_session: Session, finding: Finding) -> Clarification:
    row = Clarification(finding_id=finding.id, question=QUESTION, addressed_to="owner")
    db_session.add(row)
    db_session.commit()
    return row


def answer(client: TestClient, clarification: Clarification, who: User, text: str) -> Any:
    return client.post(
        f"/api/v1/clarifications/{clarification.id}/answer",
        json={"resolution": text},
        headers=headers_for(who),
    )


def test_a_member_reads_the_question_and_the_finding_card_shows_it(
    client: TestClient,
    finding: Finding,
    clarification: Clarification,
    make_user: Callable[..., User],
) -> None:
    viewer = make_user(role=DefaultRole.VIEWER)

    read = client.get(f"/api/v1/findings/{finding.id}/clarification", headers=headers_for(viewer))
    card = client.get(f"/api/v1/findings/{finding.id}", headers=headers_for(viewer))

    assert read.status_code == 200
    assert (read.json()["question"], read.json()["answered"], read.json()["source"]) == (
        QUESTION,
        False,
        "AI",
    )
    assert card.json()["clarification"]["id"] == str(clarification.id)


def test_answering_records_the_resolution_in_each_requirements_history(
    client: TestClient,
    db_session: Session,
    finding: Finding,
    clarification: Clarification,
    make_user: Callable[..., User],
) -> None:
    stakeholder = make_user(role=DefaultRole.STAKEHOLDER)

    response = answer(client, clarification, stakeholder, "10 seconds for partner APIs only")
    again = answer(client, clarification, stakeholder, "changed my mind")

    assert response.status_code == 200
    body = response.json()
    assert body["answered"] is True and body["resolution"] == "10 seconds for partner APIs only"
    assert body["resolved_by"] == str(stakeholder.id)
    assert again.status_code == 409 and again.json()["error"]["code"] == "already_answered"
    history = db_session.scalars(
        select(AuditLog).where(AuditLog.action == AuditAction.CLARIFICATION_ANSWERED)
    ).all()
    assert len(history) == 2 and {h.finding_id for h in history} == {finding.id}


def test_a_finding_is_resolved_once_accepted_and_answered(
    client: TestClient,
    db_session: Session,
    finding: Finding,
    clarification: Clarification,
    user: User,
) -> None:
    url = f"/api/v1/findings/{finding.id}"
    finding.status = FindingStatus.CONFIRMED
    db_session.commit()
    assert client.get(url, headers=headers_for(user)).json()["resolved"] is False

    answer(client, clarification, user, "10 seconds for partner APIs only")

    assert client.get(url, headers=headers_for(user)).json()["resolved"] is True


def test_a_viewer_cannot_answer(
    client: TestClient, clarification: Clarification, make_user: Callable[..., User]
) -> None:
    viewer = make_user(role=DefaultRole.VIEWER)

    assert answer(client, clarification, viewer, "whatever it is").status_code == 403


def test_a_question_can_be_requested_and_is_queued(
    client: TestClient,
    finding: Finding,
    user: User,
    followups: list[tuple[str, list[str]]],
) -> None:
    response = client.post(
        f"/api/v1/findings/{finding.id}/clarification", headers=headers_for(user)
    )

    assert response.status_code == 202
    assert followups == [(GENERATE_FOR_FINDING, [str(finding.id)])]


def test_no_question_is_requested_twice_or_for_a_duplicate(
    client: TestClient,
    db_session: Session,
    finding: Finding,
    clarification: Clarification,
    user: User,
) -> None:
    twice = client.post(f"/api/v1/findings/{finding.id}/clarification", headers=headers_for(user))
    finding.category = FindingCategory.DUPLICATE
    db_session.commit()
    duplicate = client.post(
        f"/api/v1/findings/{finding.id}/clarification", headers=headers_for(user)
    )

    assert twice.json()["error"]["code"] == "already_asked"
    assert duplicate.json()["error"]["code"] == "no_question_needed"


def test_another_workspaces_question_is_a_404(
    client: TestClient,
    finding: Finding,
    clarification: Clarification,
    make_user: Callable[..., User],
    make_workspace: Callable[..., Workspace],
) -> None:
    stranger = make_user(role=DefaultRole.OWNER, workspace=make_workspace())

    assert answer(client, clarification, stranger, "nope nope").status_code == 404
    assert (
        client.get(
            f"/api/v1/findings/{finding.id}/clarification", headers=headers_for(stranger)
        ).status_code
        == 404
    )


def test_a_finding_without_a_question_says_so(
    client: TestClient, finding: Finding, user: User
) -> None:
    response = client.get(f"/api/v1/findings/{finding.id}/clarification", headers=headers_for(user))

    assert response.status_code == 404
