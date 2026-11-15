"""The result card (Keval — US-31, FR-57, DR-21): posted in the requirement's thread when its live
analysis ends, with each finding and the owners @mentioned; "waiting for budget" first when the
budget is used up, rewritten when the run finishes; never claims a requirement is conflict-free."""

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.classification.budget import CountingBudget, UnlimitedBudget
from app.classification.llm_client import FakeTransport, LLMClient
from app.classification.result_card import CLEAN, WAITING
from app.core.permissions import DefaultRole
from app.embeddings.model import HashingEmbedder
from app.embeddings.store import embed_document
from app.intake import posts
from app.intake.schemas import ComposerFields
from app.models import (
    AnalysisRun,
    Channel,
    Finding,
    Message,
    MessageKind,
    Project,
    Requirement,
    RequirementState,
    User,
    Workspace,
)
from app.realtime import bus
from app.realtime.events import MESSAGE_UPDATED
from app.services import analysis_orchestrator as orchestrator
from tests.analysis_helpers import Recorder, pair_reply, run_everything, single_reply
from tests.api.conftest import headers_for

BASELINE = "API requests shall time out after 2 seconds."
POSTED = "API requests shall time out after 10 seconds."


@pytest.fixture
def events(monkeypatch: pytest.MonkeyPatch) -> Iterator[bus.InProcessEventBus]:
    test_bus = bus.InProcessEventBus()
    monkeypatch.setattr(bus, "get_bus", lambda: test_bus)
    yield test_bus


@pytest.fixture
def channel(db_session: Session, project: Project) -> Channel:
    channel = Channel(project_id=project.id, name="mobile-app")
    db_session.add(channel)
    db_session.commit()
    return channel


@pytest.fixture
def baseline_owner(make_user: Callable[..., User]) -> User:
    return make_user(role=DefaultRole.DEVELOPER)


@pytest.fixture
def approved(
    db_session: Session,
    project: Project,
    baseline_owner: User,
    make_requirement: Callable[..., Requirement],
) -> Requirement:
    requirement = make_requirement(
        BASELINE,
        source_req_id="REQ-014",
        state=RequirementState.APPROVED,
        owner_id=baseline_owner.id,
    )
    assert requirement.document_id is not None
    embed_document(db_session, requirement.document_id, HashingEmbedder())
    project.similarity_threshold = 0.3
    db_session.commit()
    return requirement


def post(db: Session, channel: Channel, author: User, statement: str = POSTED) -> AnalysisRun:
    fields = ComposerFields.model_validate(
        {
            "template": "free_text",
            "slots": {"statement": statement},
            "type": "non_functional",
            "priority": "must",
        }
    )
    return posts.post_requirement(db, channel=channel, author=author, fields=fields).run


def analyse(db: Session, run: AnalysisRun, llm: LLMClient) -> None:
    recorder = Recorder()
    orchestrator.start_requirement_run(
        db, run.id, llm_configured=True, embedder=HashingEmbedder(), dispatch=recorder
    )
    run_everything(db, recorder, llm)
    orchestrator.after_run(db, run.id)


def cards(db: Session) -> list[Message]:
    return list(db.scalars(select(Message).where(Message.kind == MessageKind.ANALYSIS_CARD)))


def test_a_conflict_is_posted_in_the_thread_and_both_owners_are_mentioned(
    db_session: Session,
    channel: Channel,
    user: User,
    baseline_owner: User,
    approved: Requirement,
    events: bus.InProcessEventBus,
) -> None:
    run = post(db_session, channel, user)

    analyse(db_session, run, LLMClient(FakeTransport([pair_reply(), single_reply()])))

    (card,) = cards(db_session)
    requirement = db_session.get(Requirement, run.subject_id)
    assert requirement is not None and card.parent_id == requirement.origin_message_id
    assert card.author_id is None and card.channel_id == channel.id
    lines = card.body.splitlines()
    assert lines[0].startswith("Analysis of REQ-015")  # numbered after the baseline REQ-014
    assert lines[1].startswith("• Conflicting with REQ-014 · 90% confidence — ")
    assert set(card.mentions) == {str(user.id), str(baseline_owner.id)}
    assert card.payload is not None and card.payload["run_id"] == str(run.id)
    assert card.payload["status"] == "done" and len(card.payload["finding_ids"]) == 1


