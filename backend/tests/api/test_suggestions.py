"""AI suggestions with human feedback (Madhav — US-45, FR-68, FR-94, NFR-36, DR-04)."""

import json
import threading
import time
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.classification.budget import CountingBudget
from app.classification.llm_client import FakeTransport, LLMClient
from app.core.permissions import DefaultRole
from app.models import (
    AnalysisRun,
    AnalysisRunStatus,
    AnalysisScope,
    CandidatePair,
    Document,
    DocumentFormat,
    Finding,
    FindingCategory,
    Project,
    Requirement,
    RequirementState,
    User,
    Workspace,
)
from app.models.suggestion import READY, SUPERSEDED, WAITING_BUDGET, Suggestion, SuggestionFeedback
from app.realtime import bus
from app.services.users import create_user
from app.suggestions import service, tasks
from tests.api.conftest import headers_for
from tests.conftest import _run_migrations

TIMEOUTS = [
    "Sessions shall time out after 30 minutes, and after 5 minutes on payment screens.",
    "Sessions shall time out after 5 minutes.",
    "Payment screens shall time out after 30 minutes.",
]


def options_reply(targets: tuple[str, ...] = ("REQ-012", "REQ-012", "REQ-031")) -> str:
    return json.dumps(
        {"options": [
            {"text": text_, "target": target, "trade_off": "Who gives way.", "confidence": 0.7,
             "tbd_slots": []}
            for text_, target in zip(TIMEOUTS, targets, strict=True)
        ]}
    )  # fmt: skip


