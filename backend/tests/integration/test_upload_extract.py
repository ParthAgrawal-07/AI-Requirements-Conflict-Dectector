"""Upload and extraction of the planted SRS through the API (Abhyudit — US-01, US-02, US-04).

Runs what a user does: upload ``eval/benchmark_v2/srs_planted.docx`` to a project, let the worker
process it (called in-process here instead of through Celery), then list the requirements. Checks
the Sprint 1 exit conditions: the expected count within 5%, printed IDs kept, and every labelled ID
present — plus the access rules of the two endpoints.

Skipped when ``eval/`` is not reachable (e.g. only ``backend/`` is mounted in the container).
"""

import csv
import os
import re
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core import security
from app.core.permissions import DefaultRole
from app.models import Project, User
from app.services import documents as document_service
from app.services.processing import ProcessingOutcome, process_document
from app.services.storage import LocalFileStorage, get_storage

REPO_ROOT = Path(__file__).resolve().parents[3]
TOLERANCE = 0.05


def _benchmark_dir() -> Path:
    for base in (os.environ.get("EVAL_DIR"), "/eval", str(REPO_ROOT / "eval")):
        if base and (Path(base) / "benchmark_v2" / "srs_planted.docx").is_file():
            return Path(base) / "benchmark_v2"
    pytest.skip("eval/benchmark_v2/srs_planted.docx is not reachable from this environment")


@pytest.fixture(scope="module")
def benchmark() -> Path:
    return _benchmark_dir()


@pytest.fixture
def storage(tmp_path: Path) -> LocalFileStorage:
    return LocalFileStorage(tmp_path / "uploads")


@pytest.fixture
def api(
    client: TestClient, storage: LocalFileStorage, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    from app.main import app

    monkeypatch.setattr(document_service, "dispatch_processing", lambda _id: "task-1")
    app.dependency_overrides[get_storage] = lambda: storage
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_storage, None)


def _headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {security.create_access_token(user.id)[0]}"}


@pytest.fixture
def uploaded(
    api: TestClient,
    db_session: Session,
    storage: LocalFileStorage,
    project: Project,
    make_user: Callable[..., User],
    benchmark: Path,
) -> list[dict[str, object]]:
    """The planted SRS uploaded by a Developer as proposals, processed, and listed."""
    developer = _headers(make_user(role=DefaultRole.DEVELOPER))
    with (benchmark / "srs_planted.docx").open("rb") as handle:
        response = api.post(
            f"/api/v1/projects/{project.id}/documents",
            files={"file": ("srs_planted.docx", handle, "application/octet-stream")},
            headers=developer,
        )
    assert response.status_code == 202, response.text
    document_id = uuid.UUID(response.json()["document_id"])

    assert process_document(db_session, document_id, storage=storage) is ProcessingOutcome.DONE

    listed = api.get(
        f"/api/v1/projects/{project.id}/requirements", params={"limit": 200}, headers=developer
    )
    assert listed.status_code == 200
    items: list[dict[str, object]] = listed.json()["items"]
    return items


def test_the_expected_number_of_requirements_is_extracted(
    uploaded: list[dict[str, object]], source_ids: set[str]
) -> None:
    expected = len(source_ids)
    # (keep your existing comment about flagged items here)
    confident = [item for item in uploaded if not item["needs_review"]]
    assert abs(len(confident) - expected) <= expected * TOLERANCE, len(confident)
    assert all(not item["source_req_id"] for item in uploaded if item["needs_review"])


def test_every_printed_id_is_kept_verbatim(
    uploaded: list[dict[str, object]], source_ids: set[str]
) -> None:
    printed = {item["source_req_id"] for item in uploaded if item["source_req_id"]}
    assert source_ids <= printed

def test_requirements_uploaded_as_proposals_are_proposed_documents(
    uploaded: list[dict[str, object]],
) -> None:
    by_id = {item["source_req_id"]: item for item in uploaded}
    assert by_id["REQ-014"]["state"] == "Proposed"
    assert by_id["REQ-014"]["origin"] == "document"
    assert by_id["REQ-014"]["body"] == (
        "REQ-014: Every unsuccessful login attempt shall be logged by the system."
    )


def test_table_rows_are_extracted_like_paragraphs(uploaded: list[dict[str, object]]) -> None:
    by_id = {item["source_req_id"]: item for item in uploaded}
    assert "REQ-049" in by_id and "recycle bin" in str(by_id["REQ-049"]["body"])


def test_headings_and_introduction_prose_are_not_requirements(
    uploaded: list[dict[str, object]],
) -> None:
    bodies = " ".join(str(item["body"]) for item in uploaded)
    assert "This document specifies the requirements of SecureDocs" not in bodies  # 1.1 Purpose


@pytest.mark.xfail(
    strict=True,
    reason="Bansil, Sprint 2: remove headings and prose from extraction (ingestion-design §12). "
    "Until then descriptive prose is kept and flagged for review.",
)
def test_descriptive_prose_and_lead_ins_are_not_extracted(
    uploaded: list[dict[str, object]],
) -> None:
    assert [item["body"] for item in uploaded if not item["source_req_id"]] == []


def test_every_labelled_id_exists_in_the_extraction(
    uploaded: list[dict[str, object]], benchmark: Path
) -> None:
    printed = {item["source_req_id"] for item in uploaded}
    with (benchmark / "labels.csv").open(encoding="utf-8") as handle:
        labelled = {
            req_id for row in csv.DictReader(handle) for req_id in (row["r1"], row["r2"]) if req_id
        }
    assert labelled <= printed, sorted(labelled - printed)


def test_a_viewer_cannot_upload_but_can_list(
    api: TestClient, project: Project, make_user: Callable[..., User], benchmark: Path
) -> None:
    viewer = _headers(make_user(role=DefaultRole.VIEWER))
    with (benchmark / "srs_planted.docx").open("rb") as handle:
        refused = api.post(
            f"/api/v1/projects/{project.id}/documents",
            files={"file": ("srs_planted.docx", handle, "application/octet-stream")},
            headers=viewer,
        )
    assert refused.status_code == 403
    assert api.get(f"/api/v1/projects/{project.id}/requirements", headers=viewer).status_code == 200


def test_another_workspaces_project_is_not_found(
    api: TestClient,
    make_project: Callable[..., Project],
    make_workspace: Callable[..., object],
    make_user: Callable[..., User],
    benchmark: Path,
) -> None:
    foreign = make_project(workspace=make_workspace())
    developer = _headers(make_user(role=DefaultRole.DEVELOPER))
    with (benchmark / "srs_planted.docx").open("rb") as handle:
        response = api.post(
            f"/api/v1/projects/{foreign.id}/documents",
            files={"file": ("srs_planted.docx", handle, "application/octet-stream")},
            headers=developer,
        )
    assert response.status_code == 404
    listed = api.get(f"/api/v1/projects/{foreign.id}/requirements", headers=developer)
    assert listed.status_code == 404

@pytest.fixture(scope="module")
def source_ids(benchmark: Path) -> set[str]:
    """Printed IDs in srs_planted.md: the one source of truth for the expected count."""
    text = (benchmark / "srs_planted.md").read_text(encoding="utf-8")
    return set(re.findall(r"REQ-\d{3}", text))
