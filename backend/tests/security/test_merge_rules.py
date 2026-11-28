"""Merge rules under attack (Affan — US-35, FR-65, FR-98, NFR-27).

Parth's ``tests/api/test_review_merge.py`` shows each rule working; these tests try to get round
them:

* **no self-approval** — for every role that may open a request, including roles that may merge;
  a merger's own change still needs someone else's approval;
* **merge permission** — exactly the roles holding ``rcr.merge`` merge, and holding it never
  bypasses an agreement rule (an accepted risk only covers an open High finding);
* **tenant isolation** — every change request route answers another workspace with 404;
* **needs update** — an approval given before the base moved never carries over a rebase;
* **compliance sign-off** — a protected requirement needs a compliance approval *of this revision*;
* **edits dismiss approvals (FR-98)** — any new revision, even a reason-only one, resets them;
* **races** — two competing requests merged at once: exactly one lands.
"""

import threading
import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.consequences import tasks as consequence_tasks
from app.core.errors import AppError
from app.core.permissions import DefaultRole
from app.intake import change_intake
from app.models import (
    ChangeRequest,
    Document,
    DocumentFormat,
    Project,
    ProjectStatus,
    Requirement,
    RequirementState,
    RequirementVersion,
    User,
    Workspace,
)
from app.services import change_requests, reviews
from app.services.access import Scope, build_access_context
from app.services.membership import add_member, get_default_role
from app.services.users import create_user
from tests.api.conftest import headers_for
from tests.conftest import _run_migrations

TEXT = "Sessions shall expire after 30 minutes of inactivity."
PROPOSED = "Sessions shall expire after 15 minutes of inactivity."
MERGERS = {
    DefaultRole.OWNER,
    DefaultRole.ADMIN,
    DefaultRole.PROJECT_MANAGER,
    DefaultRole.BUSINESS_ANALYST,
}
PROPOSERS = [
    r for r in DefaultRole if r not in (DefaultRole.VIEWER, DefaultRole.COMPLIANCE_REVIEWER)
]


class World:
    def __init__(
        self,
        db: Session,
        client: TestClient,
        project: Project,
        make_user: Callable[..., User],
        make: Callable[..., Requirement],
    ) -> None:
        self.db, self.client, self.project, self.make_user = db, client, project, make_user
        self.owner = make_user(role=DefaultRole.BUSINESS_ANALYST)  # owns REQ-014; may merge
        self.dev = make_user(role=DefaultRole.DEVELOPER)
        self.compliance = make_user(role=DefaultRole.COMPLIANCE_REVIEWER)
        self.req = make(
            TEXT, source_req_id="REQ-014", state=RequirementState.APPROVED, owner_id=self.owner.id
        )
        db.add(RequirementVersion(requirement_id=self.req.id, version_no=1, body_snapshot=TEXT))
        db.commit()

    def propose(self, user: User | None = None, **body: object) -> dict[str, Any]:
        payload: dict[str, object] = {"proposed_body": PROPOSED, "reason": "The bank asks for 15."}
        payload.update(body)
        response = self.client.post(
            f"/api/v1/requirements/{self.req.id}/change-requests",
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
    ) -> Response:
        return self.client.post(
            f"/api/v1/change-requests/{cr['id']}/reviews",
            json={"decision": decision, **extra},
            headers=headers_for(user),
        )

    def edit(self, cr: dict[str, Any], user: User | None = None, **body: object) -> Response:
        return self.client.patch(
            f"/api/v1/change-requests/{cr['id']}", json=body, headers=headers_for(user or self.dev)
        )

    def merge(self, cr: dict[str, Any], user: User | None = None, **body: object) -> Response:
        return self.client.post(
            f"/api/v1/change-requests/{cr['id']}/merge",
            json=body,
            headers=headers_for(user or self.owner),
        )

    def unmet(self, response: Response) -> set[str]:
        assert response.status_code == 409, response.text
        error = response.json()["error"]
        assert error["code"] == "merge_blocked"
        return {d["code"] for d in error["details"]}

    def approvals(self, cr: dict[str, Any]) -> list[tuple[str, bool]]:
        body = self.client.get(
            f"/api/v1/change-requests/{cr['id']}/reviews", headers=headers_for(self.dev)
        ).json()
        return [(r["decision"], r["dismissed"]) for r in body["reviews"]]

    def version(self) -> tuple[int, str]:
        self.db.expire_all()
        requirement = self.db.get(Requirement, self.req.id)
        assert requirement is not None
        return requirement.current_version, requirement.body

    def mergeable(self, user: User | None = None) -> dict[str, Any]:
        cr = self.propose(user)
        self.checks(cr)
        assert self.review(cr, self.owner).status_code == 201
        return cr


