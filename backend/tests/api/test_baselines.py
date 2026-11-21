"""Baseline snapshots and comparison (Parth — US-40, FR-73, DR-08)."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.permissions import DefaultRole
from app.models import AuditLog, Project, Requirement, RequirementState, User, Workspace
from tests.api.conftest import headers_for


@pytest.fixture
def ba(make_user: Callable[..., User]) -> User:
    return make_user(role=DefaultRole.BUSINESS_ANALYST)


def url(*parts: object) -> str:
    return "/api/v1/" + "/".join(str(p) for p in parts)


def freeze(client: TestClient, project: Project, user: User, label: str) -> dict[str, object]:
    response = client.post(url("projects", project.id, "baselines"), json={"label": label},
                           headers=headers_for(user))  # fmt: skip
    assert response.status_code == 201, response.text
    body: dict[str, object] = response.json()
    return body


def test_v1_1_compared_with_v1_0(
    client: TestClient,
    db_session: Session,
    project: Project,
    ba: User,
    make_requirement: Callable[..., Requirement],
) -> None:
    approved = RequirementState.APPROVED
    kept = make_requirement("Sessions time out after 30 minutes.", source_req_id="REQ-1",
                            state=approved)  # fmt: skip
    changed = make_requirement("Statements are kept for 7 years.", source_req_id="REQ-2",
                               state=approved)  # fmt: skip
    dropped = make_requirement("Export as CSV.", source_req_id="REQ-3", state=approved)
    make_requirement("A proposal is not in the baseline.", source_req_id="REQ-4")
    v1 = freeze(client, project, ba, "v1.0")
    assert v1["requirement_count"] == 3

    changed.body, changed.current_version = "Statements are kept for 10 years.", 2
    dropped.state = RequirementState.DEPRECATED
    added = make_requirement("Export as PDF.", source_req_id="REQ-5", state=approved)
    db_session.commit()
    v11 = freeze(client, project, ba, "v1.1")

    diff = client.get(url("baselines", v1["id"], "compare", v11["id"]),
                      headers=headers_for(ba)).json()  # fmt: skip
    assert [a["label"] for a in diff["added"]] == ["REQ-5"] and diff["added"][0][
        "requirement_id"
    ] == str(added.id)
    assert [(c["label"], c["from_version"], c["to_version"]) for c in diff["changed"]] == [
        ("REQ-2", 1, 2)
    ]
    assert diff["changed"][0]["before"] == "Statements are kept for 7 years."
    assert diff["changed"][0]["after"] == "Statements are kept for 10 years."
    assert [(r["label"], r["state"]) for r in diff["removed"]] == [("REQ-3", "Deprecated")]
    assert diff["unchanged"] == 1
    assert kept.id  # still the same in both


def test_snapshots_are_immutable_and_audited(
    client: TestClient,
    db_session: Session,
    project: Project,
    ba: User,
    make_requirement: Callable[..., Requirement],
) -> None:
    make_requirement("x", state=RequirementState.APPROVED)
    baseline = freeze(client, project, ba, "v1.0")
    for statement in ("UPDATE baselines SET label = 'x'", "DELETE FROM baseline_items",
                      "UPDATE baseline_items SET body = 'y'"):  # fmt: skip
        with pytest.raises(DBAPIError, match="immutable"), db_session.begin_nested():
            db_session.execute(text(statement))
    audit = db_session.scalars(select(AuditLog).where(AuditLog.action == "baseline_frozen")).one()
    assert audit.details["baseline_id"] == baseline["id"]


def test_labels_are_unique_per_project(client: TestClient, project: Project, ba: User) -> None:
    freeze(client, project, ba, "v1.0")
    again = client.post(url("projects", project.id, "baselines"), json={"label": " v1.0 "},
                        headers=headers_for(ba))  # fmt: skip
    assert (again.status_code, again.json()["error"]["code"]) == (409, "label_taken")


def test_list_and_detail(
    client: TestClient, project: Project, ba: User, make_requirement: Callable[..., Requirement]
) -> None:
    make_requirement("The system shall log in.", source_req_id="REQ-1",
                     state=RequirementState.IMPLEMENTED)  # fmt: skip
    first = freeze(client, project, ba, "v1.0")
    freeze(client, project, ba, "v1.1")
    listed = client.get(url("projects", project.id, "baselines"), headers=headers_for(ba)).json()
    assert {b["label"] for b in listed} == {"v1.0", "v1.1"}
    detail = client.get(url("baselines", first["id"]), headers=headers_for(ba)).json()
    assert [(i["label"], i["version"], i["state"]) for i in detail["items"]] == [
        ("REQ-1", 1, "Implemented")
    ]


def test_freezing_needs_baseline_manage(
    client: TestClient, project: Project, make_user: Callable[..., User]
) -> None:
    developer = make_user(role=DefaultRole.DEVELOPER)
    response = client.post(url("projects", project.id, "baselines"), json={"label": "v1"},
                           headers=headers_for(developer))  # fmt: skip
    assert response.status_code == 403


def test_comparing_across_projects_or_workspaces_is_404(
    client: TestClient,
    project: Project,
    ba: User,
    make_project: Callable[..., Project],
    make_workspace: Callable[..., Workspace],
    make_user: Callable[..., User],
) -> None:
    mine = freeze(client, project, ba, "v1.0")
    other = freeze(client, make_project(), ba, "v1.0")
    assert client.get(url("baselines", mine["id"], "compare", other["id"]),
                      headers=headers_for(ba)).status_code == 404  # fmt: skip
    outsider = headers_for(make_user(role=DefaultRole.OWNER, workspace=make_workspace()))
    assert client.get(url("baselines", mine["id"]), headers=outsider).status_code == 404
    assert client.get(url("projects", project.id, "baselines"), headers=outsider).status_code == 404
