"""Live analysis of a posted requirement (Dhavni — US-31 queue and events; FR-56, NFR-28):
queued with the post, run against the baseline, held in Setup, followed up after it closes, and
resumed once the budget allows."""

import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from sqlalchemy import Row, select
from sqlalchemy.orm import Session

from app.classification.budget import CountingBudget, UnlimitedBudget
from app.classification.llm_client import FakeTransport, LLMClient
from app.embeddings.model import HashingEmbedder
from app.embeddings.store import embed_document
from app.models import (
    AnalysisRun,
    AnalysisRunStatus,
    AnalysisScope,
    Finding,
    FindingCategory,
    Project,
    ProjectStatus,
    Requirement,
    RequirementState,
    User,
)
from app.realtime import bus
from app.realtime.events import ANALYSIS_COMPLETED, GRAPH_DELTA
from app.services import analysis_orchestrator as orchestrator
from tests.analysis_helpers import Recorder, make_post, pair_reply, run_everything, single_reply

BASELINE = "API requests shall time out after 2 seconds."
POSTED = "API requests shall time out after 10 seconds."


@pytest.fixture
def events(monkeypatch: pytest.MonkeyPatch) -> Iterator[bus.InProcessEventBus]:
    test_bus = bus.InProcessEventBus()
    monkeypatch.setattr(bus, "get_bus", lambda: test_bus)
    yield test_bus


@pytest.fixture
def approved(
    db_session: Session, project: Project, make_requirement: Callable[..., Requirement]
) -> Requirement:
    requirement = make_requirement(
        BASELINE, source_req_id="REQ-014", state=RequirementState.APPROVED
    )
    assert requirement.document_id is not None
    embed_document(db_session, requirement.document_id, HashingEmbedder())
    project.similarity_threshold = 0.3  # the hashing embedder is coarser than the real model
    db_session.commit()
    return requirement


def queue(db: Session, requirement: Requirement) -> AnalysisRun:
    run = orchestrator.queue_requirement_run(db, requirement)
    db.commit()
    return run


def start(db: Session, run: AnalysisRun, recorder: Recorder) -> AnalysisRun | None:
    return orchestrator.start_requirement_run(
        db, run.id, llm_configured=True, embedder=HashingEmbedder(), dispatch=recorder
    )


def test_a_post_is_compared_with_the_baseline_and_the_run_closes_with_its_finding(
    db_session: Session,
    project: Project,
    user: User,
    approved: Requirement,
    events: bus.InProcessEventBus,
    followups: list[tuple[str, list[str]]],
) -> None:
    post = make_post(db_session, project, user, POSTED, label="REQ-031")
    run = queue(db_session, post)
    assert run.status is AnalysisRunStatus.QUEUED and run.scope is AnalysisScope.REQUIREMENT
    recorder = Recorder()

    started = start(db_session, run, recorder)
    run_everything(db_session, recorder, LLMClient(FakeTransport([pair_reply(), single_reply()])))

    assert started is not None
    db_session.refresh(run)
    assert run.status is AnalysisRunStatus.DONE
    assert (run.pairs_total, run.pairs_done, run.checks_total, run.checks_done) == (1, 1, 1, 1)
    finding = db_session.scalar(select(Finding).where(Finding.analysis_run_id == run.id))
    assert finding is not None and finding.category is FindingCategory.CONFLICTING
    (completed,) = [e for e in events.published if e.type == ANALYSIS_COMPLETED]
    assert completed.data["scope"] == "requirement" and completed.data["subject_id"] == str(post.id)
    assert followups == [(orchestrator.AFTER_RUN, [str(run.id), orchestrator.CLOSED])]


def test_after_the_run_the_map_hears_about_it(
    db_session: Session,
    project: Project,
    user: User,
    approved: Requirement,
    events: bus.InProcessEventBus,
) -> None:
    post = make_post(db_session, project, user, POSTED, label="REQ-031")
    run = queue(db_session, post)
    recorder = Recorder()
    start(db_session, run, recorder)
    run_everything(db_session, recorder, LLMClient(FakeTransport([pair_reply(), single_reply()])))

    orchestrator.after_run(db_session, run.id)

    (delta,) = [e for e in events.published if e.type == GRAPH_DELTA]
    assert delta.data["sentences"] == ["Analysis of REQ-031: 1 conflict with REQ-014."]


