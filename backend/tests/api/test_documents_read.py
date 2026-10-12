"""GET /documents, /documents/{id}, /documents/{id}/requirements — US-03 status and US-04 list."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import (
    Document,
    DocumentFormat,
    DocumentStatus,
    Requirement,
    Role,
    User,
    Workspace,
)
from app.services.users import create_user
from tests.api.conftest import DOCUMENTS, headers_for
from tests.conftest import TEST_PASSWORD

BASE_TIME = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def add_document(db_session: Session) -> Callable[..., Document]:
    counter = 0

    def build(
        owner: User,
        *,
        filename: str = "srs.pdf",
        status: DocumentStatus = DocumentStatus.DONE,
        bodies: tuple[str, ...] = (),
        source_ids: tuple[str | None, ...] = (),
        error_message: str | None = None,
        progress: int | None = None,
    ) -> Document:
        nonlocal counter
        counter += 1
        document = Document(
            workspace_id=owner.workspace_id,
            uploaded_by=owner.id,
            filename=filename,
            format=DocumentFormat.PDF,
            size_bytes=1000,
            sha256=f"{counter:064x}",
            storage_path=f"{owner.workspace_id}/{uuid.uuid4()}.pdf",
            status=status,
            progress_percent=progress
            if progress is not None
            else (100 if status is DocumentStatus.DONE else 0),
            error_message=error_message,
            uploaded_at=BASE_TIME
            + timedelta(minutes=counter),  # strictly increasing, deterministic
        )
        db_session.add(document)
        db_session.flush()
        for index, body in enumerate(bodies):
            db_session.add(
                Requirement(
                    document_id=document.id,
                    body=body,
                    order_index=index,
                    source_req_id=source_ids[index] if index < len(source_ids) else None,
                    location=f"page/para {index + 1}",
                )
            )
        db_session.commit()
        return document

    return build


@pytest.fixture
def outsider(db_session: Session) -> User:
    """An analyst in a *different* workspace."""
    workspace = Workspace(name=f"Rival {uuid.uuid4().hex[:8]}")
    db_session.add(workspace)
    db_session.commit()
    return create_user(
        db_session,
        email="rival@example.com",
        password=TEST_PASSWORD,
        full_name="Rival",
        role=Role.ANALYST,
        workspace=workspace,
    )


class TestListDocuments:
    def test_newest_first_with_requirement_counts(
        self,
        api: TestClient,
        user: User,
        auth_headers: dict[str, str],
        add_document: Callable[..., Document],
    ) -> None:
        old = add_document(user, filename="old.pdf", bodies=("a", "b", "c"))
        new = add_document(user, filename="new.pdf", bodies=("x",))

        body = api.get(DOCUMENTS, headers=auth_headers).json()

        assert [item["document_id"] for item in body["items"]] == [str(new.id), str(old.id)]
        assert [item["requirement_count"] for item in body["items"]] == [1, 3]
        assert body["total"] == 2
        assert (body["limit"], body["offset"]) == (20, 0)

    def test_pagination_slices_and_reports_the_total(
        self,
        api: TestClient,
        user: User,
        auth_headers: dict[str, str],
        add_document: Callable[..., Document],
    ) -> None:
        docs = [add_document(user, filename=f"d{i}.pdf") for i in range(5)]
        expected = [str(d.id) for d in reversed(docs)]  # newest first

        page = api.get(DOCUMENTS, params={"limit": 2, "offset": 2}, headers=auth_headers).json()

        assert [i["document_id"] for i in page["items"]] == expected[2:4]
        assert page["total"] == 5
        assert api.get(DOCUMENTS, params={"offset": 99}, headers=auth_headers).json()["items"] == []

    def test_status_filter(
        self,
        api: TestClient,
        user: User,
        auth_headers: dict[str, str],
        add_document: Callable[..., Document],
    ) -> None:
        add_document(user, status=DocumentStatus.DONE)
        failed = add_document(user, status=DocumentStatus.FAILED, error_message="[extraction] x")

        body = api.get(DOCUMENTS, params={"status": "failed"}, headers=auth_headers).json()

        assert [i["document_id"] for i in body["items"]] == [str(failed.id)]
        assert body["total"] == 1

    @pytest.mark.parametrize(
        "params", [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"status": "weird"}]
    )
    def test_bad_query_parameters_are_422(
        self, api: TestClient, auth_headers: dict[str, str], params: dict[str, object]
    ) -> None:
        assert api.get(DOCUMENTS, params=params, headers=auth_headers).status_code == 422

    def test_only_the_callers_workspace_is_visible(
        self,
        api: TestClient,
        user: User,
        outsider: User,
        auth_headers: dict[str, str],
        add_document: Callable[..., Document],
    ) -> None:
        mine = add_document(user)
        add_document(outsider, filename="secret.pdf")

        body = api.get(DOCUMENTS, headers=auth_headers).json()

        assert [i["document_id"] for i in body["items"]] == [str(mine.id)]
        assert body["total"] == 1

    def test_empty_workspace_returns_an_empty_page(
        self, api: TestClient, auth_headers: dict[str, str]
    ) -> None:
        assert api.get(DOCUMENTS, headers=auth_headers).json() == {
            "items": [],
            "total": 0,
            "limit": 20,
            "offset": 0,
        }


class TestGetDocument:
    def test_processing_shows_status_and_progress(
        self,
        api: TestClient,
        user: User,
        auth_headers: dict[str, str],
        add_document: Callable[..., Document],
    ) -> None:
        document = add_document(user, status=DocumentStatus.PROCESSING, progress=10)

        body = api.get(f"{DOCUMENTS}/{document.id}", headers=auth_headers).json()

        assert body["status"] == "processing"
        assert body["progress_percent"] == 10
        assert body["error_message"] is None

    def test_failed_document_explains_why(
        self,
        api: TestClient,
        user: User,
        auth_headers: dict[str, str],
        add_document: Callable[..., Document],
    ) -> None:
        document = add_document(
            user,
            status=DocumentStatus.FAILED,
            error_message="[extraction] The document could not be read.",
        )
        body = api.get(f"{DOCUMENTS}/{document.id}", headers=auth_headers).json()
        assert body["status"] == "failed"
        assert body["error_message"].startswith("[extraction]")

    def test_done_document_reports_its_requirement_count(
        self,
        api: TestClient,
        user: User,
        auth_headers: dict[str, str],
        add_document: Callable[..., Document],
    ) -> None:
        document = add_document(user, bodies=("a", "b"))
        assert (
            api.get(f"{DOCUMENTS}/{document.id}", headers=auth_headers).json()["requirement_count"]
            == 2
        )

    def test_another_workspaces_document_is_404_not_403(
        self,
        api: TestClient,
        outsider: User,
        auth_headers: dict[str, str],
        add_document: Callable[..., Document],
    ) -> None:
        theirs = add_document(outsider)
        response = api.get(f"{DOCUMENTS}/{theirs.id}", headers=auth_headers)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_unknown_id_is_404_and_malformed_id_is_422(
        self, api: TestClient, auth_headers: dict[str, str]
    ) -> None:
        assert api.get(f"{DOCUMENTS}/{uuid.uuid4()}", headers=auth_headers).status_code == 404
        assert api.get(f"{DOCUMENTS}/not-a-uuid", headers=auth_headers).status_code == 422


class TestListRequirements:
    def test_returns_requirements_in_document_order(
        self,
        api: TestClient,
        user: User,
        auth_headers: dict[str, str],
        add_document: Callable[..., Document],
    ) -> None:
        document = add_document(
            user,
            bodies=("The system shall A.", "The system shall B.", "The system shall C."),
            source_ids=("REQ-001", None, "FR-1.2"),
        )

        body = api.get(f"{DOCUMENTS}/{document.id}/requirements", headers=auth_headers).json()

        assert [r["body"] for r in body["items"]] == [
            "The system shall A.",
            "The system shall B.",
            "The system shall C.",
        ]
        assert [r["source_req_id"] for r in body["items"]] == ["REQ-001", None, "FR-1.2"]
        first = body["items"][0]
        assert first["document_id"] == str(document.id)
        assert first["location"] == "page/para 1"
        assert first["is_protected"] is False
        assert first["current_version"] == 1
        assert uuid.UUID(first["requirement_id"])
        assert body["total"] == 3

    def test_pagination(
        self,
        api: TestClient,
        user: User,
        auth_headers: dict[str, str],
        add_document: Callable[..., Document],
    ) -> None:
        document = add_document(user, bodies=tuple(f"requirement {i}" for i in range(7)))
        page = api.get(
            f"{DOCUMENTS}/{document.id}/requirements",
            params={"limit": 3, "offset": 3},
            headers=auth_headers,
        ).json()
        assert [r["body"] for r in page["items"]] == [
            "requirement 3",
            "requirement 4",
            "requirement 5",
        ]
        assert page["total"] == 7

    def test_search_matches_text_and_ids_case_insensitively(
        self,
        api: TestClient,
        user: User,
        auth_headers: dict[str, str],
        add_document: Callable[..., Document],
    ) -> None:
        document = add_document(
            user,
            bodies=(
                "The system shall encrypt backups.",
                "Users must reset passwords.",
                "Logs are kept 90 days.",
            ),
            source_ids=(None, "SEC-9", None),
        )
        url = f"{DOCUMENTS}/{document.id}/requirements"

        by_text = api.get(url, params={"q": "ENCRYPT"}, headers=auth_headers).json()
        by_id = api.get(url, params={"q": "sec-9"}, headers=auth_headers).json()

        assert [r["body"] for r in by_text["items"]] == ["The system shall encrypt backups."]
        assert [r["body"] for r in by_id["items"]] == ["Users must reset passwords."]
        assert by_text["total"] == by_id["total"] == 1

    @pytest.mark.parametrize(
        ("term", "expected"), [("100%", 1), ("100", 2), ("a_b", 1), ("%", 1), ("_", 1)]
    )
    def test_search_treats_like_wildcards_literally(
        self,
        api: TestClient,
        user: User,
        auth_headers: dict[str, str],
        add_document: Callable[..., Document],
        term: str,
        expected: int,
    ) -> None:
        document = add_document(
            user, bodies=("Uptime of 100% is required.", "Handle 1000 users.", "Field a_b only.")
        )
        response = api.get(
            f"{DOCUMENTS}/{document.id}/requirements", params={"q": term}, headers=auth_headers
        ).json()
        assert response["total"] == expected

    def test_search_without_matches_is_an_empty_page(
        self,
        api: TestClient,
        user: User,
        auth_headers: dict[str, str],
        add_document: Callable[..., Document],
    ) -> None:
        document = add_document(user, bodies=("hello",))
        body = api.get(
            f"{DOCUMENTS}/{document.id}/requirements", params={"q": "zzz"}, headers=auth_headers
        ).json()
        assert body["items"] == [] and body["total"] == 0

    def test_a_document_with_no_requirements_is_an_empty_page_not_an_error(
        self,
        api: TestClient,
        user: User,
        auth_headers: dict[str, str],
        add_document: Callable[..., Document],
    ) -> None:
        """US-04: empty/failed extraction must be explainable — the UI reads status on /documents/{id}."""
        document = add_document(
            user, status=DocumentStatus.FAILED, error_message="[extraction] nothing found"
        )
        response = api.get(f"{DOCUMENTS}/{document.id}/requirements", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["items"] == []

    def test_another_workspaces_requirements_are_404(
        self,
        api: TestClient,
        outsider: User,
        auth_headers: dict[str, str],
        add_document: Callable[..., Document],
    ) -> None:
        theirs = add_document(outsider, bodies=("confidential",))
        assert (
            api.get(f"{DOCUMENTS}/{theirs.id}/requirements", headers=auth_headers).status_code
            == 404
        )

    def test_unknown_document_is_404(self, api: TestClient, auth_headers: dict[str, str]) -> None:
        assert (
            api.get(f"{DOCUMENTS}/{uuid.uuid4()}/requirements", headers=auth_headers).status_code
            == 404
        )

    def test_overlong_search_is_422(
        self,
        api: TestClient,
        user: User,
        auth_headers: dict[str, str],
        add_document: Callable[..., Document],
    ) -> None:
        document = add_document(user)
        response = api.get(
            f"{DOCUMENTS}/{document.id}/requirements", params={"q": "x" * 201}, headers=auth_headers
        )
        assert response.status_code == 422


class TestAccessControl:
    @pytest.mark.parametrize("path", ["", "/{id}", "/{id}/requirements"])
    def test_unauthenticated_is_401(
        self, api: TestClient, user: User, add_document: Callable[..., Document], path: str
    ) -> None:
        document = add_document(user)
        assert api.get(DOCUMENTS + path.format(id=document.id)).status_code == 401

    @pytest.mark.parametrize("role", [Role.ANALYST, Role.ADMIN, Role.COMPLIANCE_REVIEWER])
    def test_roles_that_may_read(
        self, api: TestClient, as_role: Callable[[Role], dict[str, str]], role: Role
    ) -> None:
        assert api.get(DOCUMENTS, headers=as_role(role)).status_code == 200

    @pytest.mark.parametrize("role", [Role.READ_ONLY, Role.SERVICE])
    def test_roles_that_may_not_read_documents(
        self, api: TestClient, as_role: Callable[[Role], dict[str, str]], role: Role
    ) -> None:
        assert api.get(DOCUMENTS, headers=as_role(role)).status_code == 403

    def test_a_reader_in_the_same_workspace_sees_the_same_documents(
        self,
        api: TestClient,
        user: User,
        as_role: Callable[[Role], dict[str, str]],
        add_document: Callable[..., Document],
    ) -> None:
        document = add_document(user)
        body = api.get(DOCUMENTS, headers=as_role(Role.COMPLIANCE_REVIEWER)).json()
        assert [i["document_id"] for i in body["items"]] == [str(document.id)]


def test_headers_helper_matches_auth_headers_fixture(
    user: User, auth_headers: dict[str, str]
) -> None:
    assert headers_for(user).keys() == auth_headers.keys()
