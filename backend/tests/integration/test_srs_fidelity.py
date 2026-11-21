"""SRS fidelity on the planted benchmark (Abhyudit — US-61, DR-25, Sprint 6 regression).

The 60 approved requirements of ``eval/benchmark_v2/srs_planted.md`` go through the whole updated
SRS path — readiness, draft, narrative (scripted replies), review, fidelity, publish, export — and
every baseline requirement appears **exactly once and verbatim** in the published document, in
Markdown and in DOCX; no Proposed text appears; and the fidelity check catches a narrative that
copies a Proposed requirement or states a "shall" of its own.
"""

import io
import json
import uuid
from collections.abc import Callable

import pytest
from docx import Document as DocxDocument
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.classification.llm_client import FakeTransport, LLMClient
from app.classification.srs_sections import NARRATIVE_SECTIONS
from app.core.permissions import DefaultRole
from app.models import Project, Requirement, RequirementOrigin, RequirementState, User
from app.models.srs import SrsSection
from app.srs import generator
from tests.api.conftest import headers_for
from tests.integration.planted import Planted, load, scripted, statements

PROPOSED = "The portal shall let auditors download every document as a ZIP archive overnight."


@pytest.fixture
def planted(db_session: Session, project: Project, make_user: Callable[..., User]) -> Planted:
    owners: dict[str, User] = {}
    for name in scripted()["owners"]:
        user = make_user(role=DefaultRole.BUSINESS_ANALYST)
        user.full_name = name
        owners[name] = user
    db_session.commit()
    planted = load(db_session, project, owners)
    db_session.add(Requirement(project_id=project.id, origin=RequirementOrigin.POST, body=PROPOSED,
                               source_req_id="REQ-099", state=RequirementState.PROPOSED))  # fmt: skip
    db_session.commit()
    return planted


def url(*parts: object) -> str:
    return "/api/v1/" + "/".join(str(p) for p in parts)


def _draft(client: TestClient, db: Session, project: Project, user: User) -> str:
    response = client.post(url("projects", project.id, "srs"), json={}, headers=headers_for(user))
    assert response.status_code == 201, response.text
    srs_id = response.json()["id"]
    narrative = [json.dumps({"body": "This specification covers SecureDocs.", "cited_ids": []})
                 for _ in NARRATIVE_SECTIONS]  # fmt: skip
    generator.generate(db, uuid.UUID(srs_id), LLMClient(FakeTransport(narrative)))
    return str(srs_id)


def _accept_all(client: TestClient, srs_id: str, user: User) -> None:
    for section in client.get(url("srs", srs_id), headers=headers_for(user)).json()["sections"]:
        if section["status"] == "pending":
            client.patch(url("srs", srs_id, "sections", section["key"]), json={"action": "accept"},
                         headers=headers_for(user))  # fmt: skip


def test_every_baseline_requirement_is_published_once_and_verbatim(
    client: TestClient, db_session: Session, planted: Planted, make_user: Callable[..., User]
) -> None:
    analyst = make_user(role=DefaultRole.BUSINESS_ANALYST)
    manager = make_user(role=DefaultRole.PROJECT_MANAGER)
    texts = statements()
    readiness = client.get(url("projects", planted.project.id, "srs", "readiness"),
                           headers=headers_for(analyst)).json()  # fmt: skip
    assert readiness["requirements"] == len(texts) == 60

    srs_id = _draft(client, db_session, planted.project, analyst)
    _accept_all(client, srs_id, analyst)
    report = client.post(url("srs", srs_id, "fidelity"), headers=headers_for(analyst)).json()
    assert report["passed"], report["failures"]
    assert report["requirements_checked"] == 60
    published = client.post(url("srs", srs_id, "publish"), headers=headers_for(manager)).json()
    assert published["version_label"] == "v1.0"

    markdown = client.get(url("srs", srs_id, "export"), headers=headers_for(analyst)).text
    quoted = [line[2:] for line in markdown.splitlines() if line.startswith("> ")]
    for label, body in texts.items():
        assert quoted.count(body) == 1, (label, quoted.count(body))
        assert markdown.count(f"**{label}**") == 1, label
    assert PROPOSED not in markdown and "REQ-099" not in markdown
    docx = client.get(url("srs", srs_id, "export"), params={"format": "docx"},
                      headers=headers_for(analyst))  # fmt: skip
    paragraphs = [p.text for p in DocxDocument(io.BytesIO(docx.content)).paragraphs]
    for body in texts.values():
        assert paragraphs.count(body) == 1, body


def test_the_check_catches_proposed_text_and_a_shall_of_its_own(
    client: TestClient, db_session: Session, planted: Planted, make_user: Callable[..., User]
) -> None:
    analyst = make_user(role=DefaultRole.BUSINESS_ANALYST)
    srs_id = _draft(client, db_session, planted.project, analyst)
    client.patch(url("srs", srs_id, "sections", "1.2_scope"),
                 json={"action": "edit", "body": f"In scope: {PROPOSED}"},
                 headers=headers_for(analyst))  # fmt: skip
    client.patch(url("srs", srs_id, "sections", "2.5_assumptions"),
                 json={"action": "edit", "body": "Uploads must be scanned. See REQ-005 for limits."},
                 headers=headers_for(analyst))  # fmt: skip
    section = db_session.scalars(
        select(SrsSection).where(SrsSection.srs_id == srs_id, SrsSection.key == "3.1_functional")
    ).one()
    first = next(iter(statements().values()))
    duplicated = section.body + "\n\n" + "> " + first

    with db_session.begin_nested():
        section.body = duplicated  # a draft section, still mutable
    db_session.commit()

    report = client.post(url("srs", srs_id, "fidelity"), headers=headers_for(analyst)).json()
    codes = sorted({f["code"] for f in report["failures"]})
    assert report["passed"] is False
    assert codes == ["duplicated", "normative", "not_baseline"]
    assert any("REQ-099" in f["message"] for f in report["failures"])
