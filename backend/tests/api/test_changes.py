"""Change log, summary, time slider and preview routes (Dhavni — US-55, US-50)."""

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.permissions import DefaultRole
from app.graph import deltas
from app.models import (
    CandidatePair,
    ChangeRequest,
    ConsequenceReport,
    Finding,
    FindingCategory,
    Project,
    Requirement,
    RequirementState,
    User,
    Workspace,
)
from app.realtime import bus
from tests.analysis_helpers import make_post
from tests.api.conftest import headers_for


@pytest.fixture(autouse=True)
def quiet_bus(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    test_bus = bus.InProcessEventBus()
    monkeypatch.setattr(bus, "get_bus", lambda: test_bus)
    yield


def url(*parts: object) -> str:
    return "/api/v1/" + "/".join(str(p) for p in parts)


def log(db: Session, project: Project, user: User, requirement: Requirement, sentence: str,
        kind: str, counts: dict[str, int] | None = None) -> None:  # fmt: skip
    change = deltas.Change(
        requirements={requirement.id}, sentences=[sentence], kind=kind, counts=counts or {}
    )
    deltas.publish(db, project.id, change, actor=user)


def test_the_log_lists_sentences_newest_first_with_filters_and_paging(
    client: TestClient, db_session: Session, project: Project, user: User
) -> None:
    a = make_post(db_session, project, user, "a", label="REQ-1")
    b = make_post(db_session, project, user, "b", label="REQ-2")
    log(db_session, project, user, a, "First.", kind="added")
    log(db_session, project, user, b, "Second.", kind="state")
    log(db_session, project, user, a, "Third.", kind="owner")
    headers = headers_for(user)

    page = client.get(url("projects", project.id, "changes"), params={"limit": 2},
                      headers=headers).json()  # fmt: skip
    assert [i["sentence"] for i in page["items"]] == ["Third.", "Second."]
    assert page["items"][0]["actor_name"] == "Test User"
    older = client.get(url("projects", project.id, "changes"),
                       params={"before": page["next_before"]}, headers=headers).json()  # fmt: skip
    assert [i["sentence"] for i in older["items"]] == ["First."] and older["next_before"] is None

    by_node = client.get(url("projects", project.id, "changes"),
                         params={"requirement": str(a.id)}, headers=headers).json()  # fmt: skip
    assert [i["sentence"] for i in by_node["items"]] == ["Third.", "First."]
    by_kind = client.get(url("projects", project.id, "changes"),
                         params=[("kind", "state"), ("kind", "added")], headers=headers).json()  # fmt: skip
    assert [i["sentence"] for i in by_kind["items"]] == ["Second.", "First."]


def test_summary_since_a_baseline_and_since_my_last_visit(
    client: TestClient,
    db_session: Session,
    project: Project,
    make_user: Callable[..., User],
) -> None:
    ba = make_user(role=DefaultRole.BUSINESS_ANALYST)
    headers = headers_for(ba)
    a = make_post(db_session, project, ba, "a", label="REQ-1", state=RequirementState.APPROVED)
    log(db_session, project, ba, a, "Before the baseline.", kind="added",
        counts={"requirements_added": 1})  # fmt: skip
    baseline = client.post(url("projects", project.id, "baselines"), json={"label": "v1.0"},
                           headers=headers).json()  # fmt: skip
    seen = client.put(url("projects", project.id, "changes", "seen"), headers=headers).json()
    assert seen["previous"] is None
    log(db_session, project, ba, a, "Ba merged RCR-1: REQ-1 is now v2.", kind="merged",
        counts={"change_requests_merged": 1, "requirements_changed": 1})  # fmt: skip

    since_v1 = client.get(url("projects", project.id, "changes", "summary"),
                          params={"since_baseline_id": baseline["id"]}, headers=headers).json()  # fmt: skip
    assert since_v1["since_label"] == "v1.0"
    assert since_v1["counts"]["change_requests_merged"] == 1
    assert since_v1["counts"]["requirements_added"] == 0
    assert since_v1["count_lines"] == ["1 requirement changed", "1 change request merged"]
    assert since_v1["narrative"] is None  # the AI paragraph is opt-in (Keval)

    since_visit = client.get(url("projects", project.id, "changes", "summary"),
                             params={"since_last_visit": "true"}, headers=headers).json()  # fmt: skip
    assert since_visit["since_label"] == "your last visit"
    assert since_visit["total_events"] == 1

    everything = client.get(url("projects", project.id, "changes", "summary"),
                            headers=headers).json()  # fmt: skip
    assert everything["counts"]["requirements_added"] == 1

    both = client.get(url("projects", project.id, "changes", "summary"),
                      params={"since_last_visit": "true", "since_baseline_id": baseline["id"]},
                      headers=headers)  # fmt: skip
    assert (both.status_code, both.json()["error"]["code"]) == (400, "one_start")


def test_a_baseline_of_another_project_is_404_as_a_summary_start(
    client: TestClient, db_session: Session, project: Project, user: User,
    make_project: Callable[..., Project],
) -> None:  # fmt: skip
    other = make_project()
    ba = headers_for(user)
    baseline = client.post(url("projects", other.id, "baselines"), json={"label": "x"},
                           headers=ba).json()  # fmt: skip
    response = client.get(url("projects", project.id, "changes", "summary"),
                          params={"since_baseline_id": baseline["id"]}, headers=ba)  # fmt: skip
    assert response.status_code == 404


def test_the_time_slider_shows_a_frozen_baseline_read_only(
    client: TestClient, db_session: Session, project: Project, user: User,
    make_requirement: Callable[..., Requirement],
) -> None:  # fmt: skip
    make_requirement("x", source_req_id="REQ-1", state=RequirementState.APPROVED)
    headers = headers_for(user)
    client.post(url("projects", project.id, "baselines"), json={"label": "v1.0"}, headers=headers)
    make_requirement("y", source_req_id="REQ-2")  # added after the freeze

    points = client.get(url("projects", project.id, "graph", "revisions"), headers=headers).json()
    assert [(p["label"], p["kind"]) for p in points] == [("v1.0", "baseline"), ("Now", "now")]
    frozen = client.get(url("projects", project.id, "graph", "revisions", points[0]["id"]),
                        headers=headers).json()  # fmt: skip
    assert frozen["read_only"] is True and frozen["label"] == "v1.0"
    assert [n["label"] for n in frozen["nodes"]] == ["REQ-1"]


def test_the_preview_fades_resolved_edges_and_glows_new_ones(
    client: TestClient, db_session: Session, project: Project, user: User,
    make_requirement: Callable[..., Requirement],
) -> None:  # fmt: skip
    a = make_requirement("Sessions end after 30 minutes.", source_req_id="REQ-1")
    b = make_requirement("Sessions end after 5 minutes.", source_req_id="REQ-2")
    c = make_requirement("Tokens last 10 minutes.", source_req_id="REQ-3")
    first, second = CandidatePair.ordered(a.id, b.id)
    pair = CandidatePair(requirement_a_id=first, requirement_b_id=second, similarity_score=0.9)
    db_session.add(pair)
    db_session.flush()
    finding = Finding(project_id=project.id, candidate_pair_id=pair.id,
                      category=FindingCategory.CONFLICTING, confidence=0.9, rationale="r",
                      original_ai_output={})  # fmt: skip
    change_request = ChangeRequest(project_id=project.id, requirement_id=a.id, number=1,
                                   proposer_id=user.id, base_version=1,
                                   proposed_body="Sessions end after 5 minutes.", reason="Align")  # fmt: skip
    db_session.add_all([finding, change_request])
    db_session.flush()
    headers = headers_for(user)

    pending = client.get(url("change-requests", change_request.id, "graph-preview"),
                         headers=headers).json()  # fmt: skip
    assert pending["checks_pending"] is True

    db_session.add(
        ConsequenceReport(
            change_request_id=change_request.id,
            proposal_revision=1,
            base_version=1,
            baseline_revision=0,
            affected=[{"requirement_id": str(b.id)}],
            findings_delta={
                "resolved": [
                    {
                        "finding_id": str(finding.id),
                        "category": "Conflicting",
                        "requirement_ids": [str(a.id), str(b.id)],
                    }
                ],
                "new": [
                    {
                        "finding_id": None,
                        "category": "Duplicate",
                        "requirement_ids": [str(a.id), str(c.id)],
                        "labels": ["REQ-1", "REQ-3"],
                        "reason": "Both limit the session",
                    }
                ],
                "still_open": [],
                "must_rerun": [],
            },
        )  # fmt: skip
    )
    db_session.commit()

    body = client.get(url("change-requests", change_request.id, "graph-preview"),
                      headers=headers).json()  # fmt: skip
    assert body["checks_pending"] is False and body["stale"] == []
    assert body["fading_edge_ids"] == [str(finding.id)]
    assert [(g["source"], g["target"], g["kind"]) for g in body["glowing_edges"]] == [
        (str(a.id), str(c.id), "duplicate")
    ]
    assert body["affected_node_ids"] == [str(b.id)]
    assert body["sentences"] == [
        "Merging RCR-1 would resolve 1 conflict and add 1 possible duplicate."
    ]


def test_another_workspace_sees_none_of_it(
    client: TestClient,
    project: Project,
    make_user: Callable[..., User],
    make_workspace: Callable[..., Workspace],
) -> None:
    outsider = headers_for(make_user(role=DefaultRole.OWNER, workspace=make_workspace()))
    for path in (("changes",), ("changes", "summary"), ("graph", "revisions")):
        assert client.get(url("projects", project.id, *path), headers=outsider).status_code == 404
    assert client.put(url("projects", project.id, "changes", "seen"),
                      headers=outsider).status_code == 404  # fmt: skip
