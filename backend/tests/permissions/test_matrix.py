"""Permission matrix (Affan — US-27, FR-48, NFR-27; generated from the catalogue).

Two layers:

1. **Catalogue × role.** For every default role and every permission, the effective permissions
   the access layer computes from the seeded database equal the spec table
   (``DEFAULT_ROLE_PERMISSIONS``) — including the Compliance Reviewer's protected-only grant.
2. **Routes × role.** Every Sprint 1 route that declares a permission is called by a member of
   each default role: holders get through (not 403/404), everyone else gets 403. The permission a
   route needs is read from the route's own declaration, so the matrix cannot drift from the code;
   ``test_every_permission_route_is_in_the_matrix`` fails when a new route is added without a case.
"""

import io
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core import security
from app.core.permissions import DEFAULT_ROLE_PERMISSIONS, PERMISSIONS, DefaultRole
from app.models import Document, DocumentFormat, JoinRequest, Project, User, Workspace
from app.services import documents as document_service
from app.services import join_codes as join_code_service
from app.services.access import Scope, build_access_context
from app.services.membership import get_default_role
from app.services.storage import LocalFileStorage, get_storage
from app.services.users import create_user
from tests.api.test_access_invariants import _api_routes, _declarations
from tests.factories import make_docx


# ── 1. Catalogue × role ─────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("role", list(DefaultRole), ids=lambda role: role.value)
def test_each_default_role_holds_exactly_its_catalogue_permissions(
    db_session: Session, make_user: Callable[..., User], workspace: Workspace, role: DefaultRole
) -> None:
    member = make_user(role=role)

    context = build_access_context(db_session, member, Scope(workspace.id))

    expected = DEFAULT_ROLE_PERMISSIONS[role]
    for permission in PERMISSIONS:
        assert (permission in context.permissions) == (permission in expected), permission
    held_freely = {p for p in PERMISSIONS if context.can(p)}
    protected_only = {"finding.review"} if role is DefaultRole.COMPLIANCE_REVIEWER else set()
    assert held_freely == expected - protected_only


# ── 2. Routes × role ────────────────────────────────────────────────────────────────────────
@dataclass
class World:
    workspace: Workspace
    project: Project
    document: Document
    join_code_id: uuid.UUID
    join_request: JoinRequest
    viewer_role_id: uuid.UUID


@dataclass(frozen=True)
class Case:
    method: str
    path: str  # with {workspace_id}, {project_id}, {document_id}, {join_code_id}, {join_request_id}
    body: Callable[[World], dict[str, Any] | None] = lambda _: None
    upload: bool = False
    # For require_any_permission routes: the permission this particular request needs.
    needs: str | None = None


CASES = [
    Case("GET", "/api/v1/workspaces/{workspace_id}"),
    Case("PATCH", "/api/v1/workspaces/{workspace_id}", lambda _: {"name": "Renamed"}),
    Case("GET", "/api/v1/workspaces/{workspace_id}/roles"),
    Case("POST", "/api/v1/workspaces/{workspace_id}/projects", lambda _: {"name": "New"}),
    Case("GET", "/api/v1/workspaces/{workspace_id}/projects"),
    Case("GET", "/api/v1/projects/{project_id}"),
    Case("PATCH", "/api/v1/projects/{project_id}", lambda _: {"description": "x"}),
    Case("GET", "/api/v1/projects/{project_id}/context"),
    Case("PUT", "/api/v1/projects/{project_id}/context", lambda _: {"fields": {"purpose": "x"}}),
    Case("GET", "/api/v1/projects/{project_id}/context/versions"),
    Case(
        "POST",
        "/api/v1/projects/{project_id}/context/draft",
        lambda w: {"document_id": str(w.document.id)},
    ),
    Case("POST", "/api/v1/projects/{project_id}/documents", upload=True, needs="doc.upload"),
    Case("GET", "/api/v1/projects/{project_id}/documents"),
    Case("GET", "/api/v1/documents/{document_id}"),
    Case("GET", "/api/v1/projects/{project_id}/requirements"),
    Case(
        "POST",
        "/api/v1/workspaces/{workspace_id}/join-codes",
        lambda w: {"role_id": str(w.viewer_role_id)},
    ),
    Case("GET", "/api/v1/workspaces/{workspace_id}/join-codes"),
    Case("DELETE", "/api/v1/join-codes/{join_code_id}"),
    Case("GET", "/api/v1/workspaces/{workspace_id}/join-requests"),
    Case("GET", "/api/v1/workspaces/{workspace_id}/join-requests/{join_request_id}/decision"),
    Case(
        "POST",
        "/api/v1/workspaces/{workspace_id}/join-requests/{join_request_id}/decision",
        lambda _: {"approve": False},
    ),
]


