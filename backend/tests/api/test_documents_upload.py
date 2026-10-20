"""POST /api/v1/projects/{p}/documents — US-01 acceptance criteria and failure atomicity."""

import uuid
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.permissions import DefaultRole, holders_of
from app.models import (
    AuditAction,
    AuditLog,
    Document,
    DocumentFormat,
    DocumentStatus,
    ImportMode,
    Project,
    ProjectStatus,
    User,
    Workspace,
)
from app.services import documents as document_service
from app.services.storage import LocalFileStorage
from tests.api.conftest import documents_url, headers_for, stored_files
from tests.factories import OLE_HEADER, make_docx, make_pdf, pad_pdf, unique_docx

# The project the helper below uploads into; bound per test by the autouse fixture so the many
# ``upload(api, ...)`` calls stay short. Tests that target another project pass ``project=``.
_CURRENT: dict[str, Project] = {}


@pytest.fixture(autouse=True)
def _bind_project(project: Project) -> Iterator[None]:
    _CURRENT["project"] = project
    yield
    _CURRENT.clear()


def upload(
    api: TestClient,
    data: bytes,
    name: str,
    headers: dict[str, str],
    mime: str = "application/octet-stream",
    *,
    project: Project | None = None,
    **form: str,
):
    return api.post(
        documents_url(project or _CURRENT["project"]),
        files={"file": (name, data, mime)},
        data=form,
        headers=headers,
    )


def document_count(db: Session) -> int:
    return db.scalar(select(func.count(Document.id))) or 0