def test_a_rejected_baseline_requirement_is_not_compared(
    db_session: Session, project: Project, user: User, approved: Requirement
) -> None:
    approved.state = RequirementState.REJECTED
    db_session.commit()
    post = make_post(db_session, project, user, POSTED)
    run = queue(db_session, post)
    recorder = Recorder()

    start(db_session, run, recorder)

    db_session.refresh(run)
    assert run.pairs_total == 0 and run.checks_total == 1
    assert recorder.of(orchestrator.CLASSIFY_PAIR) == []


def test_a_run_delivered_twice_starts_once(
    db_session: Session, project: Project, user: User, approved: Requirement
) -> None:
    post = make_post(db_session, project, user, POSTED)
    run = queue(db_session, post)
    recorder = Recorder()

    assert start(db_session, run, recorder) is not None
    assert start(db_session, run, recorder) is None
    assert len(recorder.of(orchestrator.CHECK_REQUIREMENT)) == 1


def test_in_setup_the_run_stays_queued_until_activation_dispatches_it(
    db_session: Session,
    make_project: Callable[..., Project],
    user: User,
) -> None:
    project = make_project(status=ProjectStatus.SETUP)
    post = make_post(db_session, project, user, POSTED)
    run = queue(db_session, post)

    assert start(db_session, run, Recorder()) is None
    db_session.refresh(run)
    assert run.status is AnalysisRunStatus.QUEUED

    recorder = Recorder()
    project.status = ProjectStatus.ACTIVE
    db_session.commit()
    orchestrator.analyse_project(db_session, project.id, dispatch=recorder)

    assert recorder.of(orchestrator.RUN_REQUIREMENT) == [[str(run.id)]]


def test_without_an_llm_the_run_ends_and_says_so(
    db_session: Session, project: Project, user: User, approved: Requirement
) -> None:
    post = make_post(db_session, project, user, POSTED)
    run = queue(db_session, post)

    orchestrator.start_requirement_run(
        db_session, run.id, llm_configured=False, embedder=HashingEmbedder(), dispatch=Recorder()
    )

    db_session.refresh(run)
    assert run.status is AnalysisRunStatus.DONE and run.error_message == orchestrator.NO_LLM


def test_an_exhausted_budget_parks_the_run_once_and_it_resumes_when_budget_returns(
    db_session: Session,
    project: Project,
    user: User,
    approved: Requirement,
    events: bus.InProcessEventBus,
    followups: list[tuple[str, list[str]]],
) -> None:
    post = make_post(db_session, project, user, POSTED)
    run = queue(db_session, post)
    recorder = Recorder()
    start(db_session, run, recorder)

    run_everything(db_session, recorder, LLMClient(FakeTransport([]), CountingBudget(0)))

    db_session.refresh(run)
    assert run.status is AnalysisRunStatus.WAITING_BUDGET
    parked = [e for e in events.published if e.type == ANALYSIS_COMPLETED]
    assert [e.data["status"] for e in parked] == ["waiting_budget"]  # once, not per item
    assert followups == [(orchestrator.AFTER_RUN, [str(run.id), orchestrator.PARKED])]

    assert (
        orchestrator.resume_waiting(db_session, budget=CountingBudget(0), llm_configured=True) == []
    )

    again = Recorder()
    resumed = orchestrator.resume_waiting(
        db_session, budget=UnlimitedBudget(), llm_configured=True, dispatch=again
    )
    assert resumed == [run.id]
    db_session.refresh(run)
    assert run.status is AnalysisRunStatus.RUNNING
    assert (run.pairs_total, run.checks_total) == (1, 1)
    run_everything(db_session, again, LLMClient(FakeTransport([pair_reply(), single_reply()])))
    db_session.refresh(run)
    assert run.status is AnalysisRunStatus.DONE


def test_a_run_that_is_not_waiting_is_not_resumed(
    db_session: Session, project: Project, user: User
) -> None:
    post = make_post(db_session, project, user, POSTED)
    run = queue(db_session, post)

    for run_id in (run.id, uuid.uuid4()):
        resumed = orchestrator.resume_run(
            db_session, run_id, llm_configured=True, dispatch=Recorder()
        )
        assert resumed is False


