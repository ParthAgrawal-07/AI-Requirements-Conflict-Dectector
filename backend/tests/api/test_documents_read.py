"""Project document list/status (US-03) and the project requirements list (US-04).

Routes: ``GET /projects/{p}/documents``, ``GET /documents/{id}``, ``GET /projects/{p}/requirements``.
"""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.permissions import DefaultRole
from app.models import (
    Document,
    DocumentFormat,
    DocumentStatus,
    Project,
    Requirement,
    RequirementOrigin,
    RequirementState,
    User,
    Workspace,
)
from tests.api.conftest import documents_url, headers_for, requirements_url

BASE_TIME = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
DOCUMENT = "/api/v1/documents"


@pytest.fixture
def add_document(db_session: Session, project: Project) -> Callable[..., Document]:
    counter = 0

    def build(
        owner: User,
        *,
        project: Project = project,
        filename: str = "srs.pdf",
        status: DocumentStatus = DocumentStatus.DONE,
        bodies: tuple[str, ...] = (),
        source_ids: tuple[str | None, ...] = (),
        error_message: str | None = None,
        progress: int | None = None,
        state: RequirementState = RequirementState.PROPOSED,
        origin: RequirementOrigin = RequirementOrigin.DOCUMENT,
        requirement_owner: User | None = None,
    ) -> Document:
        nonlocal counter
        counter += 1
        document = Document(
            workspace_id=project.workspace_id,
            project_id=project.id,
            uploaded_by=owner.id,
            filename=filename,
            format=DocumentFormat.PDF,
            size_bytes=1000,
            sha256=f"{counter:064x}",
            storage_path=f"{project.workspace_id}/{uuid.uuid4()}.pdf",
            status=status,
            progress_percent=progress
            if progress is not None
            else (100 if status is DocumentStatus.DONE else 0),
            error_message=error_message,
            uploaded_at=BASE_TIME + timedelta(minutes=counter),  # strictly increasing
        )
        db_session.add(document)
        db_session.flush()
        for index, body in enumerate(bodies):
            db_session.add(
                Requirement(
                    document_id=document.id,
                    project_id=project.id,
                    body=body,
                    order_index=index,
                    source_req_id=source_ids[index] if index < len(source_ids) else None,
                    location=f"page/para {index + 1}",
                    state=state,
                    origin=origin,
                    owner_id=None if requirement_owner is None else requirement_owner.id,
                    # one document's rows share a time; documents are ordered by upload time
                    created_at=document.uploaded_at,
                )
            )
        db_session.commit()
        return document

    return build


@pytest.fixture
def outsider(make_user: Callable[..., User], make_workspace: Callable[..., Workspace]) -> User:
    """A Business Analyst in a *different* workspace."""
    return make_user(role=DefaultRole.BUSINESS_ANALYST, workspace=make_workspace("Rival"))


@pytest.fixture
def rival_project(
    make_project: Callable[..., Project], outsider: User, db_session: Session
) -> Project:
    workspace = db_session.get(Workspace, next(iter(outsider.memberships)).workspace_id)
    assert workspace is not None
    return make_project(workspace=workspace)


