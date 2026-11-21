"""The updated SRS (Bansil — US-61, US-41; FR-106, FR-107, DR-25, NFR-38)."""

import io
import json
import uuid
from collections.abc import Callable, Iterator

import pymupdf
import pytest
from docx import Document as DocxDocument
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.classification.llm_client import FakeTransport, LLMClient
from app.classification.srs_sections import NARRATIVE_SECTIONS
from app.core.permissions import DefaultRole
from app.models import (
    AuditLog,
    ChangeRequest,
    Finding,
    FindingCategory,
    Project,
    Requirement,
    RequirementState,
    Severity,
    User,
    Workspace,
)
from app.models.srs import SrsDocument, SrsSection
from app.realtime import bus
from app.realtime.events import SRS_DRAFT_READY, SRS_SECTION_READY
from app.srs import generator
from tests.api.conftest import headers_for

APPROVED = RequirementState.APPROVED


@pytest.fixture
def events(monkeypatch: pytest.MonkeyPatch) -> Iterator[bus.InProcessEventBus]:
    test_bus = bus.InProcessEventBus()
    monkeypatch.setattr(bus, "get_bus", lambda: test_bus)
    yield test_bus


@pytest.fixture
def manager(make_user: Callable[..., User]) -> User:
    return make_user(role=DefaultRole.PROJECT_MANAGER)


@pytest.fixture
def baseline(make_requirement: Callable[..., Requirement]) -> list[Requirement]:
    return [
        make_requirement("Users shall sign in with the clinic SSO.", source_req_id="REQ-1",
                         state=APPROVED, req_type="functional", priority="must",
                         stakeholder_group="Patients"),
        make_requirement("Pages shall load within 2 seconds for 95% of requests.",
                         source_req_id="REQ-2", state=RequirementState.IMPLEMENTED,
                         req_type="non_functional"),
        make_requirement("Records are kept for 7 years under the retention law.",
                         source_req_id="REQ-3", state=APPROVED, req_type="constraint"),
    ]  # fmt: skip


def url(*parts: object) -> str:
    return "/api/v1/" + "/".join(str(p) for p in parts)


def replies(body: str = "The clinic portal lets patients book visits.") -> list[str]:
    return [json.dumps({"body": body, "cited_ids": []}) for _ in NARRATIVE_SECTIONS]


def start(client: TestClient, project: Project, user: User, **body: object) -> dict[str, object]:
    response = client.post(url("projects", project.id, "srs"), json=body, headers=headers_for(user))
    assert response.status_code == 201, response.text
    result: dict[str, object] = response.json()
    return result


def written(db: Session, srs_id: object, llm: LLMClient | None) -> None:
    generator.generate(db, uuid.UUID(str(srs_id)), llm)


def accept_all(client: TestClient, srs_id: object, user: User) -> None:
    detail = client.get(url("srs", srs_id), headers=headers_for(user)).json()
    for section in detail["sections"]:
        if section["status"] == "pending":
            response = client.patch(url("srs", srs_id, "sections", section["key"]),
                                    json={"action": "accept"}, headers=headers_for(user))  # fmt: skip
            assert response.status_code == 200, response.text


# ── readiness ───────────────────────────────────────────────────────────────────────────────
def test_readiness_blocks_on_open_items_and_a_manager_may_override_with_a_reason(
    client: TestClient, db_session: Session, project: Project, user: User, manager: User,
    baseline: list[Requirement],
) -> None:  # fmt: skip
    finding = Finding(project_id=project.id, requirement_id=baseline[0].id,
                      category=FindingCategory.AMBIGUOUS, confidence=0.8, rationale="r",
                      original_ai_output={}, severity=Severity.HIGH)  # fmt: skip
    change = ChangeRequest(project_id=project.id, requirement_id=baseline[1].id, number=1,
                           proposer_id=user.id, base_version=1, proposed_body="x", reason="r")  # fmt: skip
    db_session.add_all([finding, change])
    db_session.commit()

    check = client.get(
        url("projects", project.id, "srs", "readiness"), headers=headers_for(user)
    ).json()
    assert check["ready"] is False and check["requirements"] == 3
    blocking = {c["key"]: c for c in check["checks"] if not c["ok"]}
    assert set(blocking) == {"high_findings", "open_change_requests"}
    assert blocking["open_change_requests"]["links"] == [
        {"type": "change_request", "id": str(change.id), "key": "RCR-1"}
    ]

    refused = client.post(url("projects", project.id, "srs"), json={}, headers=headers_for(user))
    assert (refused.status_code, refused.json()["error"]["code"]) == (409, "not_ready")
    analyst = client.post(url("projects", project.id, "srs"), json={"override_reason": "Demo"},
                          headers=headers_for(user))  # fmt: skip
    assert analyst.status_code == 403  # only srs.publish holders override
    draft = start(client, project, manager, override_reason="Client review needs it today")
    assert draft["override_reason"] == "Client review needs it today"
    keys = [s["key"] for s in draft["sections"]]  # type: ignore[index]
    assert keys[-1] == "B_open_items"  # the open-items report is attached