@pytest.fixture
def w(
    db_session: Session,
    client: TestClient,
    project: Project,
    make_user: Callable[..., User],
    make_requirement: Callable[..., Requirement],
) -> World:
    return World(db_session, client, project, make_user, make_requirement)


# ── no self-approval ────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("role", PROPOSERS, ids=lambda r: r.value)
def test_no_role_can_approve_its_own_change(w: World, role: DefaultRole) -> None:
    proposer = w.make_user(role=role)
    cr = w.propose(proposer)
    refused = w.review(cr, proposer)
    assert refused.status_code == 403 and refused.json()["error"]["code"] == "self_approval"
    assert w.approvals(cr) == []


def test_a_merger_cannot_merge_their_own_change_on_their_own_say(w: World) -> None:
    cr = w.propose(w.owner)  # the owner may merge, and owns the requirement
    w.checks(cr)
    assert w.review(cr, w.owner).status_code == 403
    assert w.review(cr, w.owner, "comment", rationale="Looks right to me").status_code == 201

    assert "approvals_missing" in w.unmet(w.merge(cr, w.owner))
    assert w.version() == (1, TEXT)

    other_merger = w.make_user(role=DefaultRole.PROJECT_MANAGER)
    assert w.review(cr, other_merger).status_code == 201
    assert w.merge(cr, w.owner).status_code == 200


def test_a_proposer_cannot_ask_themselves_to_review(w: World) -> None:
    cr = w.propose(w.owner)
    response = w.client.post(
        f"/api/v1/change-requests/{cr['id']}/reviewers",
        json={"reviewer_id": str(w.owner.id)},
        headers=headers_for(w.owner),
    )
    assert response.json()["error"]["code"] == "self_review"


# ── merge permission ────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("role", list(DefaultRole), ids=lambda r: r.value)
def test_only_roles_with_rcr_merge_can_merge(w: World, role: DefaultRole) -> None:
    cr = w.mergeable()
    response = w.merge(cr, w.make_user(role=role))
    if role in MERGERS:
        assert response.status_code == 200, response.text
        assert w.version() == (2, PROPOSED)
    else:
        assert response.status_code == 403
        assert w.version() == (1, TEXT)


@pytest.mark.parametrize("role", list(DefaultRole), ids=lambda r: r.value)
def test_only_roles_with_rcr_merge_can_close(w: World, role: DefaultRole) -> None:
    cr = w.propose()
    response = w.client.post(
        f"/api/v1/change-requests/{cr['id']}/close",
        json={"reason": "Not this quarter"},
        headers=headers_for(w.make_user(role=role)),
    )
    assert response.status_code == (200 if role in MERGERS else 403)


def test_merge_permission_never_bypasses_the_rules(w: World) -> None:
    cr = w.propose()
    workspace_owner = w.make_user(role=DefaultRole.OWNER)
    assert w.unmet(w.merge(cr, workspace_owner)) == {
        "checks_pending",
        "approvals_missing",
        "reviewer_missing",
    }
    # An accepted risk covers an open High finding, nothing else.
    w.req.is_protected = True
    w.db.commit()
    w.checks(cr)
    w.review(cr, w.owner)
    blocked = w.merge(cr, workspace_owner, accepted_risk_reason="The CISO said it is fine")
    assert w.unmet(blocked) == {"compliance_missing"}
    assert w.version() == (1, TEXT)


def test_a_viewer_reads_but_cannot_open_or_review(w: World) -> None:
    cr = w.propose()
    viewer = w.make_user(role=DefaultRole.VIEWER)
    read = w.client.get(f"/api/v1/change-requests/{cr['id']}", headers=headers_for(viewer))
    opened = w.client.post(
        f"/api/v1/requirements/{w.req.id}/change-requests",
        json={"proposed_body": PROPOSED, "reason": "Me too"},
        headers=headers_for(viewer),
    )
    assert (read.status_code, opened.status_code, w.review(cr, viewer).status_code) == (
        200,
        403,
        403,
    )


