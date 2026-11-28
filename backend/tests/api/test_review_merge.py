"""Review and merge of change requests, and version history (Parth — US-35, US-12, FR-98)."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.consequences import tasks as consequence_tasks
from app.core.permissions import DefaultRole
from app.models import (
    CandidatePair,
    ChangeRequest,
    ConsequenceReport,
    Embedding,
    Finding,
    FindingCategory,
    Issue,
    Project,
    Requirement,
    RequirementState,
    RequirementTransition,
    RequirementVersion,
    Review,
    Severity,
    User,
)
from app.models.embedding import EMBEDDING_DIM
from tests.api.conftest import headers_for

TEXT = "Sessions shall expire after 30 minutes of inactivity."
PROPOSED = "Sessions shall expire after 15 minutes of inactivity."


class World:
    def __init__(
        self,
        db: Session,
        client: TestClient,
        project: Project,
        make_user: Callable[..., User],
        make: Callable[..., Requirement],
    ) -> None:
        self.db, self.client, self.project = db, client, project
        self.owner = make_user(role=DefaultRole.BUSINESS_ANALYST)  # owns REQ-014; may merge
        self.dev = make_user(role=DefaultRole.DEVELOPER)  # proposes; may not merge
        self.other = make_user(role=DefaultRole.DEVELOPER)
        self.compliance = make_user(role=DefaultRole.COMPLIANCE_REVIEWER)
        self.req = make(
            TEXT, source_req_id="REQ-014", state=RequirementState.APPROVED, owner_id=self.owner.id
        )
        db.add(RequirementVersion(requirement_id=self.req.id, version_no=1, body_snapshot=TEXT))
        db.commit()

    def propose(
        self, user: User | None = None, *, requirement: Requirement | None = None, **body: object
    ) -> dict[str, Any]:
        target = requirement or self.req
        payload: dict[str, object] = {"proposed_body": PROPOSED, "reason": "The bank asks for 15."}
        payload.update(body)
        response = self.client.post(
            f"/api/v1/requirements/{target.id}/change-requests",
            json=payload,
            headers=headers_for(user or self.dev),
        )
        assert response.status_code == 201, response.text
        result: dict[str, Any] = response.json()
        return result

    def checks(self, cr: dict[str, Any]) -> None:
        consequence_tasks.build_report(self.db, cr["id"], None, None)

    def review(
        self, cr: dict[str, Any], user: User, decision: str = "approve", **extra: object
    ) -> Any:
        return self.client.post(
            f"/api/v1/change-requests/{cr['id']}/reviews",
            json={"decision": decision, **extra},
            headers=headers_for(user),
        )

    def merge(self, cr: dict[str, Any], user: User | None = None, **body: object) -> Any:
        return self.client.post(
            f"/api/v1/change-requests/{cr['id']}/merge",
            json=body,
            headers=headers_for(user or self.owner),
        )

    def agreement(self, cr: dict[str, Any]) -> set[str]:
        body = self.client.get(
            f"/api/v1/change-requests/{cr['id']}/agreement", headers=headers_for(self.dev)
        ).json()
        return {u["code"] for u in body["unmet"]}

    def status(self, cr: dict[str, Any]) -> str:
        row = self.db.get(ChangeRequest, cr["id"])
        assert row is not None
        self.db.refresh(row)
        return row.status


@pytest.fixture
def w(
    db_session: Session,
    client: TestClient,
    project: Project,
    make_user: Callable[..., User],
    make_requirement: Callable[..., Requirement],
) -> World:
    return World(db_session, client, project, make_user, make_requirement)


# ── reviewers (ReviewPolicy) ────────────────────────────────────────────────────────────────
def test_opening_asks_the_owner_never_the_proposer(w: World) -> None:
    cr = w.propose()
    body = w.client.get(
        f"/api/v1/change-requests/{cr['id']}/reviews", headers=headers_for(w.dev)
    ).json()
    assert [(r["reviewer"]["id"], r["required"], r["reason"]) for r in body["requests"]] == [
        (str(w.owner.id), True, "owner")
    ]
    own = w.propose(w.owner, proposed_body="Sessions shall expire after 10 minutes.")
    asked = w.client.get(
        f"/api/v1/change-requests/{own['id']}/reviews", headers=headers_for(w.dev)
    ).json()
    assert str(w.owner.id) not in {r["reviewer"]["id"] for r in asked["requests"]}
    assert {r["reason"] for r in asked["requests"]} == {"merge_quota"}  # someone else may merge


def test_a_conflicting_owner_and_compliance_are_asked_for_a_protected_requirement(
    w: World, make_requirement: Callable[..., Requirement]
) -> None:
    w.req.is_protected = True
    partner = make_requirement(
        "Sessions end after 5 minutes.", source_req_id="REQ-031", owner_id=w.other.id
    )
    first, second = CandidatePair.ordered(w.req.id, partner.id)
    pair = CandidatePair(requirement_a_id=first, requirement_b_id=second, similarity_score=0.9)
    w.db.add(pair)
    w.db.flush()
    w.db.add(
        Finding(
            project_id=w.project.id,
            candidate_pair_id=pair.id,
            category=FindingCategory.CONFLICTING,
            confidence=0.9,
            rationale="r",
            original_ai_output={},
        )
    )
    w.db.commit()

    cr = w.propose()

    asked = w.client.get(
        f"/api/v1/change-requests/{cr['id']}/reviews", headers=headers_for(w.dev)
    ).json()
    reasons = {r["reviewer"]["id"]: r["reason"] for r in asked["requests"] if r["required"]}
    assert reasons[str(w.owner.id)] == "owner"
    assert reasons[str(w.other.id)] == "direct_conflict"
    assert reasons[str(w.compliance.id)] == "compliance"


# ── reviews ─────────────────────────────────────────────────────────────────────────────────
def test_no_self_approval_in_the_api_or_the_database(w: World) -> None:
    cr = w.propose()
    refused = w.review(cr, w.dev)
    assert refused.status_code == 403 and refused.json()["error"]["code"] == "self_approval"
    with pytest.raises(DBAPIError, match="cannot approve"):
        w.db.execute(
            text(
                "INSERT INTO reviews (change_request_id, reviewer_id, decision, proposal_revision, "
                "reviewed_base_version) VALUES (:cr, :user, 'approve', 1, 1)"
            ),
            {"cr": cr["id"], "user": str(w.dev.id)},
        )
    w.db.rollback()


def test_the_owners_approval_makes_it_approved(w: World) -> None:
    cr = w.propose()
    response = w.review(cr, w.owner)
    assert response.status_code == 201 and response.json()["status"] == "approved"


def test_request_changes_needs_a_reason_and_blocks(w: World) -> None:
    cr = w.propose()
    assert w.review(cr, w.owner, "request_changes").status_code == 400
    w.review(cr, w.other, "approve")
    blocked = w.review(
        cr,
        w.owner,
        "request_changes",
        rationale="15 is too strict for kiosks",
        comments=[
            {"field": "statement", "start_offset": 29, "end_offset": 39, "body": "this number"}
        ],
    )
    assert blocked.json()["status"] == "open"
    assert "changes_requested" in w.agreement(cr)
    reviews = w.client.get(
        f"/api/v1/change-requests/{cr['id']}/reviews", headers=headers_for(w.dev)
    ).json()["reviews"]
    # Not reviews[-1]: inside the test's one transaction now() is the same for both reviews, so
    # their order falls to the random id.
    blocking = next(r for r in reviews if r["decision"] == "request_changes")
    assert blocking["comments"] == [
        {"field": "statement", "start_offset": 29, "end_offset": 39, "body": "this number"}
    ]


def test_editing_the_proposal_dismisses_earlier_approvals(w: World) -> None:
    cr = w.propose()
    w.review(cr, w.owner)
    edited = w.client.patch(
        f"/api/v1/change-requests/{cr['id']}",
        json={"proposed_body": "Sessions shall expire after 20 minutes of inactivity."},
        headers=headers_for(w.dev),
    )
    by_other = w.client.patch(
        f"/api/v1/change-requests/{cr['id']}",
        json={"reason": "Mine now"},
        headers=headers_for(w.other),
    )

    assert edited.json()["proposal_revision"] == 2 and edited.json()["status"] == "open"
    assert by_other.status_code == 403
    reviews = w.client.get(
        f"/api/v1/change-requests/{cr['id']}/reviews", headers=headers_for(w.dev)
    ).json()
    assert [r["dismissed"] for r in reviews["reviews"]] == [True]
    assert not reviews["requests"][0]["approved"]
    assert {"approvals_missing", "reviewer_missing", "checks_pending"} <= w.agreement(cr)


# ── merge ───────────────────────────────────────────────────────────────────────────────────
def test_merge_is_refused_with_every_unmet_condition(w: World) -> None:
    cr = w.propose()
    response = w.merge(cr)
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "merge_blocked"
    assert {d["code"] for d in error["details"]} == {
        "checks_pending",
        "approvals_missing",
        "reviewer_missing",
    }
    assert w.db.get(Requirement, w.req.id).current_version == 1  # type: ignore[union-attr]


def test_a_member_who_may_not_merge_is_refused(w: World) -> None:
    cr = w.propose()
    assert w.merge(cr, w.other).status_code == 403


def test_merge_writes_the_new_version_and_its_consequences(
    w: World, followups: list[tuple[str, list[str]]], make_requirement: Callable[..., Requirement]
) -> None:
    issue = Issue(project_id=w.project.id, number=1, title="Which timeout?")
    w.db.add(issue)
    vague = Finding(
        project_id=w.project.id,
        requirement_id=w.req.id,
        category=FindingCategory.AMBIGUOUS,
        confidence=0.7,
        rationale="r",
        original_ai_output={},
    )
    w.db.add(vague)
    w.db.add(Embedding(requirement_id=w.req.id, vector=[0.0] * EMBEDDING_DIM, model_version="t"))
    w.db.commit()
    cr = w.propose(reason="Resolves ISS-1")
    competing = w.propose(
        w.other, proposed_body="Sessions shall expire after 10 minutes of inactivity."
    )
    w.checks(competing)
    w.checks(cr)
    w.review(cr, w.owner)

    response = w.merge(cr)

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["status"], body["merged_version"]) == ("merged", 2)
    w.db.expire_all()
    requirement = w.db.get(Requirement, w.req.id)
    assert requirement is not None and (requirement.body, requirement.current_version) == (
        PROPOSED,
        2,
    )
    assert w.db.get(Project, w.project.id).baseline_revision == 1  # type: ignore[union-attr]
    assert w.db.get(Finding, vague.id).is_stale  # type: ignore[union-attr]
    assert w.db.scalar(select(Embedding).where(Embedding.requirement_id == w.req.id)) is None
    assert [name for name, _ in followups].count("analysis.run_requirement") == 1  # re-analysis
    assert w.db.get(Issue, issue.id).close_reason == "resolved_by_merge"  # type: ignore[union-attr]
    assert w.status(competing) == "needs_update"
    stale = w.db.scalar(
        select(ConsequenceReport).where(ConsequenceReport.change_request_id == competing["id"])
    )
    assert stale is not None and stale.is_stale

    versions = w.client.get(
        f"/api/v1/requirements/{w.req.id}/versions", headers=headers_for(w.dev)
    ).json()
    assert [(v["version_no"], v["change_request"]) for v in versions] == [
        (2, {"id": cr["id"], "key": "RCR-1"}),
        (1, None),
    ]
    assert versions[0]["body"] == PROPOSED and versions[0]["changed_by"]["id"] == str(w.dev.id)


def test_a_competing_request_must_rebase_before_it_can_merge(w: World) -> None:
    first = w.propose()
    second = w.propose(
        w.other, proposed_body="Sessions shall expire after 10 minutes of inactivity."
    )
    for cr in (first, second):
        w.checks(cr)
        w.review(cr, w.owner)
    assert w.merge(first).status_code == 200

    assert "needs_update" in w.agreement(second)
    rebased = w.client.patch(
        f"/api/v1/change-requests/{second['id']}",
        json={"rebase": True},
        headers=headers_for(w.other),
    )
    assert (rebased.json()["base_version"], rebased.json()["status"]) == (2, "open")
    assert rebased.json()["base_body"] == PROPOSED


def test_a_protected_requirement_needs_a_compliance_approval(w: World) -> None:
    w.req.is_protected = True
    w.db.commit()
    cr = w.propose()
    w.checks(cr)
    w.review(cr, w.owner)
    assert "compliance_missing" in w.agreement(cr)
    w.review(cr, w.compliance)
    assert w.agreement(cr) == set()


def test_an_open_high_finding_needs_an_accepted_risk(
    w: World, make_requirement: Callable[..., Requirement]
) -> None:
    w.db.add(
        Finding(
            project_id=w.project.id,
            requirement_id=w.req.id,
            category=FindingCategory.INCOMPLETE,
            severity=Severity.HIGH,
            confidence=0.9,
            rationale="r",
            original_ai_output={},
        )
    )
    w.db.commit()
    cr = w.propose()
    w.checks(cr)
    w.review(cr, w.owner)
    assert w.agreement(cr) == {"high_finding_open"}
    assert w.merge(cr, accepted_risk_reason="Agreed with the bank on 2026-12-01").status_code == 200


def test_a_merged_deprecation_deprecates(w: World) -> None:
    cr = w.propose(kind="deprecate", proposed_body=None, reason="Replaced by REQ-090")
    w.checks(cr)
    w.review(cr, w.owner)
    assert w.merge(cr).status_code == 200
    w.db.expire_all()
    requirement = w.db.get(Requirement, w.req.id)
    assert requirement is not None and requirement.state is RequirementState.DEPRECATED
    transition = w.db.scalar(
        select(RequirementTransition).where(RequirementTransition.requirement_id == w.req.id)
    )
    assert transition is not None and transition.to_state is RequirementState.DEPRECATED


def test_withdraw_and_close(w: World) -> None:
    mine, theirs = w.propose(), w.propose(w.other, proposed_body="Sessions end after 12 minutes.")
    not_mine = w.client.post(
        f"/api/v1/change-requests/{mine['id']}/withdraw", headers=headers_for(w.other)
    )
    withdrawn = w.client.post(
        f"/api/v1/change-requests/{mine['id']}/withdraw", headers=headers_for(w.dev)
    )
    closed = w.client.post(
        f"/api/v1/change-requests/{theirs['id']}/close",
        json={"reason": "Kiosks need 30"},
        headers=headers_for(w.owner),
    )
    again = w.review(theirs, w.owner)

    assert not_mine.status_code == 403
    assert withdrawn.json()["status"] == "withdrawn"
    assert (closed.json()["status"], closed.json()["close_reason"]) == ("closed", "Kiosks need 30")
    assert again.status_code == 409


def test_another_reviewer_can_be_asked(w: World) -> None:
    cr = w.propose()
    added = w.client.post(
        f"/api/v1/change-requests/{cr['id']}/reviewers",
        json={"reviewer_id": str(w.other.id)},
        headers=headers_for(w.dev),
    )
    self_ = w.client.post(
        f"/api/v1/change-requests/{cr['id']}/reviewers",
        json={"reviewer_id": str(w.dev.id)},
        headers=headers_for(w.dev),
    )
    assert (added.status_code, added.json()["reason"], added.json()["required"]) == (
        201,
        "requested",
        False,
    )
    assert self_.json()["error"]["code"] == "self_review"
    assert w.db.scalar(select(Review)) is None


def test_version_history_is_for_members_only(w: World, make_user: Callable[..., User]) -> None:
    outsider = make_user(role=None)
    url = f"/api/v1/requirements/{w.req.id}/versions"
    assert w.client.get(url, headers=headers_for(w.dev)).status_code == 200
    assert w.client.get(url, headers=headers_for(outsider)).status_code == 404
