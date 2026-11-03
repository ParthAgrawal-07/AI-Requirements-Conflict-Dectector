"""Findings API (US-07, FR-13, FR-14): confidence, low-confidence marker, explanation, evidence and
the requirements involved with their source."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import DefaultRole
from app.models import (
    AuditAction,
    AuditLog,
    CandidatePair,
    Finding,
    FindingCategory,
    Project,
    Requirement,
    User,
    Workspace,
)
from tests.api.conftest import headers_for


@pytest.fixture
def conflict(
    db_session: Session, project: Project, make_requirement: Callable[..., Requirement]
) -> Finding:
    a = make_requirement(
        "Sessions end after 30 minutes.", source_req_id="REQ-014", section_heading="3.1 Sessions"
    )
    b = make_requirement(
        "Sessions end after 5 minutes.", source_req_id="REQ-031", section_heading="3.1 Sessions"
    )
    low, high = CandidatePair.ordered(a.id, b.id)
    pair = CandidatePair(requirement_a_id=low, requirement_b_id=high, similarity_score=0.9)
    db_session.add(pair)
    db_session.flush()
    finding = Finding(
        project_id=project.id,
        document_id=a.document_id,
        candidate_pair_id=pair.id,
        category=FindingCategory.CONFLICTING,
        confidence=0.864,
        rationale="Different session limits.",
        explanation="REQ-014 and REQ-031 set different session limits.",
        evidence_spans=[
            {
                "requirement_id": str(a.id),
                "label": "REQ-014",
                "quote": "30 minutes",
                "start": 19,
                "end": 29,
            }
        ],
        original_ai_output={"category": "Conflicting"},
        prompt_version="v2",
    )
    db_session.add(finding)
    db_session.commit()
    return finding


def test_a_finding_shows_confidence_explanation_evidence_and_both_requirements(
    client: TestClient, project: Project, user: User, conflict: Finding
) -> None:
    page = client.get(f"/api/v1/projects/{project.id}/findings", headers=headers_for(user)).json()

    (item,) = page["items"]
    assert item["source"] == "AI"
    assert (item["category"], item["confidence_percent"], item["low_confidence"]) == (
        "Conflicting",
        86,
        False,
    )
    assert item["explanation"] == "REQ-014 and REQ-031 set different session limits."
    assert item["evidence_spans"][0]["quote"] == "30 minutes"
    assert sorted(r["label"] for r in item["requirements"]) == ["REQ-014", "REQ-031"]
    assert {r["section_heading"] for r in item["requirements"]} == {"3.1 Sessions"}


def test_below_the_threshold_it_is_marked_low_confidence(
    client: TestClient, db_session: Session, project: Project, user: User, conflict: Finding
) -> None:
    project.confidence_threshold = 0.9
    db_session.commit()
    url = f"/api/v1/projects/{project.id}/findings"

    assert client.get(url, headers=headers_for(user)).json()["items"][0]["low_confidence"] is True
    assert (
        client.get(url, params={"low_confidence": False}, headers=headers_for(user)).json()["total"]
        == 0
    )


def test_filters_by_category_and_requirement(
    client: TestClient, project: Project, user: User, conflict: Finding, db_session: Session
) -> None:
    url = f"/api/v1/projects/{project.id}/findings"
    pair = db_session.get(CandidatePair, conflict.candidate_pair_id)
    assert pair is not None

    assert (
        client.get(url, params={"category": "Duplicate"}, headers=headers_for(user)).json()["total"]
        == 0
    )
    by_requirement = client.get(
        url, params={"requirement": str(pair.requirement_b_id)}, headers=headers_for(user)
    )
    assert by_requirement.json()["total"] == 1


def test_a_finding_about_a_posted_requirement_names_its_post(
    client: TestClient, db_session: Session, project: Project, user: User
) -> None:
    from app.models import Channel, Message, MessageKind, RequirementOrigin

    channel = Channel(project_id=project.id, name="general", is_default=True)
    db_session.add(channel)
    db_session.flush()
    post = Message(
        channel_id=channel.id,
        author_id=user.id,
        body="It shall be fast.",
        kind=MessageKind.REQUIREMENT_POST,
    )
    db_session.add(post)
    db_session.flush()
    posted = Requirement(
        project_id=project.id,
        body="It shall be fast.",
        origin=RequirementOrigin.POST,
        origin_message_id=post.id,
    )
    db_session.add(posted)
    db_session.flush()
    finding = Finding(
        project_id=project.id,
        requirement_id=posted.id,
        category=FindingCategory.AMBIGUOUS,
        confidence=0.7,
        rationale="fast",
        original_ai_output={"vague_terms": ["fast"]},
    )
    db_session.add(finding)
    db_session.commit()

    item = client.get(f"/api/v1/findings/{finding.id}", headers=headers_for(user)).json()
    (requirement,) = item["requirements"]
    assert requirement["origin_message_id"] == str(post.id) and requirement["document_id"] is None
    assert item["vague_terms"] == ["fast"]
    assert item["explanation"] == "fast"  # older findings fall back to the rationale


def test_opening_a_finding_about_a_protected_requirement_is_audited(
    client: TestClient, db_session: Session, user: User, conflict: Finding
) -> None:
    pair = db_session.get(CandidatePair, conflict.candidate_pair_id)
    assert pair is not None
    protected = db_session.get(Requirement, pair.requirement_a_id)
    assert protected is not None
    protected.is_protected = True
    db_session.commit()

    assert (
        client.get(f"/api/v1/findings/{conflict.id}", headers=headers_for(user)).status_code == 200
    )

    row = db_session.scalar(select(AuditLog).where(AuditLog.action == AuditAction.VIEWED_PROTECTED))
    assert row is not None and row.finding_id == conflict.id and row.requirement_id == protected.id


def test_another_workspaces_finding_is_a_404(
    client: TestClient,
    conflict: Finding,
    make_user: Callable[..., User],
    make_workspace: Callable[..., Workspace],
) -> None:
    stranger = make_user(role=DefaultRole.OWNER, workspace=make_workspace())
    assert (
        client.get(f"/api/v1/findings/{conflict.id}", headers=headers_for(stranger)).status_code
        == 404
    )