# ── generation and review ───────────────────────────────────────────────────────────────────
def test_the_system_inserts_requirements_verbatim_and_the_llm_writes_only_narrative(
    client: TestClient, db_session: Session, project: Project, user: User,
    baseline: list[Requirement], events: bus.InProcessEventBus,
    followups: list[tuple[str, list[str]]],
) -> None:  # fmt: skip
    draft = start(client, project, user)
    assert (generator.GENERATE, [draft["id"]]) in followups
    sections = {s["key"]: s for s in draft["sections"]}  # type: ignore[union-attr, index]
    functional = sections["3.1_functional"]
    assert functional["locked"] and functional["status"] == "accepted"
    assert "**REQ-1** · Priority: Must · Owner: unassigned · Version 1" in functional["body"]
    assert "> Users shall sign in with the clinic SSO." in functional["body"]
    assert "#### Patients" in functional["body"]

    transport = FakeTransport(replies())
    written(db_session, draft["id"], LLMClient(transport, None))

    assert len(transport.calls) == len(NARRATIVE_SECTIONS)  # about one call per section
    for _system, user_prompt in transport.calls:
        assert "Users shall sign in" not in user_prompt  # requirement text never goes to the LLM
    detail = client.get(url("srs", draft["id"]), headers=headers_for(user)).json()
    purpose = next(s for s in detail["sections"] if s["key"] == "1.1_purpose")
    assert (purpose["source"], purpose["status"], purpose["ai_pending"]) == ("llm", "pending", True)
    assert detail["status"] == "draft" and detail["llm_calls"] == len(NARRATIVE_SECTIONS)
    types = [e.type for e in events.published]
    assert types.count(SRS_SECTION_READY) == len(NARRATIVE_SECTIONS) + 1  # + 1.4 references
    assert types[-1] == SRS_DRAFT_READY


def test_without_a_model_every_narrative_section_gets_template_text(
    client: TestClient, db_session: Session, project: Project, user: User,
    baseline: list[Requirement],
) -> None:  # fmt: skip
    draft = start(client, project, user)
    written(db_session, draft["id"], None)
    detail = client.get(url("srs", draft["id"]), headers=headers_for(user)).json()
    scope = next(s for s in detail["sections"] if s["key"] == "1.2_scope")
    assert scope["source"] == "template" and "[To be written" in scope["body"]
    assert scope["note"] == "Template text: no AI model is configured."


