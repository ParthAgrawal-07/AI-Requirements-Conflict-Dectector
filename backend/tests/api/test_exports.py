"""Template exports and the open-items report (Bansil — US-41, US-59, FR-74, FR-102, DR-22)."""

import io
from collections.abc import Callable

import pymupdf
from docx import Document as DocxDocument
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.permissions import DefaultRole
from app.models import (
    ChangeRequest,
    Finding,
    FindingCategory,
    Issue,
    IssueRequirement,
    Project,
    Requirement,
    RequirementState,
    RequirementTransition,
    Severity,
    User,
    Workspace,
)
from tests.api.conftest import headers_for


def url(*parts: object) -> str:
    return "/api/v1/" + "/".join(str(p) for p in parts)


def world(db: Session, project: Project, user: User,
          make_requirement: Callable[..., Requirement]) -> dict[str, Requirement]:  # fmt: skip
    approved = make_requirement("Users shall sign in with the clinic SSO.", source_req_id="REQ-1",
                                state=RequirementState.APPROVED, req_type="functional",
                                stakeholder_group="Patients")  # fmt: skip
    risky = make_requirement("Sessions end after 10 minutes of inactivity.", source_req_id="REQ-2",
                             state=RequirementState.APPROVED, req_type="non_functional")  # fmt: skip
    proposed = make_requirement("Patients may export their visit history as a PDF file.",
                                source_req_id="REQ-3")  # fmt: skip
    db.add_all(
        [
            Finding(project_id=project.id, requirement_id=risky.id,
                    category=FindingCategory.AMBIGUOUS, confidence=0.9, rationale="r",
                    original_ai_output={}, severity=Severity.HIGH),
            ChangeRequest(project_id=project.id, requirement_id=approved.id, number=4,
                          proposer_id=user.id, base_version=1, proposed_body="x", reason="r",
                          status="closed", close_reason="Superseded by RCR-5"),
            RequirementTransition(requirement_id=risky.id, from_state=RequirementState.UNDER_REVIEW,
                                  to_state=RequirementState.APPROVED, version=1, actor_id=user.id,
                                  reason="Pilot needs it; ambiguity tracked", accepted_risk=True),
        ]
    )  # fmt: skip
    issue = Issue(project_id=project.id, number=7, title="Session length", author_id=user.id)
    db.add(issue)
    db.flush()
    db.add(IssueRequirement(issue_id=issue.id, requirement_id=risky.id))
    db.commit()
    return {"approved": approved, "risky": risky, "proposed": proposed}


def test_the_template_export_holds_only_the_approved_baseline_and_says_what_it_left_out(
    client: TestClient, db_session: Session, project: Project, user: User,
    make_requirement: Callable[..., Requirement],
) -> None:  # fmt: skip
    world(db_session, project, user, make_requirement)
    baseline = client.post(url("projects", project.id, "baselines"), json={"label": "v1.0"},
                           headers=headers_for(user)).json()  # fmt: skip

    md = client.get(url("baselines", baseline["id"], "export"), params={"format": "md"},
                    headers=headers_for(user)).text  # fmt: skip

    assert "**Template export** · Baseline revision 0 (snapshot “v1.0”)" in md
    assert "Not included: 1 proposed requirement, 1 open finding and 1 open issue" in md
    assert "> Users shall sign in with the clinic SSO." in md
    assert "#### Patients" in md and "### 3.2 Non-functional requirements" in md
    assert "Patients may export" not in md  # DR-22: never a Proposed requirement
    assert "[To be written: the purpose of this specification.]" in md  # no confirmed brief

    docx = client.get(url("baselines", baseline["id"], "export"), headers=headers_for(user))
    assert docx.headers["content-type"].startswith("application/vnd.openxmlformats")
    texts = [p.text for p in DocxDocument(io.BytesIO(docx.content)).paragraphs]
    assert "Sessions end after 10 minutes of inactivity." in texts
    current = client.get(url("projects", project.id, "export"), params={"format": "pdf"},
                         headers=headers_for(user))  # fmt: skip
    text = " ".join(p.get_text() for p in pymupdf.open(stream=current.content, filetype="pdf"))
    assert "Users shall sign in with the clinic SSO." in " ".join(text.split())


def test_the_open_items_report_lists_everything_the_export_leaves_out(
    client: TestClient, db_session: Session, project: Project, user: User,
    make_requirement: Callable[..., Requirement],
) -> None:  # fmt: skip
    world(db_session, project, user, make_requirement)
    baseline = client.post(url("projects", project.id, "baselines"), json={"label": "v1.0"},
                           headers=headers_for(user)).json()  # fmt: skip

    data = client.get(url("baselines", baseline["id"], "open-items"), params={"format": "json"},
                      headers=headers_for(user)).json()  # fmt: skip

    assert data["baseline_label"] == "v1.0" and data["baseline_revision"] == 0
    assert data["counts"] == {"proposed_requirements": 1, "open_findings": 1,
                              "open_change_requests": 0, "open_issues": 1}  # fmt: skip
    assert [p["label"] for p in data["proposed"]] == ["REQ-3"]
    (finding,) = data["findings"]
    assert (finding["source"], finding["severity"], finding["requirements"]) == (
        "AI",
        "high",
        ["REQ-2"],
    )
    (issue,) = data["issues"]
    assert issue["key"] == "ISS-7"
    (closed,) = data["closed_change_requests"]
    assert (closed["key"], closed["reason"]) == ("RCR-4", "Superseded by RCR-5")
    (risk,) = data["accepted_risks"]
    assert risk["reason"] == "Pilot needs it; ambiguity tracked"

    md = client.get(url("projects", project.id, "open-items"), params={"format": "md"},
                    headers=headers_for(user)).text  # fmt: skip
    assert "# Open items" in md and "**not** part of the approved specification" in md
    assert "> Patients may export their visit history as a PDF file." in md
    pdf = client.get(url("baselines", baseline["id"], "open-items"), headers=headers_for(user))
    assert pdf.headers["content-type"] == "application/pdf"


def test_exports_stay_inside_the_workspace(
    client: TestClient, project: Project, user: User,
    make_user: Callable[..., User], make_workspace: Callable[..., Workspace],
) -> None:  # fmt: skip
    baseline = client.post(url("projects", project.id, "baselines"), json={"label": "v1"},
                           headers=headers_for(user)).json()  # fmt: skip
    viewer = headers_for(make_user(role=DefaultRole.VIEWER))
    assert client.get(url("baselines", baseline["id"], "export"), params={"format": "md"},
                      headers=viewer).status_code == 200  # fmt: skip
    outsider = headers_for(make_user(role=DefaultRole.OWNER, workspace=make_workspace()))
    for path in (("baselines", baseline["id"], "export"), ("baselines", baseline["id"], "open-items"),
                 ("projects", project.id, "export"), ("projects", project.id, "open-items")):  # fmt: skip
        assert client.get(url(*path), headers=outsider).status_code == 404