def park(db: Session, project: Project, user: User) -> AnalysisRun:
    post = make_post(db, project, user, POSTED)
    run = queue(db, post)
    recorder = Recorder()
    start(db, run, recorder)
    run_everything(db, recorder, LLMClient(FakeTransport([]), CountingBudget(0)))
    db.refresh(run)
    assert run.status is AnalysisRunStatus.WAITING_BUDGET
    return run


def test_a_failed_start_hands_the_run_back_so_a_retry_starts_it(
    db_session: Session,
    project: Project,
    user: User,
    approved: Requirement,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.embeddings import incremental

    post = make_post(db_session, project, user, POSTED)
    run = queue(db_session, post)

    def broken(*_: object, **__: object) -> None:
        raise RuntimeError("embedder down")

    with monkeypatch.context() as patch:
        patch.setattr(incremental, "candidates_for_requirement", broken)
        with pytest.raises(RuntimeError):
            start(db_session, run, Recorder())

    db_session.refresh(run)
    assert run.status is AnalysisRunStatus.QUEUED and run.started_at is None
    recorder = Recorder()
    assert start(db_session, run, recorder) is not None
    assert len(recorder.of(orchestrator.CHECK_REQUIREMENT)) == 1


def test_the_park_event_carries_the_status_the_park_left(
    db_session: Session,
    project: Project,
    user: User,
    approved: Requirement,
    events: bus.InProcessEventBus,
    followups: list[tuple[str, list[str]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published = orchestrator._publish
    swept: list[bool] = []

    def resume_first(db: Session, row: Row[*tuple[Any, ...]]) -> None:
        # A sweep resumes the run between the park commit and the announcement.
        if not swept:
            swept.append(
                orchestrator.resume_run(db, run_id, llm_configured=True, dispatch=Recorder())
            )
        published(db, row)

    post = make_post(db_session, project, user, POSTED)
    run = queue(db_session, post)
    run_id = run.id
    recorder = Recorder()
    start(db_session, run, recorder)
    monkeypatch.setattr(orchestrator, "_publish", resume_first)

    run_everything(db_session, recorder, LLMClient(FakeTransport([]), CountingBudget(0)))

    statuses = {e.data["status"] for e in events.published if e.type == ANALYSIS_COMPLETED}
    assert swept == [True] and statuses == {"waiting_budget"}  # never the sweep's "running"


def test_a_late_park_follow_up_sends_no_second_map_delta(
    db_session: Session,
    project: Project,
    user: User,
    approved: Requirement,
    events: bus.InProcessEventBus,
    followups: list[tuple[str, list[str]]],
) -> None:
    run = park(db_session, project, user)
    again = Recorder()
    orchestrator.resume_run(db_session, run.id, llm_configured=True, dispatch=again)
    run_everything(db_session, again, LLMClient(FakeTransport([pair_reply(), single_reply()])))
    db_session.refresh(run)
    assert run.status is AnalysisRunStatus.DONE

    assert [args[1] for _, args in followups] == [orchestrator.PARKED, orchestrator.CLOSED]
    orchestrator.after_run(db_session, run.id, orchestrator.CLOSED)
    orchestrator.after_run(db_session, run.id, orchestrator.PARKED)  # delivered late

    assert len([e for e in events.published if e.type == GRAPH_DELTA]) == 1


def test_a_resumed_run_is_claimed_once_even_from_a_stale_copy(
    db_session: Session, project: Project, user: User, approved: Requirement
) -> None:
    run = park(db_session, project, user)
    first = Recorder()
    assert orchestrator.resume_run(db_session, run.id, llm_configured=True, dispatch=first)

    # A second sweep that loaded the row while it was still waiting.
    run.status = AnalysisRunStatus.WAITING_BUDGET
    second = Recorder()
    assert not orchestrator.resume_run(db_session, run.id, llm_configured=True, dispatch=second)
    assert second.sent == [] and first.of(orchestrator.CLASSIFY_PAIR)


def test_a_run_resumed_without_an_llm_ends_and_says_so(
    db_session: Session, project: Project, user: User, approved: Requirement
) -> None:
    run = park(db_session, project, user)
    recorder = Recorder()

    assert orchestrator.resume_run(db_session, run.id, llm_configured=False, dispatch=recorder)

    db_session.refresh(run)
    assert run.status is AnalysisRunStatus.DONE and run.error_message == orchestrator.NO_LLM
    assert recorder.sent == []