def test_a_clean_result_says_analysis_can_miss_conflicts_and_mentions_nobody(
    db_session: Session, channel: Channel, user: User, approved: Requirement
) -> None:
    run = post(db_session, channel, user, "Invoices are exported as PDF files every month.")

    analyse(db_session, run, LLMClient(FakeTransport([single_reply()])))

    (card,) = cards(db_session)
    assert CLEAN in card.body and "raise a concern" in card.body
    assert "verified" not in card.body.lower() and "conflict-free" not in card.body.lower()
    assert card.mentions == []


def test_waiting_for_budget_is_said_and_then_replaced_by_the_result(
    db_session: Session,
    channel: Channel,
    user: User,
    approved: Requirement,
    events: bus.InProcessEventBus,
) -> None:
    run = post(db_session, channel, user)
    analyse(db_session, run, LLMClient(FakeTransport([]), CountingBudget(0)))

    (waiting,) = cards(db_session)
    assert WAITING in waiting.body

    again = Recorder()
    orchestrator.resume_waiting(db_session, budget=UnlimitedBudget(), dispatch=again)
    run_everything(db_session, again, LLMClient(FakeTransport([pair_reply(), single_reply()])))
    orchestrator.after_run(db_session, run.id)

    (done,) = cards(db_session)
    assert done.id == waiting.id  # the same card, rewritten
    assert "Conflicting with REQ-014" in done.body and WAITING not in done.body
    assert MESSAGE_UPDATED in [e.type for e in events.published]


def test_without_a_model_the_card_gives_a_readable_reason(
    db_session: Session, channel: Channel, user: User, approved: Requirement
) -> None:
    run = post(db_session, channel, user)
    orchestrator.start_requirement_run(
        db_session, run.id, llm_configured=False, embedder=HashingEmbedder(), dispatch=Recorder()
    )

    orchestrator.after_run(db_session, run.id)

    (card,) = cards(db_session)
    assert "Analysis could not finish: No LLM is configured" in card.body
    assert CLEAN not in card.body  # nothing was checked, so it must not look clean


def test_failed_comparisons_are_reported(
    db_session: Session, channel: Channel, user: User, approved: Requirement
) -> None:
    run = post(db_session, channel, user)

    analyse(db_session, run, LLMClient(FakeTransport(["garbage"] * 4 + [single_reply()])))

    (card,) = cards(db_session)
    assert "1 comparison could not be completed" in card.body


def test_the_finding_records_which_model_produced_it(
    db_session: Session, channel: Channel, user: User, approved: Requirement
) -> None:
    run = post(db_session, channel, user)

    analyse(db_session, run, LLMClient(FakeTransport([pair_reply(), single_reply()])))

    finding = db_session.scalar(select(Finding).where(Finding.analysis_run_id == run.id))
    assert finding is not None and finding.llm_model == "fake/test"


def test_the_run_and_its_findings_can_be_read_by_members_only(
    client: TestClient,
    db_session: Session,
    channel: Channel,
    user: User,
    approved: Requirement,
    make_user: Callable[..., User],
    make_workspace: Callable[..., Workspace],
) -> None:
    run = post(db_session, channel, user)
    analyse(db_session, run, LLMClient(FakeTransport([pair_reply(), single_reply()])))
    viewer = make_user(role=DefaultRole.VIEWER)
    stranger = make_user(role=DefaultRole.OWNER, workspace=make_workspace())
    url = f"/api/v1/analysis-runs/{run.id}"

    read = client.get(url, headers=headers_for(viewer))

    assert read.status_code == 200
    body = read.json()
    assert (body["scope"], body["status"], body["pairs_done"]) == ("requirement", "done", 1)
    (finding,) = body["findings"]
    assert finding["category"] == "Conflicting" and finding["llm_model"] == "fake/test"
    assert {r["label"] for r in finding["requirements"]} == {"REQ-015", "REQ-014"}
    assert client.get(url, headers=headers_for(stranger)).status_code == 404