def test_sections_are_accepted_edited_or_regenerated_and_requirements_are_locked(
    client: TestClient, db_session: Session, project: Project, user: User,
    baseline: list[Requirement], followups: list[tuple[str, list[str]]],
    make_user: Callable[..., User],
) -> None:  # fmt: skip
    draft = start(client, project, user)
    written(db_session, draft["id"], LLMClient(FakeTransport(replies())))
    path = lambda key: url("srs", draft["id"], "sections", key)  # noqa: E731

    locked = client.patch(path("3.1_functional"), json={"action": "edit", "body": "x"},
                          headers=headers_for(user))  # fmt: skip
    assert (locked.status_code, locked.json()["error"]["code"]) == (409, "locked")
    edited = client.patch(path("1.2_scope"), json={"action": "edit", "body": "Booking only."},
                          headers=headers_for(user)).json()  # fmt: skip
    scope = next(s for s in edited["sections"] if s["key"] == "1.2_scope")
    assert (scope["source"], scope["status"], scope["ai_pending"]) == ("edited", "accepted", False)
    again = client.patch(path("1.1_purpose"),
                         json={"action": "regenerate", "instruction": "Shorter, for the client"},
                         headers=headers_for(user)).json()  # fmt: skip
    purpose = next(s for s in again["sections"] if s["key"] == "1.1_purpose")
    assert (purpose["status"], purpose["regenerations"]) == ("generating", 1)
    assert (generator.REGENERATE, [draft["id"], "1.1_purpose"]) in followups
    viewer = headers_for(make_user(role=DefaultRole.VIEWER))
    denied = client.patch(path("1.3_definitions"), json={"action": "accept"}, headers=viewer)
    assert denied.status_code == 403  # srs.generate is needed to review


# ── fidelity, publishing, immutability ──────────────────────────────────────────────────────
def test_fidelity_lists_failures_in_words_and_blocks_publishing(
    client: TestClient, db_session: Session, project: Project, user: User, manager: User,
    baseline: list[Requirement], make_requirement: Callable[..., Requirement],
) -> None:  # fmt: skip
    make_requirement("Patients may cancel a visit up to 24 hours before it starts.",
                     source_req_id="REQ-9")  # a Proposed requirement  # fmt: skip
    draft = start(client, project, user)
    written(db_session, draft["id"], LLMClient(FakeTransport(replies())))
    sections = db_session.scalars(select(SrsSection).where(SrsSection.srs_id == draft["id"])).all()
    functional = next(s for s in sections if s.key == "3.1_functional")
    functional.body = functional.body.replace("> Users shall sign in with the clinic SSO.", "")
    db_session.commit()
    client.patch(url("srs", draft["id"], "sections", "1.2_scope"),
                 json={"action": "edit", "body": "Patients may cancel a visit up to 24 hours "
                       "before it starts. The portal must be friendly."},
                 headers=headers_for(user))  # fmt: skip
    accept_all(client, draft["id"], user)

    early = client.post(url("srs", draft["id"], "publish"), headers=headers_for(manager))
    assert early.json()["error"]["code"] == "fidelity_required"
    report = client.post(url("srs", draft["id"], "fidelity"), headers=headers_for(user)).json()

    assert report["passed"] is False
    messages = {f["message"] for f in report["failures"]}
    assert "REQ-1 missing" in messages
    assert any("REQ-9" in m and "Proposed" in m for m in messages)
    assert any("'must' sentence" in m for m in messages)


def test_a_clean_draft_is_published_as_v1_0_immutable_then_v1_1_compares_with_it(
    client: TestClient, db_session: Session, project: Project, user: User, manager: User,
    baseline: list[Requirement],
) -> None:  # fmt: skip
    draft = start(client, project, user)
    written(db_session, draft["id"], LLMClient(FakeTransport(replies())))
    accept_all(client, draft["id"], user)
    assert client.post(url("srs", draft["id"], "fidelity"), headers=headers_for(user)).json()[
        "passed"
    ]
    assert (
        client.post(url("srs", draft["id"], "publish"), headers=headers_for(user)).status_code
        == 403
    )

    published = client.post(url("srs", draft["id"], "publish"), headers=headers_for(manager)).json()

    assert (published["status"], published["version_label"]) == ("published", "v1.0")
    assert published["fidelity"]["excluded"]["proposed_requirements"] == 0
    assert db_session.scalars(select(AuditLog).where(AuditLog.action == "srs_published")).one()
    for statement in ("UPDATE srs_documents SET status = 'draft'", "UPDATE srs_sections SET body = 'x'",
                      "DELETE FROM srs_sections"):  # fmt: skip
        with pytest.raises(DBAPIError, match="immutable"), db_session.begin_nested():
            db_session.execute(text(statement))
    again = client.patch(url("srs", draft["id"], "sections", "1.1_purpose"),
                         json={"action": "accept"}, headers=headers_for(user))  # fmt: skip
    assert again.json()["error"]["code"] == "not_a_draft"

    baseline[0].body, baseline[0].current_version = "Users shall sign in with SSO or a passkey.", 2
    db_session.commit()
    second = start(client, project, user)
    written(db_session, second["id"], LLMClient(FakeTransport(replies("A newer purpose."))))
    accept_all(client, second["id"], user)
    client.post(url("srs", second["id"], "fidelity"), headers=headers_for(user))
    v11 = client.post(url("srs", second["id"], "publish"), headers=headers_for(manager)).json()
    assert v11["version_label"] == "v1.1"

    diff = client.get(
        url("srs", draft["id"], "compare", second["id"]), headers=headers_for(user)
    ).json()
    assert [c["label"] for c in diff["requirements"]["changed"]] == ["REQ-1"]
    purpose = next(s for s in diff["sections"] if s["key"] == "1.1_purpose")
    assert purpose["change"] == "changed" and purpose["after"] == "A newer purpose."
    listed = client.get(url("projects", project.id, "srs"), headers=headers_for(user)).json()
    assert [d["version_label"] for d in listed] == ["v1.1", "v1.0"]


