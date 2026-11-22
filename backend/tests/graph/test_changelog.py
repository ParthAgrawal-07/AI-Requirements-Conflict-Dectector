"""The written change log (Dhavni — US-55, FR-95, FR-96): every delta sentence is stored with its
kind, nodes, edges and counts; summaries add the counts up from those rows; the map is frozen when
a merge starts a new baseline revision (US-50)."""

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.graph import changelog, deltas, revisions
from app.models import (
    AnalysisRun,
    AnalysisRunStatus,
    AnalysisScope,
    CandidatePair,
    Finding,
    FindingCategory,
    FindingStatus,
    GraphEvent,
    GraphState,
    Project,
    Requirement,
    User,
)
from app.realtime import bus
from tests.analysis_helpers import make_post

SECRET_TEXT = "The vault code is 4711 and must never leave the building."


@pytest.fixture(autouse=True)
def quiet_bus(monkeypatch: pytest.MonkeyPatch) -> Iterator[bus.InProcessEventBus]:
    test_bus = bus.InProcessEventBus()
    monkeypatch.setattr(bus, "get_bus", lambda: test_bus)
    yield test_bus


def conflict(db: Session, a: Requirement, b: Requirement, **extra: object) -> Finding:
    first, second = CandidatePair.ordered(a.id, b.id)
    pair = CandidatePair(requirement_a_id=first, requirement_b_id=second, similarity_score=0.9)
    db.add(pair)
    db.flush()
    finding = Finding(
        project_id=a.project_id,
        candidate_pair_id=pair.id,
        category=extra.pop("category", FindingCategory.CONFLICTING),
        confidence=0.86,
        rationale="r",
        original_ai_output={},
        **extra,
    )
    db.add(finding)
    db.commit()
    return finding


def rows(db: Session, project: Project) -> list[GraphEvent]:
    return list(
        db.scalars(
            select(GraphEvent)
            .where(GraphEvent.project_id == project.id)
            .order_by(GraphEvent.created_at, GraphEvent.id)
        )
    )


def test_every_sentence_is_stored_with_its_revision_kind_and_nodes(
    db_session: Session, project: Project, user: User
) -> None:
    post = make_post(db_session, project, user, SECRET_TEXT, label="REQ-031")

    delta = deltas.publish(
        db_session,
        project.id,
        deltas.Change(new_requirements={post.id}, sentences=["Test added REQ-031 (Proposed)."]),
        actor=user,
    )

    assert delta is not None
    (row,) = rows(db_session, project)
    assert (row.revision, row.kind, row.sentence) == (
        delta.to_revision,
        "added",
        "Test added REQ-031 (Proposed).",
    )
    assert row.node_ids == [str(post.id)] and row.actor_id == user.id
    assert row.counts == {"requirements_added": 1}
    assert SECRET_TEXT not in row.sentence


def test_a_layout_change_without_sentences_writes_nothing(
    db_session: Session, project: Project, user: User
) -> None:
    post = make_post(db_session, project, user, "x", label="REQ-1")
    deltas.publish(db_session, project.id, deltas.Change(requirements={post.id}), actor=user)
    assert rows(db_session, project) == []


def test_a_run_with_a_new_conflict_is_logged_as_conflict_found_with_both_ends(
    db_session: Session,
    project: Project,
    user: User,
    make_requirement: Callable[..., Requirement],
) -> None:
    old = make_requirement("Sessions end after 30 minutes.", source_req_id="REQ-014")
    post = make_post(db_session, project, user, "Sessions end after 5 minutes.", label="REQ-031")
    run = AnalysisRun(
        project_id=project.id,
        scope=AnalysisScope.REQUIREMENT,
        subject_id=post.id,
        status=AnalysisRunStatus.DONE,
    )
    db_session.add(run)
    db_session.commit()
    finding = conflict(db_session, post, old, analysis_run_id=run.id)

    deltas.run_finished(db_session, run)

    (row,) = rows(db_session, project)
    assert row.kind == "conflict_found"
    assert set(row.node_ids) == {str(post.id), str(old.id)}
    assert row.edge_ids == [str(finding.id)]
    assert row.counts == {"conflicts_opened": 1}


