"""Human review of findings (Parth — US-10, FR-18–FR-21, CR-19): every action, the original AI
output kept, the protected-requirement guard, the audit trail and the map update."""

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
    Finding,
    FindingCategory,
    FindingStatus,
    Project,
    Requirement,
    Role,
    RolePermission,
    User,
    Workspace,
)
from app.realtime import bus
from app.realtime.events import GRAPH_DELTA
from app.services.membership import add_member
from tests.api.conftest import headers_for


@pytest.fixture
def events(monkeypatch: pytest.MonkeyPatch) -> Iterator[bus.InProcessEventBus]:
    test_bus = bus.InProcessEventBus()
    monkeypatch.setattr(bus, "get_bus", lambda: test_bus)
    yield test_bus


@pytest.fixture
def analyst(make_user: Callable[..., User]) -> User:
    return make_user(role=DefaultRole.BUSINESS_ANALYST)


@pytest.fixture
def reviewer(make_user: Callable[..., User]) -> User:
    return make_user(role=DefaultRole.COMPLIANCE_REVIEWER)


@pytest.fixture
def pair(make_requirement: Callable[..., Requirement]) -> tuple[Requirement, Requirement]:
    return (
        make_requirement("Sessions end after 30 minutes.", source_req_id="REQ-014"),
        make_requirement("Sessions end after 5 minutes.", source_req_id="REQ-031"),
    )


def make_finding(
    db: Session,
    a: Requirement,
    b: Requirement | None = None,
    category: FindingCategory = FindingCategory.CONFLICTING,
    **extra: Any,
) -> Finding:
    pair_id = None
    if b is not None:
        first, second = CandidatePair.ordered(a.id, b.id)
        candidate = db.scalar(
            select(CandidatePair).where(
                CandidatePair.requirement_a_id == first, CandidatePair.requirement_b_id == second
            )
        )
        if candidate is None:
            candidate = CandidatePair(
                requirement_a_id=first, requirement_b_id=second, similarity_score=0.9
            )
            db.add(candidate)
            db.flush()
        pair_id = candidate.id
    finding = Finding(
        project_id=a.project_id,
        document_id=a.document_id,
        candidate_pair_id=pair_id,
        requirement_id=None if b is not None else a.id,
        category=category,
        confidence=0.86,
        rationale="Different timeouts.",
        original_ai_output={"category": category.value, "confidence": 0.86},
        **extra,
    )
    db.add(finding)
    db.commit()
    return finding


def review(client: TestClient, finding: Finding, who: User, **body: Any) -> Any:
    return client.post(f"/api/v1/findings/{finding.id}/review", json=body, headers=headers_for(who))


def test_an_analyst_confirms_a_finding_and_the_map_hears_it(
    client: TestClient,
    db_session: Session,
    pair: tuple[Requirement, Requirement],
    analyst: User,
    events: bus.InProcessEventBus,
) -> None:
    finding = make_finding(db_session, *pair)

    response = review(client, finding, analyst, action="confirm")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "confirmed" and body["reviewed_by"] == str(analyst.id)
    (delta,) = [e for e in events.published if e.type == GRAPH_DELTA]
    assert delta.data["changed"]["edges"][0]["status"] == "confirmed"
    assert delta.data["sentences"] == [
        "Test User confirmed the conflict between REQ-014 and REQ-031."
    ]
    audit = db_session.scalar(select(AuditLog).where(AuditLog.finding_id == finding.id))
    assert audit is not None and audit.action == AuditAction.CONFIRMED


def test_a_dismissal_needs_a_reason_and_removes_the_edge(
    client: TestClient,
    db_session: Session,
    pair: tuple[Requirement, Requirement],
    analyst: User,
    events: bus.InProcessEventBus,
) -> None:
    finding = make_finding(db_session, *pair)

    missing = review(client, finding, analyst, action="dismiss")
    dismissed = review(client, finding, analyst, action="dismiss", reason="Different user types")

    assert missing.status_code == 400 and missing.json()["error"]["code"] == "reason_required"
    assert dismissed.status_code == 200 and dismissed.json()["status"] == "dismissed"
    (delta,) = [e for e in events.published if e.type == GRAPH_DELTA]
    assert delta.data["removed"]["edge_ids"] == [str(finding.id)]