# ── tenant isolation (NFR-27) ───────────────────────────────────────────────────────────────
def test_another_workspace_gets_404_on_every_change_request_route(
    w: World, make_workspace: Callable[..., Workspace]
) -> None:
    cr = w.mergeable()
    outsider = headers_for(w.make_user(role=DefaultRole.OWNER, workspace=make_workspace()))
    base = f"/api/v1/change-requests/{cr['id']}"
    calls = [
        ("GET", base, None),
        ("PATCH", base, {"reason": "Mine now"}),
        ("GET", f"{base}/reviews", None),
        ("POST", f"{base}/reviews", {"decision": "approve"}),
        ("POST", f"{base}/reviewers", {"reviewer_id": str(w.owner.id)}),
        ("GET", f"{base}/agreement", None),
        ("GET", f"{base}/checks", None),
        ("POST", f"{base}/checks/rerun", None),
        ("POST", f"{base}/merge", {}),
        ("POST", f"{base}/close", {"reason": "Not yours"}),
        ("POST", f"{base}/withdraw", None),
        (
            "POST",
            f"/api/v1/requirements/{w.req.id}/change-requests",
            {"proposed_body": "x y z", "reason": "abc"},
        ),
        ("GET", f"/api/v1/requirements/{w.req.id}/impact", None),
        ("GET", f"/api/v1/projects/{w.project.id}/change-requests", None),
    ]
    answers = {
        (method, path): w.client.request(method, path, json=body, headers=outsider).status_code
        for method, path, body in calls
    }
    assert set(answers.values()) == {404}, answers
    assert w.version() == (1, TEXT)


# ── needs update ────────────────────────────────────────────────────────────────────────────
def test_an_approval_from_before_the_base_moved_never_carries_over(w: World) -> None:
    first = w.mergeable()
    second = w.mergeable(w.make_user(role=DefaultRole.QA_ENGINEER))
    assert w.merge(first).status_code == 200

    # Straight away: refused, and the text stays the first request's.
    assert "needs_update" in w.unmet(w.merge(second))
    assert w.version() == (2, PROPOSED)
    proposer = w.db.get(User, uuid.UUID(second["proposer"]["id"]))
    assert proposer is not None

    rebased = w.edit(
        second, proposer, rebase=True, proposed_body="Sessions shall expire after 10 minutes."
    )
    assert (rebased.json()["base_version"], rebased.json()["status"]) == (2, "open")
    assert w.approvals(second) == [("approve", True)]  # given on base v1: dismissed
    assert {"approvals_missing", "checks_pending"} <= w.unmet(w.merge(second))
    assert w.version() == (2, PROPOSED)


def test_a_rebase_by_anyone_but_the_proposer_is_refused(w: World) -> None:
    first, second = w.mergeable(), w.mergeable(w.make_user(role=DefaultRole.QA_ENGINEER))
    w.merge(first)
    assert w.edit(second, w.owner, rebase=True).status_code == 403


# ── compliance sign-off ─────────────────────────────────────────────────────────────────────
def test_a_protected_change_needs_a_compliance_approval_whatever_else_it_has(w: World) -> None:
    w.req.is_protected = True
    w.project.required_approvals = 3
    w.db.commit()
    cr = w.propose()
    w.checks(cr)
    for approver in (
        w.owner,
        w.make_user(role=DefaultRole.PROJECT_MANAGER),
        w.make_user(role=DefaultRole.ADMIN),
    ):
        assert w.review(cr, approver).status_code == 201
    assert w.unmet(w.merge(cr)) == {"compliance_missing"}

    assert w.review(cr, w.compliance).status_code == 201
    assert w.merge(cr).status_code == 200


def test_a_compliance_reviewer_signs_off_but_cannot_merge(w: World) -> None:
    w.req.is_protected = True
    w.db.commit()
    cr = w.mergeable()
    w.review(cr, w.compliance)
    assert w.merge(cr, w.compliance).status_code == 403
    assert w.merge(cr).status_code == 200


def test_a_compliance_approval_of_an_earlier_revision_is_dismissed(w: World) -> None:
    w.req.is_protected = True
    w.db.commit()
    cr = w.mergeable()
    w.review(cr, w.compliance)

    w.edit(cr, proposed_body="Sessions shall expire after 14 minutes of inactivity.")
    w.checks(cr)

    assert w.approvals(cr) == [("approve", True), ("approve", True)]
    assert {"compliance_missing", "approvals_missing"} <= w.unmet(w.merge(cr))


# ── edits dismiss approvals (FR-98) ─────────────────────────────────────────────────────────
def test_an_edit_after_approval_cannot_merge_on_the_old_approval(w: World) -> None:
    cr = w.mergeable()
    w.edit(cr, proposed_body="Sessions shall expire after 1 minute of inactivity.")

    assert {"approvals_missing", "checks_pending"} <= w.unmet(w.merge(cr))
    assert w.version() == (1, TEXT)


def test_a_reason_only_edit_also_dismisses_approvals(w: World) -> None:
    cr = w.mergeable()
    edited = w.edit(cr, reason="The bank asks for 15; the regulator agrees.")
    assert edited.json()["proposal_revision"] == 2
    assert w.approvals(cr) == [("approve", True)]