def test_dismissing_a_conflict_counts_it_as_resolved(
    db_session: Session,
    project: Project,
    user: User,
    make_requirement: Callable[..., Requirement],
) -> None:
    a = make_requirement("a", source_req_id="REQ-1")
    b = make_requirement("b", source_req_id="REQ-2")
    finding = conflict(db_session, a, b)
    finding.status = FindingStatus.DISMISSED
    db_session.commit()

    deltas.publish(
        db_session,
        project.id,
        deltas.Change(
            findings={finding.id}, sentences=["Test dismissed it."], kind="conflict_resolved"
        ),
        actor=user,
    )

    (row,) = rows(db_session, project)
    assert row.kind == "conflict_resolved" and row.counts == {"conflicts_resolved": 1}
    assert set(row.node_ids) == {str(a.id), str(b.id)}  # the panel can highlight both ends


def test_only_the_first_sentence_of_a_change_carries_its_counts(
    db_session: Session, project: Project, user: User
) -> None:
    post = make_post(db_session, project, user, "x", label="REQ-1")
    deltas.publish(
        db_session,
        project.id,
        deltas.Change(
            requirements={post.id},
            sentences=["One.", "Two."],
            kind="merged",
            counts={"change_requests_merged": 1, "requirements_changed": 1},
        ),
        actor=user,
    )
    first, second = rows(db_session, project)
    assert first.counts == {"change_requests_merged": 1, "requirements_changed": 1}
    assert second.counts == {}


def test_unknown_kinds_and_counts_are_refused(db_session: Session, project: Project) -> None:
    with pytest.raises(ValueError, match="kind"):
        changelog.record(db_session, project.id, revision=1, baseline_revision=0, actor_id=None,
                         kind="gossip", sentences=["x"], node_ids=(), edge_ids=(),
                         counts={})  # fmt: skip
    with pytest.raises(ValueError, match="counts"):
        changelog.record(db_session, project.id, revision=1, baseline_revision=0, actor_id=None,
                         kind="added", sentences=["x"], node_ids=(), edge_ids=(),
                         counts={"likes": 3})  # fmt: skip


def test_events_filter_by_kind_actor_requirement_and_revision(
    db_session: Session, project: Project, user: User, make_user: Callable[..., User]
) -> None:
    other = make_user()
    a = make_post(db_session, project, user, "a", label="REQ-1")
    b = make_post(db_session, project, other, "b", label="REQ-2")
    first = deltas.publish(db_session, project.id,
                           deltas.Change(new_requirements={a.id}, sentences=["A."]),
                           actor=user)  # fmt: skip
    deltas.publish(db_session, project.id,
                   deltas.Change(requirements={b.id}, sentences=["B."], kind="state"),
                   actor=other)  # fmt: skip
    assert first is not None

    assert [e.sentence for e in changelog.events(db_session, project.id)] == ["B.", "A."]
    assert [e.sentence for e in changelog.events(db_session, project.id, kinds=["state"])] == ["B."]
    assert [e.sentence for e in changelog.events(db_session, project.id, actor_id=user.id)] == [
        "A."
    ]
    assert [e.sentence for e in changelog.events(db_session, project.id, requirement_id=b.id)] == [
        "B."
    ]
    assert [
        e.sentence
        for e in changelog.events(db_session, project.id, until_revision=first.to_revision)
    ] == ["A."]