@pytest.fixture
def events(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    published: list[Any] = []
    monkeypatch.setattr(bus, "publish", published.append)
    return published


@pytest.fixture
def people(make_user: Callable[..., User]) -> dict[str, User]:
    return {
        "riya": make_user(role=DefaultRole.DEVELOPER),
        "arjun": make_user(role=DefaultRole.DEVELOPER),
        "ba": make_user(role=DefaultRole.BUSINESS_ANALYST),
        "viewer": make_user(role=DefaultRole.VIEWER),
        "client": make_user(role=DefaultRole.COMPLIANCE_REVIEWER),
    }


@pytest.fixture
def conflict(
    db_session: Session,
    project: Project,
    make_requirement: Callable[..., Requirement],
    people: dict[str, User],
) -> Finding:
    a = make_requirement("Sessions shall time out after 30 minutes.", source_req_id="REQ-012",
                         owner_id=people["riya"].id, state=RequirementState.APPROVED)  # fmt: skip
    b = make_requirement("Payment screens shall time out after 5 minutes.",
                         source_req_id="REQ-031", owner_id=people["arjun"].id,
                         state=RequirementState.APPROVED)  # fmt: skip
    first, second = CandidatePair.ordered(a.id, b.id)
    pair = CandidatePair(requirement_a_id=first, requirement_b_id=second, similarity_score=0.8)
    db_session.add(pair)
    db_session.flush()
    finding = Finding(project_id=project.id, candidate_pair_id=pair.id, confidence=0.9,
                      category=FindingCategory.CONFLICTING, rationale="Different timeouts.",
                      original_ai_output={})  # fmt: skip
    db_session.add(finding)
    db_session.commit()
    return finding


def ready(db: Session, finding: Finding, reply: str | None = None) -> Suggestion:
    row, _ = service.request(db, finding)
    service.generate(db, row.id, LLMClient(FakeTransport([reply or options_reply()])))
    db.refresh(row)
    return row


# ── generation ──────────────────────────────────────────────────────────────────────────────
def test_three_options_with_targets_resolved_to_requirements(
    db_session: Session, conflict: Finding, events: list[Any]
) -> None:
    row = ready(db_session, conflict)

    assert row.status == READY and row.prompt_version == "suggest-v1"
    assert [o["target"] for o in row.options] == ["REQ-012", "REQ-012", "REQ-031"]
    assert all(o["target_requirement_id"] for o in row.options)
    assert row.ready_at is not None and row.llm_calls == 1
    assert [e.type for e in events] == ["suggestion.ready"]


def test_one_live_suggestion_per_finding(db_session: Session, conflict: Finding) -> None:
    first, created = service.request(db_session, conflict)
    again, created_again = service.request(db_session, conflict)
    assert created and not created_again and first.id == again.id


def test_over_budget_it_waits(db_session: Session, conflict: Finding) -> None:
    row, _ = service.request(db_session, conflict)
    service.generate(db_session, row.id, LLMClient(FakeTransport([options_reply()]),
                                                   CountingBudget(0)))  # fmt: skip
    assert (row.status, row.error) == (WAITING_BUDGET, "budget_exhausted")


def test_invalid_options_fail_after_a_retry(db_session: Session, conflict: Finding) -> None:
    bad = options_reply(("REQ-999", "REQ-012", "REQ-031"))
    row, _ = service.request(db_session, conflict)
    service.generate(db_session, row.id, LLMClient(FakeTransport([bad, bad])))
    assert (row.status, row.error) == ("failed", "no_valid_options")


def test_examples_only_when_the_project_opts_in(
    db_session: Session, project: Project, conflict: Finding, people: dict[str, User]
) -> None:
    assert service.examples(db_session, project, "Conflicting") == []
    row = ready(db_session, conflict)
    db_session.add(SuggestionFeedback(suggestion_id=row.id, user_id=people["riya"].id,
                                      action="accepted", option_index=0))  # fmt: skip
    db_session.commit()
    assert service.examples(db_session, project, "Conflicting") == []
    project.use_feedback_examples = True
    found = service.examples(db_session, project, "Conflicting")
    assert [(e.outcome, e.text) for e in found] == [("accepted", TIMEOUTS[0])]


def test_after_a_run_each_new_finding_is_queued(
    db_session: Session, project: Project, conflict: Finding, followups: list[Any]
) -> None:
    run = AnalysisRun(project_id=project.id, scope=AnalysisScope.DOCUMENT,
                      subject_id=project.id, status=AnalysisRunStatus.DONE)  # fmt: skip
    db_session.add(run)
    db_session.flush()
    conflict.analysis_run_id = run.id
    db_session.commit()

    queued = tasks.for_run(db_session, run)
    assert followups == [("suggestions.generate", [str(queued[0])])]
    assert tasks.for_run(db_session, run) == []  # idempotent


# ── feedback (append-only) ──────────────────────────────────────────────────────────────────
def test_feedback_rows_cannot_be_updated_or_deleted(
    db_session: Session, conflict: Finding, people: dict[str, User]
) -> None:
    row = ready(db_session, conflict)
    db_session.add(SuggestionFeedback(suggestion_id=row.id, user_id=people["riya"].id,
                                      action="prefer", option_index=1))  # fmt: skip
    db_session.commit()
    for statement in (
        "UPDATE suggestion_feedback SET option_index = 2",
        "DELETE FROM suggestion_feedback",
    ):
        with pytest.raises(DBAPIError, match="append-only"), db_session.begin_nested():
            db_session.execute(text(statement))


def test_deleting_the_finding_still_cascades(
    db_session: Session, conflict: Finding, people: dict[str, User]
) -> None:
    row = ready(db_session, conflict)
    db_session.add(SuggestionFeedback(suggestion_id=row.id, user_id=people["riya"].id,
                                      action="deferred"))  # fmt: skip
    db_session.commit()
    db_session.execute(text("DELETE FROM findings WHERE id = :id"), {"id": conflict.id})
    assert db_session.scalar(select(SuggestionFeedback.id)) is None


def test_the_schema_requires_text_for_an_edit_and_an_option_for_a_choice(
    db_session: Session, conflict: Finding
) -> None:
    row = ready(db_session, conflict)
    for bad in (
        {"action": "accepted_edited", "option_index": 0},
        {"action": "accepted"},
        {"action": "deferred", "option_index": 1},
        {"action": "expert_rating", "option_index": 0},
    ):
        with pytest.raises(DBAPIError), db_session.begin_nested():
            db_session.add(SuggestionFeedback(suggestion_id=row.id, **bad))
            db_session.flush()


# ── the API ─────────────────────────────────────────────────────────────────────────────────
def url(*parts: object) -> str:
    return "/api/v1/" + "/".join(str(p) for p in parts)


def test_opening_a_finding_queues_its_suggestion(
    client: TestClient, conflict: Finding, people: dict[str, User], followups: list[Any]
) -> None:
    response = client.get(url("findings", conflict.id, "suggestions"),
                          headers=headers_for(people["viewer"]))  # fmt: skip
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending" and body["label"] == "AI"
    assert followups == [("suggestions.generate", [body["id"]])]


def test_both_owners_mark_a_preference(
    client: TestClient, db_session: Session, conflict: Finding, people: dict[str, User]
) -> None:
    row = ready(db_session, conflict)
    for who in ("riya", "arjun"):
        response = client.post(url("suggestions", row.id, "feedback"),
                               json={"action": "prefer", "option_index": 1},
                               headers=headers_for(people[who]))  # fmt: skip
        assert response.status_code == 201, response.text
    body = client.get(url("findings", conflict.id, "suggestions"),
                      headers=headers_for(people["riya"])).json()  # fmt: skip
    assert sorted((p["user_id"], p["option_index"]) for p in body["preferences"]) == sorted(
        [(str(people["riya"].id), 1), (str(people["arjun"].id), 1)]
    )


def test_accepting_returns_a_prefill_and_changes_nothing(
    client: TestClient, db_session: Session, conflict: Finding, people: dict[str, User]
) -> None:
    row = ready(db_session, conflict)
    a = db_session.get(Requirement, row.options[0]["target_requirement_id"])
    assert a is not None
    before = (a.body, a.current_version)

    response = client.post(url("suggestions", row.id, "feedback"),
                           json={"action": "accepted_edited", "option_index": 0,
                                 "final_text": "Sessions shall time out after 15 minutes."},
                           headers=headers_for(people["riya"]))  # fmt: skip

    assert response.status_code == 201, response.text
    prefill = response.json()["prefill"]
    assert prefill["kind"] == "change_request"
    assert prefill["requirement_id"] == str(a.id)
    assert prefill["proposed_body"] == "Sessions shall time out after 15 minutes."
    assert prefill["source_suggestion_id"] == str(row.id)
    db_session.refresh(a)
    assert (a.body, a.current_version) == before  # DR-04


def test_accepting_your_own_proposal_supersedes_it_with_a_post(
    client: TestClient, db_session: Session, conflict: Finding, people: dict[str, User]
) -> None:
    row = ready(db_session, conflict)
    target = db_session.get(Requirement, row.options[0]["target_requirement_id"])
    assert target is not None
    target.state = RequirementState.PROPOSED
    db_session.commit()
    body = client.post(url("suggestions", row.id, "feedback"),
                       json={"action": "accepted", "option_index": 0},
                       headers=headers_for(people["riya"])).json()  # fmt: skip
    assert body["prefill"]["kind"] == "post"


def test_rejections_carry_their_structured_reason(
    client: TestClient, db_session: Session, conflict: Finding, people: dict[str, User]
) -> None:
    row = ready(db_session, conflict)
    for action in ("rejected_meaning", "rejected_infeasible", "rejected_missing_context"):
        response = client.post(url("suggestions", row.id, "feedback"),
                               json={"action": action, "option_index": 2, "reason": "No"},
                               headers=headers_for(people["arjun"]))  # fmt: skip
        assert response.status_code == 201
    deferred = client.post(url("suggestions", row.id, "feedback"), json={"action": "deferred"},
                           headers=headers_for(people["arjun"]))  # fmt: skip
    assert deferred.json()["feedback"]["option_index"] is None


def test_regenerate_supersedes_and_queues(
    client: TestClient,
    db_session: Session,
    conflict: Finding,
    people: dict[str, User],
    followups: list[Any],
) -> None:
    row = ready(db_session, conflict)
    response = client.post(url("findings", conflict.id, "suggestions", "regenerate"),
                           json={"instruction": "Keep 30 minutes for the web app"},
                           headers=headers_for(people["riya"]))  # fmt: skip
    assert response.status_code == 202
    new = response.json()
    assert new["instruction"] == "Keep 30 minutes for the web app" and new["status"] == "pending"
    db_session.refresh(row)
    assert row.status == SUPERSEDED
    assert followups[-1] == ("suggestions.generate", [new["id"]])
    stale = client.post(url("suggestions", row.id, "feedback"), json={"action": "deferred"},
                        headers=headers_for(people["riya"]))  # fmt: skip
    assert stale.status_code == 409


def test_permissions(
    client: TestClient, db_session: Session, conflict: Finding, people: dict[str, User]
) -> None:
    row = ready(db_session, conflict)
    viewer = client.post(url("suggestions", row.id, "feedback"), json={"action": "deferred"},
                         headers=headers_for(people["viewer"]))  # fmt: skip
    assert viewer.status_code == 403
    # A compliance reviewer may discuss but not propose: no acceptance.
    accept = client.post(url("suggestions", row.id, "feedback"),
                         json={"action": "accepted", "option_index": 0},
                         headers=headers_for(people["client"]))  # fmt: skip
    assert accept.status_code == 403
    rating = client.post(url("suggestions", row.id, "rating"),
                         json={"option_index": 0, "rating": 4},
                         headers=headers_for(people["riya"]))  # fmt: skip
    assert rating.status_code == 403


def test_another_workspace_is_404(
    client: TestClient,
    db_session: Session,
    conflict: Finding,
    make_workspace: Callable[..., Workspace],
    make_user: Callable[..., User],
) -> None:
    row = ready(db_session, conflict)
    outsider = make_user(role=DefaultRole.OWNER, workspace=make_workspace())
    headers = headers_for(outsider)
    assert (
        client.get(url("findings", conflict.id, "suggestions"), headers=headers).status_code == 404
    )
    assert client.post(url("suggestions", row.id, "feedback"), json={"action": "deferred"},
                       headers=headers).status_code == 404  # fmt: skip
    assert client.get(url("projects", conflict.project_id, "suggestions", "stats"),
                      headers=headers).status_code == 404  # fmt: skip


def test_stats_report_outcomes_next_to_expert_ratings(
    client: TestClient, db_session: Session, conflict: Finding, people: dict[str, User]
) -> None:
    row = ready(db_session, conflict)
    post = lambda who, body: client.post(  # noqa: E731
        url("suggestions", row.id, "feedback"), json=body, headers=headers_for(people[who])
    )
    post("riya", {"action": "accepted", "option_index": 0})
    post("arjun", {"action": "deferred"})
    post("arjun", {"action": "rejected_meaning", "option_index": 0})  # arjun's latest counts
    client.post(url("suggestions", row.id, "rating"), json={"option_index": 0, "rating": 5},
                headers=headers_for(people["ba"]))  # fmt: skip

    stats = client.get(url("projects", conflict.project_id, "suggestions", "stats"),
                       headers=headers_for(people["viewer"])).json()  # fmt: skip
    (conflicting,) = stats["categories"]
    assert conflicting["outcomes"]["accepted"] == 1
    assert conflicting["outcomes"]["rejected_meaning"] == 1
    assert conflicting["outcomes"]["deferred"] == 0
    assert stats["acceptance_rate"] == 0.5
    assert (stats["expert_ratings"], stats["expert_correct_share"]) == (1, 1.0)


def test_two_requests_at_once_share_the_live_suggestion(
    scratch_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Real concurrency (found in the Sprint 0-5 review): both owners open a new conflict issue at
    the same moment. The second request waits for the first's suggestion and returns it, instead
    of failing on the one-live-suggestion index."""
    _run_migrations(scratch_engine)
    with Session(scratch_engine) as setup:
        workspace = Workspace(name="Race")
        setup.add(workspace)
        setup.commit()
        project = Project(workspace_id=workspace.id, name="Race")
        setup.add(project)
        setup.commit()
        author = create_user(
            setup,
            email="race@example.com",
            password="correct-horse-battery-staple",
            full_name="Race",
        )
        document = Document(
            workspace_id=workspace.id, project_id=project.id, uploaded_by=author.id,
            filename="srs.docx", format=DocumentFormat.DOCX, size_bytes=1, sha256="0" * 64,
            storage_path="srs.docx",
        )  # fmt: skip
        setup.add(document)
        setup.commit()
        a, b = (
            Requirement(document_id=document.id, project_id=project.id, body=body, order_index=i)
            for i, body in enumerate(
                ("Sessions end after 30 minutes.", "Sessions end after 5 minutes.")
            )
        )
        setup.add_all([a, b])
        setup.commit()
        first_id, second_id = CandidatePair.ordered(a.id, b.id)
        pair = CandidatePair(
            requirement_a_id=first_id, requirement_b_id=second_id, similarity_score=0.9
        )
        setup.add(pair)
        setup.commit()
        finding = Finding(project_id=project.id, candidate_pair_id=pair.id, confidence=0.9,
                          category=FindingCategory.CONFLICTING, rationale="Different timeouts.",
                          original_ai_output={})  # fmt: skip
        setup.add(finding)
        setup.commit()
        finding_id = finding.id

    with Session(scratch_engine) as first, Session(scratch_engine) as second:
        monkeypatch.setattr(first, "commit", first.flush)  # the first request is still open
        earlier, made = service.request(first, first.get_one(Finding, finding_id))

        def commit_once_the_other_waits() -> None:
            with scratch_engine.connect() as probe:
                for _ in range(200):
                    waiting = probe.scalar(
                        text("SELECT count(*) FROM pg_stat_activity WHERE wait_event_type = 'Lock'")
                    )
                    if waiting:
                        break
                    time.sleep(0.05)
            Session.commit(first)

        committer = threading.Thread(target=commit_once_the_other_waits)
        committer.start()
        later, made_again = service.request(second, second.get_one(Finding, finding_id))
        committer.join(timeout=30)
        assert (made, made_again) == (True, False)
        assert later.id == first.get_one(Suggestion, earlier.id).id