def test_reclassifying_keeps_what_the_ai_said(
    client: TestClient,
    db_session: Session,
    pair: tuple[Requirement, Requirement],
    analyst: User,
) -> None:
    finding = make_finding(db_session, *pair)

    response = review(client, finding, analyst, action="reclassify", category="Duplicate")

    assert response.status_code == 200
    body = response.json()
    assert (body["category"], body["status"], body["ai_category"]) == (
        "Duplicate",
        "reclassified",
        "Conflicting",
    )
    db_session.refresh(finding)
    assert finding.original_ai_output["category"] == "Conflicting"  # FR-20
    (history,) = client.get(
        f"/api/v1/findings/{finding.id}/reviews", headers=headers_for(analyst)
    ).json()
    assert (history["from_category"], history["to_category"]) == ("Conflicting", "Duplicate")


def test_a_pair_finding_cannot_become_a_single_requirement_category(
    client: TestClient,
    db_session: Session,
    pair: tuple[Requirement, Requirement],
    analyst: User,
) -> None:
    finding = make_finding(db_session, *pair)

    response = review(client, finding, analyst, action="reclassify", category="Ambiguous")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "category_kind_mismatch"


def test_merging_folds_a_finding_into_another_of_the_same_category(
    client: TestClient,
    db_session: Session,
    pair: tuple[Requirement, Requirement],
    make_requirement: Callable[..., Requirement],
    analyst: User,
) -> None:
    keep = make_finding(db_session, *pair, category=FindingCategory.DUPLICATE)
    third = make_requirement("Sessions end after 5 min.", source_req_id="REQ-032")
    fold = make_finding(db_session, pair[1], third, category=FindingCategory.DUPLICATE)
    other_kind = make_finding(db_session, pair[0], third)

    merged = review(client, fold, analyst, action="merge", merge_into=str(keep.id))
    mismatch = review(client, other_kind, analyst, action="merge", merge_into=str(keep.id))
    itself = review(client, keep, analyst, action="merge", merge_into=str(keep.id))

    assert merged.status_code == 200
    assert merged.json()["status"] == "merged" and merged.json()["merged_into_id"] == str(keep.id)
    assert mismatch.json()["error"]["code"] == "merge_category_mismatch"
    assert itself.json()["error"]["code"] == "merge_into_self"


def test_two_findings_cannot_be_merged_into_each_other(
    client: TestClient,
    db_session: Session,
    pair: tuple[Requirement, Requirement],
    make_requirement: Callable[..., Requirement],
    analyst: User,
) -> None:
    first = make_finding(db_session, *pair, category=FindingCategory.DUPLICATE)
    third = make_requirement("Sessions end after 5 min.", source_req_id="REQ-032")
    second = make_finding(db_session, pair[1], third, category=FindingCategory.DUPLICATE)

    into_second = review(client, first, analyst, action="merge", merge_into=str(second.id))
    back = review(client, second, analyst, action="merge", merge_into=str(first.id))

    assert into_second.status_code == 200
    assert back.status_code == 409 and back.json()["error"]["code"] == "merge_target_closed"


def test_a_finding_cannot_be_merged_into_another_projects_finding(
    client: TestClient,
    db_session: Session,
    pair: tuple[Requirement, Requirement],
    make_project: Callable[..., Project],
    analyst: User,
) -> None:
    finding = make_finding(db_session, *pair, category=FindingCategory.DUPLICATE)
    other_project = make_project()
    elsewhere = Requirement(project_id=other_project.id, document_id=pair[0].document_id, body="x")
    db_session.add(elsewhere)
    db_session.commit()
    foreign = make_finding(db_session, elsewhere, category=FindingCategory.AMBIGUOUS)

    response = review(client, finding, analyst, action="merge", merge_into=str(foreign.id))

    assert response.status_code == 404


def test_reopen_brings_a_dismissed_finding_back(
    client: TestClient,
    db_session: Session,
    pair: tuple[Requirement, Requirement],
    analyst: User,
) -> None:
    finding = make_finding(db_session, *pair, status=FindingStatus.DISMISSED)

    response = review(client, finding, analyst, action="reopen")

    assert response.status_code == 200 and response.json()["status"] == "flagged"