def test_a_summary_adds_up_the_counts_and_lists_the_important_changes(
    db_session: Session, project: Project, user: User
) -> None:
    a = make_post(db_session, project, user, "a", label="REQ-1")
    b = make_post(db_session, project, user, "b", label="REQ-2")
    deltas.publish(db_session, project.id,
                   deltas.Change(new_requirements={a.id, b.id}, sentences=["Two added."]),
                   actor=user)  # fmt: skip
    deltas.publish(
        db_session,
        project.id,
        deltas.Change(
            requirements={a.id},
            sentences=["Test merged RCR-3: REQ-1 is now v2."],
            kind="merged",
            counts={"change_requests_merged": 1, "requirements_changed": 1},
        ),
        actor=user,
    )
    deltas.publish(db_session, project.id,
                   deltas.Change(requirements={b.id}, sentences=["Owner changed."], kind="owner"),
                   actor=user)  # fmt: skip

    result = changelog.summary(db_session, project.id, since=None, since_label="the beginning")

    assert result.counts["requirements_added"] == 2
    assert result.counts["change_requests_merged"] == 1
    assert result.counts["requirements_changed"] == 1
    assert result.total_events == 3
    assert [e.kind for e in result.highlights] == ["merged", "added"]  # owner is not "important"
    assert "## Changes since the beginning" in result.markdown
    assert "- 2 requirements added" in result.markdown
    assert "Test merged RCR-3: REQ-1 is now v2." in result.markdown
    assert result.keys == ["RCR-3", "REQ-1"]


def test_a_summary_since_a_moment_ignores_what_came_before(
    db_session: Session, project: Project, user: User
) -> None:
    a = make_post(db_session, project, user, "a", label="REQ-1")
    deltas.publish(db_session, project.id,
                   deltas.Change(new_requirements={a.id}, sentences=["Old."]),
                   actor=user)  # fmt: skip
    later = datetime.now(UTC) + timedelta(seconds=1)
    result = changelog.summary(db_session, project.id, since=later, since_label="later")
    assert result.total_events == 0
    assert "No changes in this period." in result.markdown


def test_last_visit_is_per_member_and_project(
    db_session: Session, project: Project, user: User
) -> None:
    assert changelog.last_visit(db_session, user.id, project.id) is None
    first = changelog.mark_seen(db_session, user.id, project.id)
    assert changelog.last_visit(db_session, user.id, project.id) == first
    second = changelog.mark_seen(db_session, user.id, project.id)
    assert second >= first


def test_the_map_is_frozen_once_per_new_baseline_revision(
    db_session: Session, project: Project, user: User
) -> None:
    a = make_post(db_session, project, user, "a", label="REQ-1")
    deltas.publish(db_session, project.id,
                   deltas.Change(requirements={a.id}, sentences=["x"]), actor=user)  # fmt: skip
    assert db_session.scalars(select(GraphState)).all() == []  # nothing merged yet

    project.baseline_revision = 1
    db_session.commit()
    for sentence in ("merged", "later"):
        deltas.publish(db_session, project.id,
                       deltas.Change(requirements={a.id}, sentences=[sentence]),
                       actor=user)  # fmt: skip

    (state,) = db_session.scalars(select(GraphState)).all()
    assert state.baseline_revision == 1 and state.baseline_id is None
    assert [n["label"] for n in state.nodes] == ["REQ-1"]
    points = revisions.points(db_session, project)
    assert [p.label for p in points] == ["Baseline revision 1", "Now"]


def test_a_frozen_map_keeps_what_it_showed_then(
    db_session: Session, project: Project, user: User, make_requirement: Callable[..., Requirement]
) -> None:
    a = make_requirement("a", source_req_id="REQ-1")
    b = make_requirement("b", source_req_id="REQ-2")
    finding = conflict(db_session, a, b)
    project.baseline_revision = 1
    db_session.commit()
    assert revisions.capture_revision(db_session, project.id)

    finding.status = FindingStatus.DISMISSED  # reviewed afterwards
    db_session.commit()

    state = db_session.scalars(select(GraphState)).one()
    nodes, edges = revisions.state(state)
    assert {n.label for n in nodes} == {"REQ-1", "REQ-2"}
    assert [(e.id, e.status) for e in edges] == [(finding.id, "flagged")]