class TestAccepted:
    def test_pdf_returns_202_with_document_id_and_queued_status(
        self,
        api: TestClient,
        auth_headers: dict[str, str],
        user: User,
        project: Project,
        db_session: Session,
        storage: LocalFileStorage,
        dispatched: list[uuid.UUID],
    ) -> None:
        pdf = make_pdf("REQ-001: The system shall log every login.")

        response = upload(api, pdf, "srs_v3.pdf", auth_headers, "application/pdf")

        assert response.status_code == 202
        body = response.json()
        # the documented contract (docs/engineering/api-reference.md)...
        assert body["status"] == "queued"
        assert body["filename"] == "srs_v3.pdf"
        document_id = uuid.UUID(body["document_id"])
        assert response.headers["Location"] == f"/api/v1/documents/{document_id}"
        # ...plus the extras the UI needs
        assert body["format"] == "pdf"
        assert body["size_bytes"] == len(pdf)
        assert body["progress_percent"] == 0
        assert body["requirement_count"] == 0
        assert body["error_message"] is None
        assert body["uploaded_by"] == str(user.id)
        assert body["duplicate_of"] is None
        assert body["project_id"] == str(project.id)
        assert body["import_mode"] == "proposals"  # the safe default
        assert body["stakeholder_group"] is None
        assert "storage_path" not in body
        assert "sha256" not in body

        document = db_session.get(Document, document_id)
        assert document is not None
        assert document.workspace_id == project.workspace_id
        assert document.project_id == project.id
        assert document.status is DocumentStatus.QUEUED
        assert document.task_id == "task-1"
        assert document.storage_path == f"{project.workspace_id}/{document_id}.pdf"
        assert storage.resolve(document.storage_path).read_bytes() == pdf
        assert dispatched == [document_id]

    def test_docx_is_accepted(self, api: TestClient, auth_headers: dict[str, str]) -> None:
        response = upload(api, make_docx("REQ-1: hello"), "srs.docx", auth_headers)
        assert response.status_code == 202
        assert response.json()["format"] == "docx"

    @pytest.mark.parametrize("role", holders_of("doc.upload"))
    def test_every_role_holding_doc_upload_may_upload_proposals(
        self, api: TestClient, as_role: Callable[[DefaultRole], dict[str, str]], role: DefaultRole
    ) -> None:
        assert upload(api, make_pdf(), "a.pdf", as_role(role)).status_code == 202

    def test_upload_is_audited_with_identifiers_only(
        self,
        api: TestClient,
        user: User,
        project: Project,
        auth_headers: dict[str, str],
        db_session: Session,
    ) -> None:
        body = upload(api, make_pdf(), "secret-plans.pdf", auth_headers).json()
        row = db_session.scalar(
            select(AuditLog).where(AuditLog.action == AuditAction.DOCUMENT_UPLOADED)
        )
        assert row is not None
        assert row.actor_id == user.id and row.workspace_id == project.workspace_id
        assert row.details == {
            "document_id": body["document_id"],
            "project_id": str(project.id),
            "import_mode": "proposals",
        }
        assert "secret-plans" not in str(row.details)  # no file or requirement text (CR-04)

    def test_client_filename_is_sanitised_and_never_used_as_a_path(
        self,
        api: TestClient,
        auth_headers: dict[str, str],
        db_session: Session,
        storage: LocalFileStorage,
    ) -> None:
        response = upload(api, make_pdf(), "../../../etc/cron.d/evil.pdf", auth_headers)

        assert response.status_code == 202
        assert response.json()["filename"] == "evil.pdf"
        document = db_session.get(Document, uuid.UUID(response.json()["document_id"]))
        assert document is not None
        assert "evil" not in document.storage_path
        assert [p.relative_to(storage.root).as_posix() for p in stored_files(storage)] == [
            document.storage_path
        ]

    def test_content_type_header_is_ignored(
        self, api: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """A wrong (or hostile) Content-Type must neither block a good file nor rescue a bad one."""
        assert upload(api, make_pdf(), "a.pdf", auth_headers, "text/html").status_code == 202
        assert upload(api, b"<html>", "a.pdf", auth_headers, "application/pdf").status_code == 400

    def test_file_is_stored_before_the_job_is_queued(
        self,
        api: TestClient,
        auth_headers: dict[str, str],
        db_session: Session,
        storage: LocalFileStorage,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The worker must never be handed a document whose row or file isn't there yet."""
        seen: list[tuple[bool, bool]] = []

        def dispatch(document_id: uuid.UUID) -> str:
            document = db_session.get(Document, document_id)
            seen.append(
                (
                    document is not None,
                    document is not None and storage.exists(document.storage_path),
                )
            )
            return "t"

        monkeypatch.setattr(document_service, "dispatch_processing", dispatch)
        upload(api, make_pdf(), "a.pdf", auth_headers)
        assert seen == [(True, True)]


class TestRejected:
    """'Given an unsupported or corrupted file ... rejects it with a clear, specific error.'"""

    @pytest.mark.parametrize(
        ("data", "name", "code"),
        [
            (b"hello", "notes.txt", "unsupported_file_type"),
            (make_pdf(), "malware.exe", "unsupported_file_type"),
            (make_pdf(), "no_extension", "unsupported_file_type"),
            (b"", "empty.pdf", "empty_file"),
            (b"just some text pretending" * 10, "fake.pdf", "corrupted_file"),
            (make_pdf()[:300], "truncated.pdf", "corrupted_file"),
            (make_docx("x"), "wrong.pdf", "file_content_mismatch"),
            (make_pdf(), "wrong.docx", "file_content_mismatch"),
            (OLE_HEADER, "old.doc", "unsupported_file_type"),
            (OLE_HEADER, "locked.docx", "file_content_mismatch"),
            (b"PK\x03\x04garbage", "broken.docx", "corrupted_file"),
        ],
    )
    def test_returns_400_with_a_specific_code_and_stores_nothing(
        self,
        api: TestClient,
        auth_headers: dict[str, str],
        db_session: Session,
        storage: LocalFileStorage,
        dispatched: list[uuid.UUID],
        data: bytes,
        name: str,
        code: str,
    ) -> None:
        response = upload(api, data, name, auth_headers)

        assert response.status_code == 400
        error = response.json()["error"]
        assert error["code"] == code
        assert len(error["message"]) > 20
        assert error["request_id"] == response.headers["X-Request-ID"]
        assert document_count(db_session) == 0
        assert stored_files(storage) == []
        assert dispatched == []

    def test_missing_file_part_is_a_422(
        self, api: TestClient, auth_headers: dict[str, str]
    ) -> None:
        response = api.post(
            documents_url(_CURRENT["project"]), data={"note": "no file here"}, headers=auth_headers
        )
        assert response.status_code == 422
        assert response.json()["error"]["details"][0]["field"] == "file"


class TestSizeLimit:
    """'Given a file exceeding the configured size limit ... rejects it before processing begins.'"""

    @pytest.fixture(autouse=True)
    def _one_megabyte_limit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(get_settings(), "max_upload_size_mb", 1)

    def test_one_byte_over_the_limit_is_413_and_nothing_is_kept(
        self,
        api: TestClient,
        auth_headers: dict[str, str],
        db_session: Session,
        storage: LocalFileStorage,
        dispatched: list[uuid.UUID],
    ) -> None:
        too_big = pad_pdf(make_pdf(), 1024 * 1024 + 1)

        response = upload(api, too_big, "big.pdf", auth_headers)

        assert response.status_code == 413
        error = response.json()["error"]
        assert error["code"] == "payload_too_large"
        assert "1 MB" in error["message"]
        assert document_count(db_session) == 0
        assert stored_files(storage) == []
        assert dispatched == []

    def test_exactly_at_the_limit_is_accepted(
        self, api: TestClient, auth_headers: dict[str, str]
    ) -> None:
        at_limit = pad_pdf(make_pdf(), 1024 * 1024)
        assert len(at_limit) == 1024 * 1024
        assert upload(api, at_limit, "edge.pdf", auth_headers).status_code == 202


class TestAtomicity:
    def test_queue_outage_returns_503_and_leaves_no_orphan(
        self,
        api: TestClient,
        auth_headers: dict[str, str],
        db_session: Session,
        storage: LocalFileStorage,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def broker_down(_: uuid.UUID) -> str:
            raise ConnectionError("redis is down")

        monkeypatch.setattr(document_service, "dispatch_processing", broker_down)

        response = upload(api, make_pdf(), "a.pdf", auth_headers)

        assert response.status_code == 503
        assert response.json()["error"]["code"] == "queue_unavailable"
        assert "try again" in response.json()["error"]["message"]
        assert document_count(db_session) == 0
        assert stored_files(storage) == []

    def test_a_failing_disk_write_leaves_nothing_behind(
        self,
        api: TestClient,
        user: User,
        project: Project,
        db_session: Session,
        storage: LocalFileStorage,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def disk_full(*_: object, **__: object) -> None:
            raise OSError("no space left on device")

        monkeypatch.setattr(LocalFileStorage, "commit", disk_full)

        with pytest.raises(OSError, match="no space"):
            document_service.create_document_from_upload(
                db_session,
                user=user,
                project=project,
                filename="a.pdf",
                source=__import__("io").BytesIO(make_pdf()),
                storage=storage,
                max_upload_size_mb=25,
            )

        assert document_count(db_session) == 0
        assert stored_files(storage) == []


class TestDuplicates:
    def test_identical_content_is_accepted_and_points_at_the_earlier_upload(
        self, api: TestClient, auth_headers: dict[str, str]
    ) -> None:
        pdf = make_pdf("REQ-7: same file")
        first = upload(api, pdf, "srs.pdf", auth_headers).json()
        second = upload(api, pdf, "srs_copy.pdf", auth_headers)

        assert second.status_code == 202
        assert second.json()["duplicate_of"] == first["document_id"]
        assert second.json()["document_id"] != first["document_id"]

    def test_the_same_content_in_another_project_is_not_a_duplicate(
        self,
        api: TestClient,
        auth_headers: dict[str, str],
        make_project: Callable[..., Project],
    ) -> None:
        pdf = make_pdf("REQ-8: shared text")
        upload(api, pdf, "a.pdf", auth_headers)
        response = upload(api, pdf, "a.pdf", auth_headers, project=make_project())
        assert response.json()["duplicate_of"] is None

    def test_the_same_content_in_another_workspace_is_not_a_duplicate(
        self,
        api: TestClient,
        auth_headers: dict[str, str],
        make_user: Callable[..., User],
        make_workspace: Callable[..., Workspace],
        make_project: Callable[..., Project],
    ) -> None:
        pdf = make_pdf("REQ-8: shared text")
        upload(api, pdf, "a.pdf", auth_headers)
        rival_workspace = make_workspace()
        other = make_user(workspace=rival_workspace)
        rival_project = make_project(workspace=rival_workspace)
        response = upload(api, pdf, "a.pdf", headers_for(other), project=rival_project)
        assert response.json()["duplicate_of"] is None

    def test_a_failed_earlier_upload_does_not_count(
        self, api: TestClient, auth_headers: dict[str, str], db_session: Session
    ) -> None:
        pdf = make_pdf("REQ-9: retry me")
        first = upload(api, pdf, "a.pdf", auth_headers).json()
        document = db_session.get(Document, uuid.UUID(first["document_id"]))
        assert document is not None
        document.status = DocumentStatus.FAILED
        db_session.commit()

        assert upload(api, pdf, "a.pdf", auth_headers).json()["duplicate_of"] is None


class TestImportMode:
    """FR-01 / SX-08: import as baseline (Approved) needs baseline.manage; as proposals needs doc.upload."""

    @pytest.mark.parametrize("role", holders_of("baseline.manage"))
    def test_roles_with_baseline_manage_may_import_a_baseline(
        self,
        api: TestClient,
        as_role: Callable[[DefaultRole], dict[str, str]],
        db_session: Session,
        role: DefaultRole,
    ) -> None:
        response = upload(api, make_pdf(), "a.pdf", as_role(role), import_mode="baseline")
        assert response.status_code == 202
        assert response.json()["import_mode"] == "baseline"
        document = db_session.get(Document, uuid.UUID(response.json()["document_id"]))
        assert document is not None and document.import_mode is ImportMode.BASELINE

    @pytest.mark.parametrize(
        "role",
        [r for r in holders_of("doc.upload") if r not in holders_of("baseline.manage")],
    )
    def test_roles_without_baseline_manage_cannot_import_a_baseline_but_can_propose(
        self,
        api: TestClient,
        as_role: Callable[[DefaultRole], dict[str, str]],
        db_session: Session,
        storage: LocalFileStorage,
        role: DefaultRole,
    ) -> None:
        headers = as_role(role)
        denied = upload(api, unique_docx(), "a.docx", headers, import_mode="baseline")
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "forbidden"
        assert document_count(db_session) == 0
        assert stored_files(storage) == []
        assert (
            upload(api, unique_docx(), "a.docx", headers, import_mode="proposals").status_code
            == 202
        )

    def test_unknown_import_mode_is_422(
        self, api: TestClient, auth_headers: dict[str, str]
    ) -> None:
        assert (
            upload(api, make_pdf(), "a.pdf", auth_headers, import_mode="sideways").status_code
            == 422
        )

    def test_stakeholder_group_is_stored_trimmed_and_blank_means_none(
        self, api: TestClient, auth_headers: dict[str, str]
    ) -> None:
        tagged = upload(api, make_pdf(), "a.pdf", auth_headers, stakeholder_group="  Finance  ")
        blank = upload(api, make_pdf(), "b.pdf", auth_headers, stakeholder_group="   ")
        assert tagged.json()["stakeholder_group"] == "Finance"
        assert blank.json()["stakeholder_group"] is None

    def test_overlong_stakeholder_group_is_422(
        self, api: TestClient, auth_headers: dict[str, str]
    ) -> None:
        response = upload(api, make_pdf(), "a.pdf", auth_headers, stakeholder_group="x" * 121)
        assert response.status_code == 422

    def test_uploading_into_a_project_in_setup_is_allowed(
        self,
        api: TestClient,
        auth_headers: dict[str, str],
        make_project: Callable[..., Project],
    ) -> None:
        """The initial SRS is uploaded while the project is still in Setup (design update §12.2)."""
        setup = make_project(status=ProjectStatus.SETUP)
        assert upload(api, make_pdf(), "a.pdf", auth_headers, project=setup).status_code == 202


class TestAccessControl:
    def test_unauthenticated_is_401(self, api: TestClient) -> None:
        response = upload(api, make_pdf(), "a.pdf", {})
        assert response.status_code == 401

    @pytest.mark.parametrize("role", [DefaultRole.VIEWER, DefaultRole.COMPLIANCE_REVIEWER])
    def test_roles_without_upload_permissions_get_403_and_nothing_is_stored(
        self,
        api: TestClient,
        as_role: Callable[[DefaultRole], dict[str, str]],
        db_session: Session,
        storage: LocalFileStorage,
        role: DefaultRole,
    ) -> None:
        response = upload(api, unique_docx(), "a.docx", as_role(role))
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden"
        assert document_count(db_session) == 0
        assert stored_files(storage) == []

    def test_another_workspaces_project_is_404_and_nothing_is_stored(
        self,
        api: TestClient,
        auth_headers: dict[str, str],
        make_workspace: Callable[..., Workspace],
        make_project: Callable[..., Project],
        db_session: Session,
        storage: LocalFileStorage,
    ) -> None:
        theirs = make_project(workspace=make_workspace())
        response = upload(api, unique_docx(), "a.docx", auth_headers, project=theirs)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"
        assert document_count(db_session) == 0
        assert stored_files(storage) == []

    def test_unknown_project_is_404(self, api: TestClient, auth_headers: dict[str, str]) -> None:
        response = api.post(
            f"/api/v1/projects/{uuid.uuid4()}/documents",
            files={"file": ("a.pdf", make_pdf(), "application/pdf")},
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_a_removed_member_cannot_upload(
        self, api: TestClient, user: User, auth_headers: dict[str, str], db_session: Session
    ) -> None:
        from datetime import UTC, datetime

        from app.models import Membership

        db_session.query(Membership).filter_by(user_id=user.id).one().ended_at = datetime.now(UTC)
        db_session.commit()
        assert upload(api, make_pdf(), "a.pdf", auth_headers).status_code == 404


def test_stored_format_comes_from_the_detected_content(
    api: TestClient, auth_headers: dict[str, str], db_session: Session
) -> None:
    body = upload(api, make_pdf(), "REPORT.PDF", auth_headers).json()
    document = db_session.get(Document, uuid.UUID(body["document_id"]))
    assert document is not None
    assert document.format is DocumentFormat.PDF
    assert document.storage_path.endswith(".pdf")  # normalised from ".PDF"
