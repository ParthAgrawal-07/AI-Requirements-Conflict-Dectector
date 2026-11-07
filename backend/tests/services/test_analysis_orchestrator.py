"""Analysis orchestration (Parth — US-05 enabler, G1): extract → embed → candidates → classify,
counted per run, idempotent, held back in Setup, parked on an exhausted budget."""

import json
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.classification.budget import BudgetExceededError, CountingBudget
from app.classification.llm_client import FakeTransport, LLMClient
from app.classification.tasks import classify_candidate_pair, classify_requirement
from app.embeddings.model import HashingEmbedder
from app.embeddings.store import embed_document
from app.models import (
    AnalysisRun,
    AnalysisRunStatus,
    Document,
    DocumentFormat,
    DocumentStatus,
    Finding,
    Project,
    ProjectStatus,
    Requirement,
    User,
)
from app.realtime import bus
from app.realtime.events import ANALYSIS_COMPLETED
from app.services import analysis_orchestrator as orchestrator

A = "API requests shall time out after 2 seconds."
B = "API requests may take up to 10 seconds before they time out."


def pair_reply(category: str = "Conflicting") -> str:
    return json.dumps(
        {
            "category": category,
            "confidence": 0.9,
            "rationale": "Different timeouts.",
            "dependency_direction": None,
            "evidence": [],
        }
    )


def single_reply() -> str:
    return json.dumps(
        {
            "category": "None",
            "confidence": 0.9,
            "rationale": "Clear.",
            "vague_terms": [],
            "missing_information": [],
        }
    )


class Recorder:
    def __init__(self) -> None:
        self.sent: list[tuple[str, list[str]]] = []

    def __call__(self, name: str, args: list[str]) -> None:
        self.sent.append((name, args))

    def of(self, name: str) -> list[list[str]]:
        return [args for task, args in self.sent if task == name]


@pytest.fixture
def events(monkeypatch: pytest.MonkeyPatch) -> Iterator[bus.InProcessEventBus]:
    test_bus = bus.InProcessEventBus()
    monkeypatch.setattr(bus, "get_bus", lambda: test_bus)
    yield test_bus


@pytest.fixture
def document(db_session: Session, project: Project, user: User) -> Document:
    document = Document(
        workspace_id=project.workspace_id,
        project_id=project.id,
        uploaded_by=user.id,
        filename="srs.docx",
        format=DocumentFormat.DOCX,
        size_bytes=1,
        sha256="1" * 64,
        storage_path="srs.docx",
        status=DocumentStatus.DONE,
    )
    db_session.add(document)
    db_session.flush()
    db_session.add_all(
        Requirement(
            document_id=document.id,
            project_id=project.id,
            body=body,
            source_req_id=label,
            order_index=i,
        )
        for i, (label, body) in enumerate([("REQ-021", A), ("REQ-023", B)])
    )
    db_session.commit()
    embed_document(db_session, document.id, HashingEmbedder())
    project.similarity_threshold = 0.3  # the hashing embedder is coarser than the real model
    db_session.commit()
    return document


def run_everything(db: Session, recorder: Recorder, llm: LLMClient) -> None:
    """What the workers do with the fanned-out tasks."""
    for run_id, pair_id in recorder.of(orchestrator.CLASSIFY_PAIR):
        try:
            classify_candidate_pair(db, uuid.UUID(pair_id), llm, run_id=uuid.UUID(run_id))
        except BudgetExceededError:
            db.rollback()
        orchestrator.record(
            db, uuid.UUID(run_id), "pair", orchestrator.pair_outcome(db, uuid.UUID(pair_id))
        )
    for run_id, requirement_id in recorder.of(orchestrator.CHECK_REQUIREMENT):
        classify_requirement(db, uuid.UUID(requirement_id), llm, run_id=uuid.UUID(run_id))
        orchestrator.record(
            db,
            uuid.UUID(run_id),
            "check",
            orchestrator.check_outcome(db, uuid.UUID(requirement_id)),
        )