def test_an_edit_that_changes_nothing_keeps_the_approval(w: World) -> None:
    cr = w.mergeable()
    same = w.edit(cr, proposed_body=PROPOSED, reason="The bank asks for 15.")
    assert same.json()["proposal_revision"] == 1
    assert w.approvals(cr) == [("approve", False)]
    assert w.merge(cr).status_code == 200


def test_a_decided_request_cannot_be_edited_reviewed_or_merged_again(w: World) -> None:
    cr = w.mergeable()
    assert w.merge(cr).status_code == 200
    again = w.merge(cr)
    assert "not_open" in w.unmet(again)
    assert w.edit(cr, proposed_body="Sessions shall expire after 5 minutes.").status_code == 409
    assert w.review(cr, w.make_user(role=DefaultRole.PROJECT_MANAGER)).status_code == 409
    assert w.version() == (2, PROPOSED)


# ── races ───────────────────────────────────────────────────────────────────────────────────
def test_two_competing_merges_at_once_only_one_lands(scratch_engine: Engine) -> None:
    """Real concurrency: committed data, two connections; the requirement's row lock decides."""
    _run_migrations(scratch_engine)
    with Session(scratch_engine) as setup:
        workspace = Workspace(name="Race")
        setup.add(workspace)
        setup.commit()
        project = Project(workspace_id=workspace.id, name="Race", status=ProjectStatus.ACTIVE)
        setup.add(project)
        setup.commit()

        def member(name: str, role: DefaultRole) -> User:
            user = create_user(
                setup, email=f"{name}@example.com", password="correct-horse-battery-staple",
                full_name=name,
            )  # fmt: skip
            add_member(
                setup,
                workspace_id=workspace.id,
                user_id=user.id,
                role_id=get_default_role(setup, role).id,
            )
            return user

        owner = member("owner", DefaultRole.BUSINESS_ANALYST)
        mergers = [member(f"merger{i}", DefaultRole.PROJECT_MANAGER) for i in range(2)]
        proposers = [member(f"dev{i}", DefaultRole.DEVELOPER) for i in range(2)]
        document = Document(
            workspace_id=workspace.id,
            project_id=project.id,
            uploaded_by=owner.id,
            filename="srs.docx",
            format=DocumentFormat.DOCX,
            size_bytes=1024,
            sha256="0" * 64,
            storage_path="/data/uploads/srs.docx",
        )
        setup.add(document)
        setup.commit()
        requirement = Requirement(
            document_id=document.id,
            project_id=project.id,
            body=TEXT,
            source_req_id="REQ-014",
            state=RequirementState.APPROVED,
            owner_id=owner.id,
        )
        setup.add(requirement)
        setup.commit()
        setup.add(
            RequirementVersion(requirement_id=requirement.id, version_no=1, body_snapshot=TEXT)
        )
        setup.commit()

        scope = Scope(workspace.id, project.id)
        requests: list[uuid.UUID] = []
        for proposer, minutes in zip(proposers, (15, 10), strict=True):
            cr = change_intake.open_change_request(
                setup,
                build_access_context(setup, proposer, scope),
                requirement,
                kind="modify",
                reason="Shorter",
                proposed_body=f"Sessions shall expire after {minutes} minutes of inactivity.",
            )
            consequence_tasks.build_report(setup, cr.id, None, None)
            setup.refresh(cr)
            reviews.review(setup, build_access_context(setup, owner, scope), cr, decision="approve")
            change_requests.after_review(setup, cr, owner, "approve")
            requests.append(cr.id)
        requirement_id, merger_ids = requirement.id, [m.id for m in mergers]

    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def race(merger_id: uuid.UUID, change_request_id: uuid.UUID) -> None:
        with Session(scratch_engine) as db:
            merger = db.get(User, merger_id)
            change_request = db.get(ChangeRequest, change_request_id)
            assert merger is not None and change_request is not None
            ctx = build_access_context(db, merger, scope)
            barrier.wait()
            try:
                change_requests.merge(db, ctx, change_request)
                outcomes.append("merged")
            except AppError as error:
                db.rollback()
                outcomes.append(error.code)

    threads = [
        threading.Thread(target=race, args=(m, cr))
        for m, cr in zip(merger_ids, requests, strict=True)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert sorted(outcomes) == ["merge_blocked", "merged"]
    with Session(scratch_engine) as check:
        requirement = check.get(Requirement, requirement_id)
        assert requirement is not None and requirement.current_version == 2
        statuses = sorted(check.get(ChangeRequest, i).status for i in requests)  # type: ignore[union-attr]
        assert statuses == ["merged", "needs_update"]
