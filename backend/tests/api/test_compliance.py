"""Protecting compliance-critical requirements (Parth — US-18, FR-21, FR-36, NFR-13, DR-05).

The guard itself is tested where it lives: findings in ``test_finding_review.py`` (US-10), merges
in ``tests/security/test_merge_rules.py`` (a protected requirement's change request without a
compliance approval answers ``409 compliance_missing``), approvals in ``test_lifecycle.py``.
"""

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.permissions import DefaultRole
from app.graph import service as graph_service
from app.models import (
    AuditLog,
    ChangeRequest,
    Finding,
    FindingCategory,
    GraphEvent,
    Project,
    Requirement,
    RequirementState,
    Review,
    User,
    Workspace,
)
from app.realtime import bus
from tests.api.conftest import headers_for


@pytest.fixture(autouse=True)
def quiet_bus(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(bus, "get_bus", lambda: bus.InProcessEventBus())
    yield


@pytest.fixture
def reviewer(make_user: Callable[..., User]) -> User:
    return make_user(role=DefaultRole.COMPLIANCE_REVIEWER)


def url(*parts: object) -> str:
    return "/api/v1/" + "/".join(str(p) for p in parts)


def actions(db: Session, action: str) -> list[AuditLog]:
    return list(db.scalars(select(AuditLog).where(AuditLog.action == action)))


def test_a_compliance_reviewer_protects_a_requirement_and_everyone_sees_it(
    client: TestClient, db_session: Session, project: Project, user: User, reviewer: User,
    make_requirement: Callable[..., Requirement],
) -> None:  # fmt: skip
    requirement = make_requirement("Records are kept for 7 years.", source_req_id="REQ-7")
    denied = client.put(url("requirements", requirement.id, "protection"),
                        json={"protected": True}, headers=headers_for(user))  # fmt: skip
    assert denied.status_code == 403  # an analyst does not hold req.protect

    body = client.put(url("requirements", requirement.id, "protection"),
                      json={"protected": True, "reason": "Retention law"},
                      headers=headers_for(reviewer)).json()  # fmt: skip

    assert body["is_protected"] is True and body["protection_reason"] == "Retention law"
    assert body["protected_by"] == str(reviewer.id)
    (audit,) = actions(db_session, "protection_changed")
    assert audit.requirement_id == requirement.id and audit.details["protected"] is True
    node = next(
        n for n in graph_service.snapshot(db_session, project.id).nodes if n.id == requirement.id
    )
    assert node.is_protected is True
    sentence = db_session.scalars(select(GraphEvent.sentence)).one()
    assert sentence == "Test User marked REQ-7 protected (compliance review required)."
    detail = client.get(url("requirements", requirement.id), headers=headers_for(user)).json()
    assert detail["protection_reason"] == "Retention law"


def test_removing_protection_needs_a_reason(
    client: TestClient, db_session: Session, reviewer: User,
    make_requirement: Callable[..., Requirement],
) -> None:  # fmt: skip
    requirement = make_requirement("x", is_protected=True)
    path = url("requirements", requirement.id, "protection")
    silent = client.put(path, json={"protected": False}, headers=headers_for(reviewer))
    assert (silent.status_code, silent.json()["error"]["code"]) == (400, "reason_required")
    done = client.put(path, json={"protected": False, "reason": "Law repealed"},
                      headers=headers_for(reviewer)).json()  # fmt: skip
    assert done["is_protected"] is False and done["protected_by"] is None


def test_requirements_are_protected_in_bulk_after_an_import(
    client: TestClient, db_session: Session, project: Project, reviewer: User,
    make_requirement: Callable[..., Requirement], make_project: Callable[..., Project],
) -> None:  # fmt: skip
    a = make_requirement("a", source_req_id="REQ-1")
    make_requirement("b", source_req_id="REQ-2")
    c = make_requirement("c", source_req_id="REQ-3")

    body = client.post(url("projects", project.id, "protection"),
                       json={"labels": ["REQ-1", "REQ-9"], "requirement_ids": [str(c.id)],
                             "reason": "HIPAA"},
                       headers=headers_for(reviewer)).json()  # fmt: skip

    assert {p["label"] for p in body["protected"]} == {"REQ-1", "REQ-3"}
    assert body["not_found"] == ["REQ-9"]
    db_session.refresh(a)
    assert a.is_protected and a.protection_reason == "HIPAA"
    assert len(actions(db_session, "protection_changed")) == 2
    other = make_project()
    foreign = Requirement(project_id=other.id, document_id=None, origin="post", body="x")
    db_session.add(foreign)
    db_session.commit()
    across = client.post(url("projects", project.id, "protection"),
                         json={"requirement_ids": [str(foreign.id)]}, headers=headers_for(reviewer))  # fmt: skip
    assert across.status_code == 404


def test_the_queue_lists_what_waits_for_a_compliance_reviewer(
    client: TestClient, db_session: Session, project: Project, user: User, reviewer: User,
    make_requirement: Callable[..., Requirement],
) -> None:  # fmt: skip
    protected = make_requirement("Keep logs 7 years.", source_req_id="REQ-7", is_protected=True,
                                 state=RequirementState.APPROVED)  # fmt: skip
    make_requirement("Unprotected.", source_req_id="REQ-8")
    finding = Finding(project_id=project.id, requirement_id=protected.id,
                      category=FindingCategory.AMBIGUOUS, confidence=0.7, rationale="r",
                      original_ai_output={})  # fmt: skip
    change = ChangeRequest(project_id=project.id, requirement_id=protected.id, number=1,
                           proposer_id=user.id, base_version=1, proposed_body="Keep logs 10 years.",
                           reason="New law")  # fmt: skip
    db_session.add_all([finding, change])
    db_session.commit()
    headers = headers_for(reviewer)

    queue = client.get(url("projects", project.id, "compliance", "queue"), headers=headers).json()

    assert {(i["kind"], i["status"]) for i in queue["pending"]} == {
        ("finding", "awaiting_decision"),
        ("change_request", "awaiting_approval"),
        ("signoff", "awaiting_signoff"),
    }
    assert [p["label"] for p in queue["protected"]] == ["REQ-7"]

    client.post(url("requirements", protected.id, "signoff"), json={"version": 1}, headers=headers)
    db_session.add(Review(change_request_id=change.id, reviewer_id=reviewer.id, decision="approve",
                          proposal_revision=1, reviewed_base_version=1))  # fmt: skip
    db_session.commit()
    after = client.get(url("projects", project.id, "compliance", "queue"), headers=headers).json()
    statuses = {(i["kind"], i["status"]) for i in after["pending"]}
    assert ("signoff", "awaiting_signoff") not in statuses
    assert ("change_request", "approved") in statuses
    approved = next(i for i in after["pending"] if i["kind"] == "change_request")
    assert approved["done_by_name"] == "Test User"
    (row,) = after["protected"]
    assert (row["signed_off_version"], row["signed_off_by"]) == (1, str(reviewer.id))
    assert client.get(url("projects", project.id, "compliance", "queue"),
                      headers=headers_for(user)).status_code == 403  # fmt: skip


def test_viewing_a_protected_requirement_is_audited_once_a_minute(
    client: TestClient, db_session: Session, user: User,
    make_requirement: Callable[..., Requirement],
) -> None:  # fmt: skip
    protected = make_requirement("x", is_protected=True)
    plain = make_requirement("y")
    headers = headers_for(user)
    for _ in range(2):
        client.get(url("requirements", protected.id), headers=headers)
    client.get(url("requirements", protected.id, "timeline"), headers=headers)
    client.get(url("requirements", plain.id), headers=headers)

    (view,) = actions(db_session, "viewed_protected")
    assert (view.requirement_id, view.actor_id, view.details) == (
        protected.id, user.id, {"view": "detail"}
    )  # fmt: skip


def test_the_trail_exports_as_json_and_csv_is_audited_and_immutable(
    client: TestClient, db_session: Session, project: Project, user: User, reviewer: User,
    make_user: Callable[..., User], make_requirement: Callable[..., Requirement],
    make_workspace: Callable[..., Workspace],
) -> None:  # fmt: skip
    requirement = make_requirement("x", source_req_id="REQ-7")
    make_requirement("y", source_req_id="REQ-8")
    client.put(url("requirements", requirement.id, "protection"), json={"protected": True},
               headers=headers_for(reviewer))  # fmt: skip
    client.get(url("requirements", requirement.id), headers=headers_for(user))
    owner = make_user(role=DefaultRole.OWNER)

    rows = client.get(url("projects", project.id, "compliance", "audit"),
                      headers=headers_for(owner)).json()  # fmt: skip
    # One test transaction stamps both rows with the same time: compare them as a set.
    assert sorted(r["action"] for r in rows) == ["protection_changed", "viewed_protected"]
    assert {r["requirement_label"] for r in rows} == {"REQ-7"}
    csv = client.get(url("projects", project.id, "compliance", "audit"), params={"format": "csv"},
                     headers=headers_for(owner))  # fmt: skip
    assert csv.headers["content-type"].startswith("text/csv")
    lines = csv.text.splitlines()
    assert lines[0] == "at,actor,actor_id,action,requirement,requirement_id,finding_id,details"
    assert len(lines) == 3 and "x" not in lines[1].split(",")[4]
    assert {e.details["format"] for e in actions(db_session, "audit_exported")} == {"json", "csv"}

    assert client.get(url("projects", project.id, "compliance", "audit"),
                      headers=headers_for(user)).status_code == 403  # fmt: skip
    outsider = headers_for(make_user(role=DefaultRole.OWNER, workspace=make_workspace()))
    assert client.get(url("projects", project.id, "compliance", "audit"),
                      headers=outsider).status_code == 404  # fmt: skip
    with pytest.raises(DBAPIError), db_session.begin_nested():
        db_session.execute(text("UPDATE audit_log SET action = 'x'"))