def test_illegal_reviews_and_stale_findings_are_a_409(
    client: TestClient,
    db_session: Session,
    pair: tuple[Requirement, Requirement],
    analyst: User,
) -> None:
    open_one = make_finding(db_session, *pair)
    stale = make_finding(db_session, pair[0], category=FindingCategory.AMBIGUOUS, is_stale=True)

    assert review(client, open_one, analyst, action="reopen").json()["error"]["code"] == (
        "illegal_review"
    )
    assert review(client, stale, analyst, action="confirm").json()["error"]["code"] == (
        "finding_stale"
    )


def test_escalating_is_audited_and_changes_nothing_else(
    client: TestClient,
    db_session: Session,
    pair: tuple[Requirement, Requirement],
    analyst: User,
) -> None:
    finding = make_finding(db_session, *pair)

    response = review(client, finding, analyst, action="escalate", reason="Legal must look")

    assert response.status_code == 200 and response.json()["status"] == "flagged"
    audit = db_session.scalar(select(AuditLog).where(AuditLog.finding_id == finding.id))
    assert audit is not None and audit.action == AuditAction.ESCALATED


# ── the protected-requirement guard (CR-19, FR-21) ──────────────────────────────────────────
def test_only_a_compliance_reviewer_acts_on_a_protected_requirements_finding(
    client: TestClient,
    db_session: Session,
    pair: tuple[Requirement, Requirement],
    analyst: User,
    reviewer: User,
    make_user: Callable[..., User],
) -> None:
    pair[0].is_protected = True
    finding = make_finding(db_session, *pair)
    owner = make_user(role=DefaultRole.OWNER)

    by_analyst = review(client, finding, analyst, action="dismiss", reason="Not a real conflict")
    by_owner = review(client, finding, owner, action="dismiss", reason="Not a real conflict")
    by_reviewer = review(client, finding, reviewer, action="confirm")

    assert by_analyst.status_code == 403 and by_owner.status_code == 403
    assert by_reviewer.status_code == 200
    audit = db_session.scalar(select(AuditLog).where(AuditLog.action == AuditAction.CONFIRMED))
    assert audit is not None and audit.details and audit.details["protected"] is True


def test_a_compliance_reviewer_cannot_act_on_an_ordinary_finding(
    client: TestClient,
    db_session: Session,
    pair: tuple[Requirement, Requirement],
    reviewer: User,
) -> None:
    finding = make_finding(db_session, *pair)

    assert review(client, finding, reviewer, action="confirm").status_code == 403


@pytest.mark.parametrize("role", [DefaultRole.DEVELOPER, DefaultRole.VIEWER])
def test_members_without_finding_review_are_refused(
    client: TestClient,
    db_session: Session,
    pair: tuple[Requirement, Requirement],
    make_user: Callable[..., User],
    role: DefaultRole,
) -> None:
    finding = make_finding(db_session, *pair)

    assert review(client, finding, make_user(role=role), action="confirm").status_code == 403


def test_review_history_needs_view(
    client: TestClient,
    db_session: Session,
    workspace: Workspace,
    pair: tuple[Requirement, Requirement],
    make_user: Callable[..., User],
) -> None:
    finding = make_finding(db_session, *pair)
    role = Role(
        workspace_id=workspace.id,
        name="No view",
        permissions=[RolePermission(permission="message.post")],
    )
    db_session.add(role)
    db_session.commit()
    member = make_user(role=None)
    add_member(db_session, workspace_id=workspace.id, user_id=member.id, role_id=role.id)

    history = client.get(f"/api/v1/findings/{finding.id}/reviews", headers=headers_for(member))

    assert history.status_code == 403


def test_another_workspaces_finding_is_a_404(
    client: TestClient,
    db_session: Session,
    pair: tuple[Requirement, Requirement],
    make_user: Callable[..., User],
    make_workspace: Callable[..., Workspace],
) -> None:
    finding = make_finding(db_session, *pair)
    stranger = make_user(role=DefaultRole.OWNER, workspace=make_workspace())

    assert review(client, finding, stranger, action="confirm").status_code == 404
    assert (
        client.get(
            f"/api/v1/findings/{finding.id}/reviews", headers=headers_for(stranger)
        ).status_code
        == 404
    )