def test_a_published_srs_exports_as_markdown_docx_and_pdf_with_the_exclusion_note(
    client: TestClient, db_session: Session, project: Project, user: User, manager: User,
    baseline: list[Requirement], make_requirement: Callable[..., Requirement],
) -> None:  # fmt: skip
    make_requirement("Proposed thing that is not approved yet at all.", source_req_id="REQ-8")
    draft = start(client, project, user)
    written(db_session, draft["id"], LLMClient(FakeTransport(replies())))
    accept_all(client, draft["id"], user)
    early = client.get(url("srs", draft["id"], "export"), params={"format": "pdf"},
                       headers=headers_for(user))  # fmt: skip
    assert early.json()["error"]["code"] == "not_published"
    client.post(url("srs", draft["id"], "fidelity"), headers=headers_for(user))
    client.post(url("srs", draft["id"], "publish"), headers=headers_for(manager))

    md = client.get(url("srs", draft["id"], "export"), headers=headers_for(user))
    assert md.headers["content-type"].startswith("text/markdown")
    assert "**SRS v1.0** · Baseline revision 0" in md.text
    assert "Not included: 1 proposed requirement" in md.text
    assert "> Records are kept for 7 years under the retention law." in md.text
    assert "Proposed thing" not in md.text
    docx = client.get(url("srs", draft["id"], "export"), params={"format": "docx"},
                      headers=headers_for(user))  # fmt: skip
    paragraphs = [p.text for p in DocxDocument(io.BytesIO(docx.content)).paragraphs]
    assert "Records are kept for 7 years under the retention law." in paragraphs
    pdf = client.get(url("srs", draft["id"], "export"), params={"format": "pdf"},
                     headers=headers_for(user))  # fmt: skip
    pages = " ".join(p.get_text() for p in pymupdf.open(stream=pdf.content, filetype="pdf"))
    assert "Pages shall load within 2 seconds for 95% of requests." in " ".join(pages.split())


def test_one_draft_at_a_time_and_another_workspace_sees_nothing(
    client: TestClient, db_session: Session, project: Project, user: User,
    baseline: list[Requirement], make_user: Callable[..., User],
    make_workspace: Callable[..., Workspace],
) -> None:  # fmt: skip
    draft = start(client, project, user)
    second = client.post(url("projects", project.id, "srs"), json={}, headers=headers_for(user))
    assert (second.status_code, second.json()["error"]["code"]) == (409, "draft_open")
    developer = client.post(url("srs", draft["id"], "discard"),
                            headers=headers_for(make_user(role=DefaultRole.DEVELOPER)))  # fmt: skip
    assert developer.status_code == 403
    outsider = headers_for(make_user(role=DefaultRole.OWNER, workspace=make_workspace()))
    assert client.get(url("srs", draft["id"]), headers=outsider).status_code == 404
    assert client.get(url("projects", project.id, "srs"), headers=outsider).status_code == 404
    assert (
        client.post(url("srs", draft["id"], "discard"), headers=headers_for(user)).json()["status"]
        == "discarded"
    )
    assert db_session.get(SrsDocument, draft["id"]) is not None
