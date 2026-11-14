"""Graph deltas (Dhavni — US-14, FR-84, NFR-32): revisions, added/changed/removed from the stored
state, the run delta with its sentence and placement, and no requirement text on the bus."""

import uuid
from collections.abc import Callable, Iterator

import pytest
from sqlalchemy.orm import Session

from app.embeddings.model import HashingEmbedder
from app.graph import deltas
from app.graph.positions import NEIGHBOUR_DISTANCE
from app.models import (
    AnalysisRun,
    AnalysisRunStatus,
    AnalysisScope,
    CandidatePair,
    Finding,
    FindingCategory,
    FindingStatus,
    NodePosition,
    Project,
    Requirement,
    Severity,
    User,
)
from app.realtime import bus
from app.realtime.events import GRAPH_DELTA, Event
from tests.analysis_helpers import make_post

SECRET_TEXT = "The vault code is 4711 and must never leave the building."


@pytest.fixture
def events(monkeypatch: pytest.MonkeyPatch) -> Iterator[bus.InProcessEventBus]:
    test_bus = bus.InProcessEventBus()
    monkeypatch.setattr(bus, "get_bus", lambda: test_bus)
    yield test_bus


def graph_events(events: bus.InProcessEventBus) -> list[Event]:
    return [e for e in events.published if e.type == GRAPH_DELTA]


def pair_finding(
    db: Session, a: Requirement, b: Requirement, *, run: AnalysisRun | None = None, **extra: object
) -> Finding:
    first, second = CandidatePair.ordered(a.id, b.id)
    pair = CandidatePair(requirement_a_id=first, requirement_b_id=second, similarity_score=0.9)
    db.add(pair)
    db.flush()
    finding = Finding(
        project_id=a.project_id,
        candidate_pair_id=pair.id,
        analysis_run_id=run.id if run else None,
        category=extra.pop("category", FindingCategory.CONFLICTING),
        confidence=0.86,
        rationale="r",
        original_ai_output={},
        **extra,
    )
    db.add(finding)
    db.commit()
    return finding


def test_each_publish_bumps_the_revision_by_one(
    db_session: Session, project: Project, user: User, events: bus.InProcessEventBus
) -> None:
    post = make_post(db_session, project, user, SECRET_TEXT, label="REQ-031")

    first = deltas.publish(db_session, project.id, deltas.Change(new_requirements={post.id}))
    second = deltas.publish(db_session, project.id, deltas.Change(requirements={post.id}))

    assert first is not None and second is not None
    assert (first.from_revision, first.to_revision) == (0, 1)
    assert (second.from_revision, second.to_revision) == (1, 2)
    db_session.refresh(project)
    assert project.graph_revision == 2
    assert [e.data["to_revision"] for e in graph_events(events)] == [1, 2]


def test_an_empty_change_publishes_nothing(
    db_session: Session, project: Project, events: bus.InProcessEventBus
) -> None:
    assert deltas.publish(db_session, project.id, deltas.Change()) is None
    db_session.refresh(project)
    assert project.graph_revision == 0 and graph_events(events) == []


def test_new_findings_are_added_and_dismissed_or_stale_ones_removed(
    db_session: Session, project: Project, user: User, events: bus.InProcessEventBus
) -> None:
    a = make_post(db_session, project, user, "a", label="REQ-001")
    b = make_post(db_session, project, user, "b", label="REQ-002")
    c = make_post(db_session, project, user, "c", label="REQ-003")
    live = pair_finding(db_session, a, b)
    dismissed = pair_finding(db_session, a, c, status=FindingStatus.DISMISSED)
    stale = pair_finding(db_session, b, c, is_stale=True)
    confirmed = Finding(
        project_id=project.id,
        requirement_id=a.id,
        category=FindingCategory.AMBIGUOUS,
        confidence=0.7,
        rationale="r",
        original_ai_output={},
        status=FindingStatus.CONFIRMED,
    )
    db_session.add(confirmed)
    db_session.commit()

    delta = deltas.publish(
        db_session,
        project.id,
        deltas.Change(new_findings={live.id}, findings={dismissed.id, stale.id, confirmed.id}),
    )

    assert delta is not None
    assert [e.id for e in delta.added.edges] == [live.id]
    assert [(e.id, e.status, e.source == e.target) for e in delta.changed.edges] == [
        (confirmed.id, "confirmed", True)
    ]
    assert set(delta.removed.edge_ids) == {dismissed.id, stale.id}


def test_the_event_names_requirements_by_id_and_never_carries_their_text(
    db_session: Session, project: Project, user: User, events: bus.InProcessEventBus
) -> None:
    post = make_post(db_session, project, user, SECRET_TEXT, label="REQ-031")

    deltas.publish(
        db_session,
        project.id,
        deltas.Change(new_requirements={post.id}, sentences=["Test User added REQ-031."]),
        actor=user,
    )

    (event,) = graph_events(events)
    assert event.project_id == project.id and event.workspace_id == project.workspace_id
    assert event.data["actor_name"] == "Test User"
    assert event.data["added"]["nodes"][0]["label"] == "REQ-031"
    assert "4711" not in event.model_dump_json()