class TestListDocuments:
    def test_newest_first_with_requirement_counts(
        self,
        api: TestClient,
        user: User,
        project: Project,
        auth_headers: dict[str, str],
        add_document: Callable[..., Document],
    ) -> None:
        old = add_document(user, filename="old.pdf", bodies=("a", "b", "c"))
        new = add_document(user, filename="new.pdf", bodies=("x",))

        body = api.get(documents_url(project), headers=auth_headers).json()

        assert [item["document_id"] for item in body["items"]] == [str(new.id), str(old.id)]
        assert [item["requirement_count"] for item in body["items"]] == [1, 3]
        assert body["total"] == 2
        assert (body["limit"], body["offset"]) == (20, 0)
        assert body["items"][0]["project_id"] == str(project.id)

    def test_pagination_slices_and_reports_the_total(
        self,
        api: TestClient,
        user: User,
        project: Project,
        auth_headers: dict[str, str],
        add_document: Callable[..., Document],
    ) -> None:
        docs = [add_document(user, filename=f"d{i}.pdf") for i in range(5)]
        expected = [str(d.id) for d in reversed(docs)]  # newest first
        url = documents_url(project)

        page = api.get(url, params={"limit": 2, "offset": 2}, headers=auth_headers).json()

        assert [i["document_id"] for i in page["items"]] == expected[2:4]
        assert page["total"] == 5
        assert api.get(url, params={"offset": 99}, headers=auth_headers).json()["items"] == []

    def test_status_filter(
        self,
        api: TestClient,
        user: User,
        project: Project,
        auth_headers: dict[str, str],
        add_document: Callable[..., Document],
    ) -> None:
        add_document(user, status=DocumentStatus.DONE)
        failed = add_document(user, status=DocumentStatus.FAILED, error_message="[extraction] x")

        body = api.get(
            documents_url(project), params={"status": "failed"}, headers=auth_headers
        ).json()

        assert [i["document_id"] for i in body["items"]] == [str(failed.id)]
        assert body["total"] == 1

    @pytest.mark.parametrize(
        "params", [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"status": "weird"}]
    )
    def test_bad_query_parameters_are_422(
        self,
        api: TestClient,
        project: Project,
        auth_headers: dict[str, str],
        params: dict[str, object],
    ) -> None:
        assert (
            api.get(documents_url(project), params=params, headers=auth_headers).status_code == 422
        )

    def test_only_the_projects_documents_are_listed(
        self,
        api: TestClient,
        user: User,
        project: Project,
        make_project: Callable[..., Project],
        auth_headers: dict[str, str],
        add_document: Callable[..., Document],
    ) -> None:
        mine = add_document(user)
        add_document(user, project=make_project(), filename="other-project.pdf")

        body = api.get(documents_url(project), headers=auth_headers).json()

        assert [i["document_id"] for i in body["items"]] == [str(mine.id)]
        assert body["total"] == 1

    def test_another_workspaces_project_is_404(
        self,
        api: TestClient,
        outsider: User,
        rival_project: Project,
        auth_headers: dict[str, str],
        add_document: Callable[..., Document],
    ) -> None:
        add_document(outsider, project=rival_project, filename="secret.pdf")
        response = api.get(documents_url(rival_project), headers=auth_headers)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"
        assert "secret" not in response.text

    def test_empty_project_returns_an_empty_page(
        self, api: TestClient, project: Project, auth_headers: dict[str, str]
    ) -> None:
        assert api.get(documents_url(project), headers=auth_headers).json() == {
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

        body = api.get(f"{DOCUMENT}/{document.id}", headers=auth_headers).json()

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
        body = api.get(f"{DOCUMENT}/{document.id}", headers=auth_headers).json()
        assert body["status"] == "failed"
        assert body["error_message"].startswith("[extraction]")

    def test_done_document_reports_its_requirement_count_and_import_details(
        self,
        api: TestClient,
        user: User,
        auth_headers: dict[str, str],
        add_document: Callable[..., Document],
    ) -> None:
        document = add_document(user, bodies=("a", "b"))
        body = api.get(f"{DOCUMENT}/{document.id}", headers=auth_headers).json()
        assert body["requirement_count"] == 2
        assert body["import_mode"] == "proposals"
        assert body["stakeholder_group"] is None

    def test_another_workspaces_document_is_404_not_403(
        self,
        api: TestClient,
        outsider: User,
        rival_project: Project,
        auth_headers: dict[str, str],
        add_document: Callable[..., Document],
    ) -> None:
        theirs = add_document(outsider, project=rival_project)
        response = api.get(f"{DOCUMENT}/{theirs.id}", headers=auth_headers)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_unknown_id_is_404_and_malformed_id_is_422(
        self, api: TestClient, auth_headers: dict[str, str]
    ) -> None:
        assert api.get(f"{DOCUMENT}/{uuid.uuid4()}", headers=auth_headers).status_code == 404
        assert api.get(f"{DOCUMENT}/not-a-uuid", headers=auth_headers).status_code == 422


class TestListRequirements:
    def test_returns_requirements_in_document_order_with_state_origin_and_owner(
        self,
        api: TestClient,
        user: User,
        project: Project,
        auth_headers: dict[str, str],
        add_document: Callable[..., Document],
    ) -> None:
        document = add_document(
            user,
            bodies=("The system shall A.", "The system shall B.", "The system shall C."),
            source_ids=("REQ-001", None, "FR-1.2"),
            requirement_owner=user,
        )

        body = api.get(requirements_url(project), headers=auth_headers).json()

        assert [r["body"] for r in body["items"]] == [
            "The system shall A.",
            "The system shall B.",
            "The system shall C.",
        ]
        assert [r["source_req_id"] for r in body["items"]] == ["REQ-001", None, "FR-1.2"]
        first = body["items"][0]
        assert first["document_id"] == str(document.id)
        assert first["project_id"] == str(project.id)
        assert first["location"] == "page/para 1"
        assert first["is_protected"] is False
        assert first["current_version"] == 1
        assert first["state"] == "Proposed"
        assert first["origin"] == "document"
        assert first["owner_id"] == str(user.id)
        assert first["owner_name"] == user.full_name
        assert uuid.UUID(first["requirement_id"])
        assert body["total"] == 3

    def test_unassigned_requirements_have_no_owner(
        self,
        api: TestClient,
        user: User,
        project: Project,
        auth_headers: dict[str, str],
        add_document: Callable[..., Document],
    ) -> None:
        add_document(user, bodies=("x",))
        item = api.get(requirements_url(project), headers=auth_headers).json()["items"][0]
        assert item["owner_id"] is None and item["owner_name"] is None

    def test_lists_across_all_documents_of_the_project_but_no_other_project(
        self,
        api: TestClient,
        user: User,
        project: Project,
        make_project: Callable[..., Project],
        auth_headers: dict[str, str],
        add_document: Callable[..., Document],
    ) -> None:
        add_document(user, bodies=("first doc",))
        add_document(user, bodies=("second doc",))
        add_document(user, project=make_project(), bodies=("someone else's project",))

        body = api.get(requirements_url(project), headers=auth_headers).json()

        assert [r["body"] for r in body["items"]] == ["first doc", "second doc"]
        assert body["total"] == 2

    def test_document_filter(
        self,
        api: TestClient,
        user: User,
        project: Project,
        auth_headers: dict[str, str],
        add_document: Callable[..., Document],
    ) -> None:
        add_document(user, bodies=("from first",))
        second = add_document(user, bodies=("from second",))
        body = api.get(
            requirements_url(project), params={"document_id": str(second.id)}, headers=auth_headers
        ).json()
        assert [r["body"] for r in body["items"]] == ["from second"]

    def test_state_origin_and_owner_filters(
        self,
        api: TestClient,
        user: User,
        project: Project,
        make_user: Callable[..., User],
        auth_headers: dict[str, str],
        add_document: Callable[..., Document],
    ) -> None:
        other = make_user()
        add_document(user, bodies=("proposed one",), state=RequirementState.PROPOSED)
        add_document(
            user, bodies=("approved one",), state=RequirementState.APPROVED, requirement_owner=other
        )
        add_document(
            user,
            bodies=("from a post",),
            origin=RequirementOrigin.POST,
            requirement_owner=user,
        )
        url = requirements_url(project)

        approved = api.get(url, params={"state": "Approved"}, headers=auth_headers).json()
        posts = api.get(url, params={"origin": "post"}, headers=auth_headers).json()
        owned = api.get(url, params={"owner": str(other.id)}, headers=auth_headers).json()
        combined = api.get(
            url, params={"state": "Proposed", "origin": "post"}, headers=auth_headers
        ).json()

        assert [r["body"] for r in approved["items"]] == ["approved one"]
        assert [r["body"] for r in posts["items"]] == ["from a post"]
        assert [r["body"] for r in owned["items"]] == ["approved one"]
        assert [r["body"] for r in combined["items"]] == ["from a post"]

    @pytest.mark.parametrize(
        "params",
        [
            {"state": "Done"},
            {"origin": "email"},
            {"owner": "not-a-uuid"},
            {"limit": 0},
            {"limit": 201},
        ],
    )
    def test_bad_filters_are_422(
        self,
        api: TestClient,
        project: Project,
        auth_headers: dict[str, str],
        params: dict[str, object],
    ) -> None:
        assert (
            api.get(requirements_url(project), params=params, headers=auth_headers).status_code
            == 422
        )

    def test_pagination(
        self,
        api: TestClient,
        user: User,
        project: Project,
        auth_headers: dict[str, str],
        add_document: Callable[..., Document],
    ) -> None:
        add_document(user, bodies=tuple(f"requirement {i}" for i in range(7)))
        page = api.get(
            requirements_url(project), params={"limit": 3, "offset": 3}, headers=auth_headers
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
        project: Project,
        auth_headers: dict[str, str],
        add_document: Callable[..., Document],
    ) -> None:
        add_document(
            user,
            bodies=(
                "The system shall encrypt backups.",
                "Users must reset passwords.",
                "Logs are kept 90 days.",
            ),
            source_ids=(None, "SEC-9", None),
        )
        url = requirements_url(project)

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
        project: Project,
        auth_headers: dict[str, str],
        add_document: Callable[..., Document],
        term: str,
        expected: int,
    ) -> None:
        add_document(
            user, bodies=("Uptime of 100% is required.", "Handle 1000 users.", "Field a_b only.")
        )
        response = api.get(
            requirements_url(project), params={"q": term}, headers=auth_headers
        ).json()
        assert response["total"] == expected

    def test_search_without_matches_is_an_empty_page(
        self,
        api: TestClient,
        user: User,
        project: Project,
        auth_headers: dict[str, str],
        add_document: Callable[..., Document],
    ) -> None:
        add_document(user, bodies=("hello",))
        body = api.get(requirements_url(project), params={"q": "zzz"}, headers=auth_headers).json()
        assert body["items"] == [] and body["total"] == 0

    def test_a_project_with_no_requirements_is_an_empty_page_not_an_error(
        self,
        api: TestClient,
        user: User,
        project: Project,
        auth_headers: dict[str, str],
        add_document: Callable[..., Document],
    ) -> None:
        """US-04: empty/failed extraction must be explainable — the UI reads status on /documents/{id}."""
        add_document(user, status=DocumentStatus.FAILED, error_message="[extraction] nothing found")
        response = api.get(requirements_url(project), headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["items"] == []

    def test_another_workspaces_requirements_are_404(
        self,
        api: TestClient,
        outsider: User,
        rival_project: Project,
        auth_headers: dict[str, str],
        add_document: Callable[..., Document],
    ) -> None:
        add_document(outsider, project=rival_project, bodies=("confidential",))
        response = api.get(requirements_url(rival_project), headers=auth_headers)
        assert response.status_code == 404
        assert "confidential" not in response.text

    def test_unknown_project_is_404(self, api: TestClient, auth_headers: dict[str, str]) -> None:
        url = f"/api/v1/projects/{uuid.uuid4()}/requirements"
        assert api.get(url, headers=auth_headers).status_code == 404

    def test_overlong_search_is_422(
        self, api: TestClient, project: Project, auth_headers: dict[str, str]
    ) -> None:
        response = api.get(requirements_url(project), params={"q": "x" * 201}, headers=auth_headers)
        assert response.status_code == 422


class TestAccessControl:
    @pytest.mark.parametrize("path", ["/documents", "/requirements"])
    def test_unauthenticated_is_401(self, api: TestClient, project: Project, path: str) -> None:
        assert api.get(f"/api/v1/projects/{project.id}{path}").status_code == 401

    def test_unauthenticated_document_status_is_401(
        self, api: TestClient, user: User, add_document: Callable[..., Document]
    ) -> None:
        assert api.get(f"{DOCUMENT}/{add_document(user).id}").status_code == 401

    @pytest.mark.parametrize("role", list(DefaultRole))
    def test_every_default_role_can_read_because_all_hold_view(
        self,
        api: TestClient,
        project: Project,
        as_role: Callable[[DefaultRole], dict[str, str]],
        role: DefaultRole,
    ) -> None:
        headers = as_role(role)
        assert api.get(documents_url(project), headers=headers).status_code == 200
        assert api.get(requirements_url(project), headers=headers).status_code == 200

    def test_a_reader_in_the_same_workspace_sees_the_same_documents(
        self,
        api: TestClient,
        user: User,
        project: Project,
        as_role: Callable[[DefaultRole], dict[str, str]],
        add_document: Callable[..., Document],
    ) -> None:
        document = add_document(user)
        body = api.get(documents_url(project), headers=as_role(DefaultRole.VIEWER)).json()
        assert [i["document_id"] for i in body["items"]] == [str(document.id)]

    def test_a_removed_member_loses_access_on_the_next_request(
        self, api: TestClient, project: Project, user: User, db_session: Session
    ) -> None:
        from app.models import Membership

        headers = headers_for(user)
        assert api.get(documents_url(project), headers=headers).status_code == 200
        membership = db_session.query(Membership).filter_by(user_id=user.id).one()
        membership.ended_at = datetime.now(UTC)
        db_session.commit()
        assert api.get(documents_url(project), headers=headers).status_code == 404


def test_headers_helper_matches_auth_headers_fixture(
    user: User, auth_headers: dict[str, str]
) -> None:
    assert headers_for(user).keys() == auth_headers.keys()