def _declared_permission(method: str, path: str) -> tuple[str, ...]:
    for route_method, route in _api_routes():
        if route_method == method and route.path == path:
            return _declarations(route.dependant)[0].permissions
    raise AssertionError(f"{method} {path} is not a route of the app")


@pytest.fixture
def world(
    db_session: Session,
    workspace: Workspace,
    project: Project,
    make_user: Callable[..., User],
) -> World:
    owner = make_user(role=DefaultRole.OWNER)
    document = Document(
        workspace_id=workspace.id,
        project_id=project.id,
        uploaded_by=owner.id,
        filename="srs.docx",
        format=DocumentFormat.DOCX,
        size_bytes=1,
        sha256="0" * 64,
        storage_path="srs.docx",
    )
    db_session.add(document)
    db_session.commit()
    developer_role = get_default_role(db_session, DefaultRole.DEVELOPER).id
    code = join_code_service.create_code(
        db_session, workspace_id=workspace.id, creator=owner, role_id=developer_role,
        expires_in_days=7,
    )  # fmt: skip
    gated = join_code_service.create_code(
        db_session, workspace_id=workspace.id, creator=owner, role_id=developer_role,
        expires_in_days=7, requires_approval=True,
    )  # fmt: skip
    newcomer = create_user(
        db_session,
        email=f"new-{uuid.uuid4().hex[:8]}@example.com",
        password="correct-horse-battery-staple",
        full_name="Newcomer",
    )
    request = join_code_service.redeem(db_session, gated.code, newcomer)
    assert isinstance(request, JoinRequest)
    db_session.commit()
    viewer = get_default_role(db_session, DefaultRole.VIEWER).id
    return World(workspace, project, document, code.join_code.id, request, viewer)


@pytest.fixture
def api(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    from app.main import app

    monkeypatch.setattr(document_service, "dispatch_processing", lambda _id: "task-1")
    app.dependency_overrides[get_storage] = lambda: LocalFileStorage(tmp_path / "uploads")
    yield client
    app.dependency_overrides.pop(get_storage, None)


def _call(api: TestClient, case: Case, world: World, user: User) -> int:
    path = case.path.format(
        workspace_id=world.workspace.id,
        project_id=world.project.id,
        document_id=world.document.id,
        join_code_id=world.join_code_id,
        join_request_id=world.join_request.id,
    )
    headers = {"Authorization": f"Bearer {security.create_access_token(user.id)[0]}"}
    body = case.body(world)
    if case.upload:
        files = {"file": ("srs.docx", io.BytesIO(make_docx("REQ-001: It shall work.")), "x")}
        return api.request(case.method, path, files=files, headers=headers).status_code
    return api.request(case.method, path, json=body, headers=headers).status_code


@pytest.mark.parametrize("role", list(DefaultRole), ids=lambda role: role.value)
@pytest.mark.parametrize("case", CASES, ids=lambda case: f"{case.method} {case.path}")
def test_route_is_allowed_exactly_for_holders_of_its_permission(
    api: TestClient,
    db_session: Session,
    world: World,
    make_user: Callable[..., User],
    case: Case,
    role: DefaultRole,
) -> None:
    declared = _declared_permission(case.method, case.path)
    needed = case.needs or declared[0]
    member = make_user(role=role)

    status = _call(api, case, world, member)

    if needed in DEFAULT_ROLE_PERMISSIONS[role]:
        assert status not in (401, 403, 404), f"{role.value} should pass, got {status}"
    else:
        assert status == 403, f"{role.value} should be refused, got {status}"


def test_every_permission_route_is_in_the_matrix() -> None:
    covered = {(case.method, case.path) for case in CASES}
    declared = {
        (method, route.path)
        for method, route in _api_routes()
        if _declarations(route.dependant)[0].kind in ("permission", "any_permission")
        and not route.path.startswith(("/api/v1/findings", "/api/v1/reports"))
    }
    assert declared <= covered, f"add these routes to CASES: {sorted(declared - covered)}"