def test_a_finished_post_run_adds_its_edges_places_its_node_and_says_so(
    db_session: Session, project: Project, user: User, events: bus.InProcessEventBus
) -> None:
    baseline = make_post(
        db_session, project, user, "Sessions end after 30 minutes.", label="REQ-014"
    )
    db_session.add(NodePosition(requirement_id=baseline.id, project_id=project.id, x=100, y=50))
    post = make_post(db_session, project, user, "Sessions end after 5 minutes.", label="REQ-031")
    run = AnalysisRun(
        project_id=project.id,
        scope=AnalysisScope.REQUIREMENT,
        subject_id=post.id,
        status=AnalysisRunStatus.DONE,
    )
    db_session.add(run)
    db_session.commit()
    finding = pair_finding(db_session, baseline, post, run=run, severity=Severity.HIGH)

    delta = deltas.run_finished(db_session, run)

    assert delta is not None
    assert [e.id for e in delta.added.edges] == [finding.id]
    assert delta.sentences == ["Analysis of REQ-031: 1 conflict with REQ-014 (high)."]
    assert delta.actor_id == user.id
    (node,) = delta.changed.nodes
    assert node.id == post.id and node.x is not None and node.y is not None
    distance = ((node.x - 100) ** 2 + (node.y - 50) ** 2) ** 0.5
    assert distance == pytest.approx(NEIGHBOUR_DISTANCE)


def test_a_clean_run_never_claims_the_requirement_is_conflict_free(
    db_session: Session, project: Project, user: User, events: bus.InProcessEventBus
) -> None:
    post = make_post(db_session, project, user, "Invoices are exported as PDF.", label="REQ-050")
    run = AnalysisRun(
        project_id=project.id,
        scope=AnalysisScope.REQUIREMENT,
        subject_id=post.id,
        status=AnalysisRunStatus.DONE,
    )
    db_session.add(run)
    db_session.commit()

    delta = deltas.run_finished(db_session, run)

    assert delta is not None
    (sentence,) = delta.sentences
    assert "no issues detected" in sentence and "can miss" in sentence
    assert "verified" not in sentence.lower() and "conflict-free" not in sentence.lower()


def test_a_new_node_without_findings_is_placed_by_its_closest_requirement(
    db_session: Session, project: Project, user: User, events: bus.InProcessEventBus
) -> None:
    from app.embeddings.incremental import embed_requirements

    near = make_post(db_session, project, user, "Sessions end after 30 minutes.", label="REQ-014")
    db_session.add(NodePosition(requirement_id=near.id, project_id=project.id, x=0, y=0))
    post = make_post(db_session, project, user, "Sessions end after 5 minutes.", label="REQ-031")
    embed_requirements(db_session, [near.id, post.id], HashingEmbedder())
    run = AnalysisRun(
        project_id=project.id,
        scope=AnalysisScope.REQUIREMENT,
        subject_id=post.id,
        status=AnalysisRunStatus.DONE,
    )
    db_session.add(run)
    db_session.commit()

    deltas.run_finished(db_session, run)

    placed = db_session.get(NodePosition, post.id)
    assert placed is not None
    assert (placed.x**2 + placed.y**2) ** 0.5 == pytest.approx(NEIGHBOUR_DISTANCE)


def test_a_finished_document_run_adds_its_requirements_and_counts_the_findings(
    db_session: Session,
    project: Project,
    make_requirement: Callable[..., Requirement],
    events: bus.InProcessEventBus,
) -> None:
    a = make_requirement("Sessions end after 30 minutes.", source_req_id="REQ-014")
    b = make_requirement("Sessions end after 5 minutes.", source_req_id="REQ-031")
    assert a.document_id is not None
    run = AnalysisRun(
        project_id=project.id,
        scope=AnalysisScope.DOCUMENT,
        subject_id=a.document_id,
        status=AnalysisRunStatus.DONE,
    )
    db_session.add(run)
    db_session.commit()
    pair_finding(db_session, a, b, run=run)

    delta = deltas.run_finished(db_session, run)

    assert delta is not None
    assert {n.id for n in delta.added.nodes} == {a.id, b.id}
    assert delta.sentences == ["Analysis of srs.docx finished: 1 conflict."]


def test_a_run_for_a_requirement_that_is_gone_publishes_nothing(
    db_session: Session, project: Project, events: bus.InProcessEventBus
) -> None:
    run = AnalysisRun(
        project_id=project.id,
        scope=AnalysisScope.REQUIREMENT,
        subject_id=uuid.uuid4(),
        status=AnalysisRunStatus.DONE,
    )
    db_session.add(run)
    db_session.commit()

    assert deltas.run_finished(db_session, run) is None
    assert graph_events(events) == []