def test_a_document_is_classified_end_to_end_and_the_run_reports_its_counts(
    db_session: Session, document: Document, events: bus.InProcessEventBus
) -> None:
    recorder = Recorder()
    run = orchestrator.start_document_run(
        db_session, document.id, llm_configured=True, dispatch=recorder
    )

    assert run is not None and run.status is AnalysisRunStatus.RUNNING
    assert (run.pairs_total, run.checks_total) == (1, 2)
    run_everything(
        db_session,
        recorder,
        LLMClient(FakeTransport([pair_reply(), single_reply(), single_reply()])),
    )

    db_session.refresh(run)
    assert run.status is AnalysisRunStatus.DONE and run.finished_at is not None
    assert (run.pairs_done, run.pairs_failed, run.checks_done, run.checks_failed) == (1, 0, 2, 0)
    finding = db_session.scalar(select(Finding))
    assert finding is not None and finding.analysis_run_id == run.id
    (event,) = [e for e in events.published if e.type == ANALYSIS_COMPLETED]
    assert event.data["status"] == "done" and event.data["pairs_total"] == 1


def test_a_pair_that_fails_is_counted_and_the_run_still_ends(
    db_session: Session, document: Document
) -> None:
    recorder = Recorder()
    run = orchestrator.start_document_run(
        db_session, document.id, llm_configured=True, dispatch=recorder
    )
    assert run is not None

    run_everything(
        db_session, recorder, LLMClient(FakeTransport(["garbage"] * 4 + [single_reply()] * 2))
    )

    db_session.refresh(run)
    assert run.status is AnalysisRunStatus.DONE
    assert (run.pairs_done, run.pairs_failed) == (0, 1)


def test_an_exhausted_budget_parks_the_run(db_session: Session, document: Document) -> None:
    recorder = Recorder()
    run = orchestrator.start_document_run(
        db_session, document.id, llm_configured=True, dispatch=recorder
    )
    assert run is not None
    (run_id, pair_id), *_ = recorder.of(orchestrator.CLASSIFY_PAIR)
    with pytest.raises(BudgetExceededError):
        classify_candidate_pair(
            db_session, uuid.UUID(pair_id), LLMClient(FakeTransport([]), CountingBudget(0))
        )
    orchestrator.record(
        db_session, run.id, "pair", orchestrator.pair_outcome(db_session, uuid.UUID(pair_id))
    )

    db_session.refresh(run)
    assert run.status is AnalysisRunStatus.WAITING_BUDGET


def test_a_second_run_pays_for_nothing_already_classified(
    db_session: Session, document: Document
) -> None:
    recorder = Recorder()
    orchestrator.start_document_run(db_session, document.id, llm_configured=True, dispatch=recorder)
    run_everything(
        db_session,
        recorder,
        LLMClient(FakeTransport([pair_reply("None"), single_reply(), single_reply()])),
    )

    again = Recorder()
    rerun = orchestrator.start_document_run(
        db_session, document.id, llm_configured=True, dispatch=again
    )

    assert rerun is not None and (rerun.pairs_total, rerun.checks_total) == (0, 0)
    assert rerun.status is AnalysisRunStatus.DONE and again.sent == []


def test_without_an_llm_the_run_ends_after_candidates_and_says_so(
    db_session: Session, document: Document
) -> None:
    recorder = Recorder()
    run = orchestrator.start_document_run(
        db_session, document.id, llm_configured=False, dispatch=recorder
    )

    assert run is not None and run.status is AnalysisRunStatus.DONE
    assert run.error_message == orchestrator.NO_LLM and recorder.sent == []


def test_nothing_is_classified_while_the_project_is_in_setup(
    db_session: Session, document: Document, project: Project
) -> None:
    project.status = ProjectStatus.SETUP
    db_session.commit()
    recorder = Recorder()

    assert (
        orchestrator.start_document_run(
            db_session, document.id, llm_configured=True, dispatch=recorder
        )
        is None
    )
    assert recorder.sent == [] and db_session.scalar(select(AnalysisRun)) is None


def test_activating_a_project_analyses_its_documents(
    db_session: Session, document: Document, project: Project
) -> None:
    recorder = Recorder()
    assert orchestrator.analyse_project(db_session, project.id, dispatch=recorder) == 1
    assert recorder.sent == [(orchestrator.RUN_DOCUMENT, [str(document.id)])]


def test_the_document_task_queues_the_analysis(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core import tasks
    from app.core.celery_app import celery_app

    sent: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(celery_app, "send_task", lambda name, args, **_: sent.append((name, args)))
    document_id = str(uuid.uuid4())

    tasks.dispatch_analysis(document_id)

    assert sent == [("analysis.run_document", [document_id])]
    route = celery_app.amqp.router.route({}, "analysis.classify_pair")
    assert route["queue"].name == "analysis"
