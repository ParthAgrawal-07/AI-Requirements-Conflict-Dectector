"""Change-log sentences match the map deltas (Abhyudit — US-55, Sprint 6 regression).

On the planted SRS, real actions through the API — a finding dismissed, a concern raised, a
requirement protected, a link made — each publish a ``graph.delta``. For every one, the written
change log holds exactly the delta's sentences, under the delta's revision, with the kind and the
requirements the panel highlights; and a summary over the whole session counts what the database
holds.
"""

import json
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import DefaultRole
from app.graph import changelog
from app.models import Finding, FindingCategory, FindingStatus, GraphEvent, Project, User
from app.realtime import bus
from app.realtime.events import GRAPH_DELTA
from tests.api.conftest import headers_for
from tests.integration.planted import Planted, load, scripted


@pytest.fixture
def events(monkeypatch: pytest.MonkeyPatch) -> Iterator[bus.InProcessEventBus]:
    test_bus = bus.InProcessEventBus()
    monkeypatch.setattr(bus, "get_bus", lambda: test_bus)
    yield test_bus


@pytest.fixture
def planted(db_session: Session, project: Project, make_user: Callable[..., User]) -> Planted:
    owners: dict[str, User] = {}
    for name in scripted()["owners"]:
        user = make_user(role=DefaultRole.BUSINESS_ANALYST)
        user.full_name = name
        owners[name] = user
    db_session.commit()
    return load(db_session, project, owners)


def url(*parts: object) -> str:
    return "/api/v1/" + "/".join(str(p) for p in parts)


def test_every_delta_is_written_down_exactly_once_with_its_revision(
    client: TestClient,
    db_session: Session,
    planted: Planted,
    make_user: Callable[..., User],
    events: bus.InProcessEventBus,
) -> None:
    analyst = make_user(role=DefaultRole.BUSINESS_ANALYST)
    reviewer = make_user(role=DefaultRole.COMPLIANCE_REVIEWER)
    project, req = planted.project, planted.by_label
    conflict = planted.findings[frozenset(("REQ-021", "REQ-023"))]

    steps = [
        client.post(url("findings", conflict.id, "review"),
                    json={"action": "dismiss", "reason": "Different APIs"},
                    headers=headers_for(analyst)),
        client.post(url("projects", project.id, "concerns"),
                    json={"category": "Conflicting",
                          "requirement_ids": [str(req["REQ-001"].id), str(req["REQ-002"].id)],
                          "explanation": "Both limit the same login flow differently."},
                    headers=headers_for(analyst)),
        client.put(url("requirements", req["REQ-010"].id, "protection"),
                   json={"protected": True, "reason": "Regulated"}, headers=headers_for(reviewer)),
        client.post(url("requirements", req["REQ-040"].id, "links"),
                    json={"target_id": str(req["REQ-041"].id), "kind": "refines"},
                    headers=headers_for(analyst)),
    ]  # fmt: skip
    assert [s.status_code for s in steps] == [200, 201, 200, 201], [s.text for s in steps]

    deltas = [json.loads(e.model_dump_json()) for e in events.published if e.type == GRAPH_DELTA]
    written = db_session.scalars(
        select(GraphEvent)
        .where(GraphEvent.project_id == project.id)
        .order_by(GraphEvent.created_at)
    ).all()
    with_sentences = [d["data"] for d in deltas if d["data"]["sentences"]]
    assert [s for d in with_sentences for s in d["sentences"]] == [r.sentence for r in written]
    for delta in with_sentences:
        rows = [r for r in written if r.revision == delta["to_revision"]]
        assert [r.sentence for r in rows] == delta["sentences"]
    # A raised concern also opens its issue (US-56): two sentences, two kinds.
    assert [r.kind for r in written] == ["conflict_resolved", "concern", "issue", "state", "link"]
    assert str(conflict.id) in written[0].edge_ids
    assert {str(req["REQ-021"].id), str(req["REQ-023"].id)} <= set(written[0].node_ids)
    assert set(written[4].node_ids) == {str(req["REQ-040"].id), str(req["REQ-041"].id)}
    assert all("shall" not in r.sentence.lower() for r in written)  # IDs and names, never text


def test_a_summary_counts_what_the_database_holds(
    client: TestClient,
    db_session: Session,
    planted: Planted,
    make_user: Callable[..., User],
    events: bus.InProcessEventBus,
) -> None:
    analyst = make_user(role=DefaultRole.BUSINESS_ANALYST)
    protected = {r.id for r in planted.by_label.values() if r.is_protected}
    conflicts = [
        finding
        for labels, finding in planted.findings.items()
        if finding.category is FindingCategory.CONFLICTING
        and not {planted.by_label[label].id for label in labels} & protected
    ]
    for finding in conflicts[:3]:  # a protected one would need a compliance reviewer
        response = client.post(url("findings", finding.id, "review"),
                               json={"action": "dismiss", "reason": "Not a conflict"},
                               headers=headers_for(analyst))  # fmt: skip
        assert response.status_code == 200, response.text

    result = changelog.summary(db_session, planted.project.id, since=None, since_label="start")

    dismissed = db_session.scalars(
        select(Finding).where(
            Finding.project_id == planted.project.id,
            Finding.category == FindingCategory.CONFLICTING,
            Finding.status == FindingStatus.DISMISSED,
        )
    ).all()
    assert result.counts["conflicts_resolved"] == len(dismissed) == 3
    assert result.total_events == 3
