"""``require_permission``: permission names decide, membership comes first, 404 before 403.

The probe app below has one route per catalogue permission, so these tests are the full
permission x role matrix of the dependency itself (every permission x every default role).
"""

import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Annotated, Any

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import authenticated_only, require_any_permission, require_permission
from app.core.database import get_db
from app.core.errors import install_exception_handlers
from app.core.permissions import (
    DEFAULT_ROLE_PERMISSIONS,
    PERMISSIONS,
    PROTECTED_ONLY_GRANTS,
    DefaultRole,
)
from app.models import (
    Document,
    DocumentFormat,
    Membership,
    PlatformRole,
    Project,
    ProjectMember,
    User,
    Workspace,
)
from app.services import access
from app.services.access import AccessContext, Scope, register_scope_resolver
from app.services.membership import get_default_role
from tests.api.conftest import headers_for


@pytest.fixture
def probe(db_session: Session) -> Iterator[TestClient]:
    app = FastAPI()
    install_exception_handlers(app)
    app.dependency_overrides[get_db] = lambda: db_session

    for permission in PERMISSIONS:
        dependency = Depends(require_permission(permission))

        @app.get(f"/workspaces/{{workspace_id}}/probe/{permission}")
        def _workspace_probe(ctx: Annotated[AccessContext, dependency]) -> dict[str, Any]:
            return {"role": ctx.role.name}

        @app.get(f"/projects/{{project_id}}/probe/{permission}")
        def _project_probe(ctx: Annotated[AccessContext, dependency]) -> dict[str, Any]:
            return {"role": ctx.role.name}

    for permission in PERMISSIONS:
        opted_in = Depends(require_permission(permission, allow_protected_only=True))

        @app.get(f"/workspaces/{{workspace_id}}/optin/{permission}")
        def _opt_in_probe(ctx: Annotated[AccessContext, opted_in]) -> dict[str, Any]:
            return {"role": ctx.role.name, "protected_only": sorted(ctx.protected_only)}

    @app.get("/workspaces/{workspace_id}/context")
    def context(
        ctx: Annotated[AccessContext, Depends(require_permission("view"))],
    ) -> dict[str, Any]:
        return {
            "workspace_id": str(ctx.workspace_id),
            "project_id": None if ctx.project_id is None else str(ctx.project_id),
            "role": ctx.role.name,
            "permissions": sorted(ctx.permissions),
            "protected_only": sorted(ctx.protected_only),
        }

    @app.get("/workspaces/{workspace_id}/any")
    def any_of(
        ctx: Annotated[
            AccessContext, Depends(require_any_permission("doc.upload", "baseline.manage"))
        ],
    ) -> dict[str, bool]:
        return {"upload": ctx.can("doc.upload"), "baseline": ctx.can("baseline.manage")}

    @app.get("/projects/{project_id}/documents/{document_id}/probe")
    def nested(
        ctx: Annotated[AccessContext, Depends(require_permission("view"))],
    ) -> dict[str, str]:
        return {"ok": "yes"}

    @app.get("/no-scope")
    def no_scope(
        ctx: Annotated[AccessContext, Depends(require_permission("view"))],
    ) -> dict[str, str]:
        return {"ok": "never"}

    @app.get("/account")
    def account(user: Annotated[User, Depends(authenticated_only)]) -> dict[str, str]:
        return {"email": user.email}

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def probe_url(scope: str, scope_id: uuid.UUID, permission: str) -> str:
    return f"/{scope}/{scope_id}/probe/{permission}"


def expected_status(role: DefaultRole, permission: str) -> int:
    """200 only for an *unrestricted* grant: protected-only grants are refused unless opted in."""
    if permission not in DEFAULT_ROLE_PERMISSIONS[role]:
        return 403
    return 403 if (role, permission) in PROTECTED_ONLY_GRANTS else 200


# ── the matrix ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("role", list(DefaultRole))
def test_workspace_permission_matrix(
    probe: TestClient, make_user: Callable[..., User], workspace: Workspace, role: DefaultRole
) -> None:
    headers = headers_for(make_user(role=role))
    for permission in PERMISSIONS:
        response = probe.get(probe_url("workspaces", workspace.id, permission), headers=headers)
        expected = expected_status(role, permission)
        assert response.status_code == expected, f"{role.value} / {permission}"
        if expected == 403:
            assert response.json()["error"]["code"] == "forbidden"


@pytest.mark.parametrize("role", list(DefaultRole))
def test_project_permission_matrix_matches_the_workspace_one(
    probe: TestClient, make_user: Callable[..., User], project: Project, role: DefaultRole
) -> None:
    headers = headers_for(make_user(role=role))
    for permission in PERMISSIONS:
        response = probe.get(probe_url("projects", project.id, permission), headers=headers)
        assert response.status_code == expected_status(role, permission), (
            f"{role.value} / {permission}"
        )


# ── protected-only grants fail closed ───────────────────────────────────────────────────────
def test_a_protected_only_grant_is_refused_unless_the_route_opts_in(
    probe: TestClient, make_user: Callable[..., User], workspace: Workspace
) -> None:
    """The Compliance Reviewer holds finding.review for protected requirements only: a route that
    merely says ``require_permission("finding.review")`` must NOT admit them to every requirement."""
    headers = headers_for(make_user(role=DefaultRole.COMPLIANCE_REVIEWER))

    default = probe.get(probe_url("workspaces", workspace.id, "finding.review"), headers=headers)
    opted_in = probe.get(f"/workspaces/{workspace.id}/optin/finding.review", headers=headers)

    assert default.status_code == 403
    assert opted_in.status_code == 200
    assert opted_in.json()["protected_only"] == ["finding.review"]  # the handler must still check


def test_opting_in_changes_nothing_for_unrestricted_holders(
    probe: TestClient, make_user: Callable[..., User], workspace: Workspace
) -> None:
    analyst = headers_for(make_user(role=DefaultRole.BUSINESS_ANALYST))
    developer = headers_for(make_user(role=DefaultRole.DEVELOPER))
    url = f"/workspaces/{workspace.id}/optin/finding.review"
    assert probe.get(url, headers=analyst).status_code == 200
    assert probe.get(url, headers=developer).status_code == 403  # does not hold it at all


def test_ctx_can_is_safe_by_default_and_takes_the_requirement_into_account(
    db_session: Session, make_user: Callable[..., User], workspace: Workspace
) -> None:
    reviewer = make_user(role=DefaultRole.COMPLIANCE_REVIEWER)
    context = access.build_access_context(db_session, reviewer, Scope(workspace.id))
    assert "finding.review" in context.permissions  # held (and shown in /me/permissions)...
    assert context.can("finding.review") is False  # ...but not for an unspecified requirement
    assert context.can("finding.review", protected_requirement=False) is False
    assert context.can("finding.review", protected_requirement=True) is True
    assert context.can("rcr.review") is True  # an ordinary grant is unaffected
    assert context.can("rcr.merge") is False


def test_require_any_permission_also_refuses_protected_only_unless_opted_in(
    db_session: Session, make_user: Callable[..., User], workspace: Workspace
) -> None:
    app = FastAPI()
    install_exception_handlers(app)
    app.dependency_overrides[get_db] = lambda: db_session

    @app.get("/workspaces/{workspace_id}/plain")
    def plain(
        ctx: Annotated[
            AccessContext, Depends(require_any_permission("finding.review", "rcr.merge"))
        ],
    ) -> dict[str, str]:
        return {"ok": "yes"}

    @app.get("/workspaces/{workspace_id}/optin")
    def optin(
        ctx: Annotated[
            AccessContext,
            Depends(
                require_any_permission("finding.review", "rcr.merge", allow_protected_only=True)
            ),
        ],
    ) -> dict[str, str]:
        return {"ok": "yes"}

    headers = headers_for(make_user(role=DefaultRole.COMPLIANCE_REVIEWER))
    with TestClient(app) as client:
        assert client.get(f"/workspaces/{workspace.id}/plain", headers=headers).status_code == 403
        assert client.get(f"/workspaces/{workspace.id}/optin", headers=headers).status_code == 200


# ── membership comes first: outsiders get 404, never 403 ────────────────────────────────────
def test_a_non_member_gets_404_for_every_permission_even_view(
    probe: TestClient,
    make_user: Callable[..., User],
    make_workspace: Callable[..., Workspace],
    workspace: Workspace,
) -> None:
    outsider = make_user(role=DefaultRole.OWNER, workspace=make_workspace())  # owner *elsewhere*
    headers = headers_for(outsider)
    for permission in ("view", "workspace.manage", "doc.upload"):
        response = probe.get(probe_url("workspaces", workspace.id, permission), headers=headers)
        assert response.status_code == 404, permission
        assert response.json()["error"]["code"] == "not_found"


def test_a_user_with_no_membership_at_all_gets_404(
    probe: TestClient, make_user: Callable[..., User], workspace: Workspace
) -> None:
    loner = make_user(role=None)
    response = probe.get(probe_url("workspaces", workspace.id, "view"), headers=headers_for(loner))
    assert response.status_code == 404


def test_platform_admins_get_no_automatic_access_to_workspaces(
    probe: TestClient, make_user: Callable[..., User], workspace: Workspace
) -> None:
    root = make_user(role=None, platform_role=PlatformRole.PLATFORM_ADMIN)
    response = probe.get(probe_url("workspaces", workspace.id, "view"), headers=headers_for(root))
    assert response.status_code == 404


def test_a_missing_workspace_and_a_foreign_one_are_indistinguishable(
    probe: TestClient,
    make_user: Callable[..., User],
    make_workspace: Callable[..., Workspace],
    user: User,
) -> None:
    headers = headers_for(user)
    foreign = probe.get(probe_url("workspaces", make_workspace().id, "view"), headers=headers)
    missing = probe.get(probe_url("workspaces", uuid.uuid4(), "view"), headers=headers)
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json()["error"]["message"] == missing.json()["error"]["message"]


def test_a_malformed_id_is_a_422_not_a_404(probe: TestClient, user: User) -> None:
    response = probe.get("/workspaces/not-a-uuid/probe/view", headers=headers_for(user))
    assert response.status_code == 422


def test_unauthenticated_is_401_before_anything_else(
    probe: TestClient, workspace: Workspace
) -> None:
    assert probe.get(probe_url("workspaces", workspace.id, "view")).status_code == 401


def test_ids_from_different_tenants_in_one_path_are_a_404(
    probe: TestClient,
    make_user: Callable[..., User],
    make_project: Callable[..., Project],
    make_workspace: Callable[..., Workspace],
    project: Project,
    db_session: Session,
    user: User,
) -> None:
    """A project id with a document id from another project must not leak the document."""
    other_project = make_project()
    document = Document(
        workspace_id=other_project.workspace_id,
        project_id=other_project.id,
        uploaded_by=user.id,
        filename="x.pdf",
        format=DocumentFormat.PDF,
        size_bytes=1,
        sha256="1" * 64,
        storage_path="x",
    )
    db_session.add(document)
    db_session.commit()
    headers = headers_for(user)

    mismatch = probe.get(f"/projects/{project.id}/documents/{document.id}/probe", headers=headers)
    match = probe.get(
        f"/projects/{other_project.id}/documents/{document.id}/probe", headers=headers
    )
    assert mismatch.status_code == 404
    assert match.status_code == 200


# ── membership and roles are re-read on every request ───────────────────────────────────────
def test_removing_a_member_applies_on_their_next_request(
    probe: TestClient, user: User, workspace: Workspace, db_session: Session
) -> None:
    headers = headers_for(user)
    url = probe_url("workspaces", workspace.id, "view")
    assert probe.get(url, headers=headers).status_code == 200

    membership = db_session.scalars(select(Membership).where(Membership.user_id == user.id)).one()
    membership.ended_at = datetime.now(UTC)
    db_session.commit()

    assert probe.get(url, headers=headers).status_code == 404


def test_changing_a_role_applies_on_the_next_request_with_the_same_token(
    probe: TestClient, make_user: Callable[..., User], workspace: Workspace, db_session: Session
) -> None:
    developer = make_user(role=DefaultRole.DEVELOPER)
    headers = headers_for(developer)  # one token, used throughout
    merge = probe_url("workspaces", workspace.id, "rcr.merge")
    assert probe.get(merge, headers=headers).status_code == 403

    membership = db_session.scalars(
        select(Membership).where(Membership.user_id == developer.id)
    ).one()
    membership.role_id = get_default_role(db_session, DefaultRole.BUSINESS_ANALYST).id
    db_session.commit()
    assert probe.get(merge, headers=headers).status_code == 200

    membership.role_id = get_default_role(db_session, DefaultRole.VIEWER).id
    db_session.commit()
    assert probe.get(merge, headers=headers).status_code == 403
    assert (
        probe.get(probe_url("workspaces", workspace.id, "view"), headers=headers).status_code == 200
    )


def test_a_deactivated_user_is_401_even_with_a_valid_membership(
    probe: TestClient, user: User, workspace: Workspace, db_session: Session
) -> None:
    headers = headers_for(user)
    user.is_active = False
    db_session.commit()
    assert (
        probe.get(probe_url("workspaces", workspace.id, "view"), headers=headers).status_code == 401
    )


# ── project-level role override (FR-79) ─────────────────────────────────────────────────────
def test_a_project_role_override_replaces_the_workspace_role_inside_that_project_only(
    probe: TestClient,
    make_user: Callable[..., User],
    project: Project,
    workspace: Workspace,
    db_session: Session,
) -> None:
    viewer = make_user(role=DefaultRole.VIEWER)
    headers = headers_for(viewer)
    in_project = probe_url("projects", project.id, "doc.upload")
    in_workspace = probe_url("workspaces", workspace.id, "doc.upload")
    assert probe.get(in_project, headers=headers).status_code == 403

    db_session.add(
        ProjectMember(
            project_id=project.id,
            user_id=viewer.id,
            role_override_id=get_default_role(db_session, DefaultRole.DEVELOPER).id,
        )
    )
    db_session.commit()

    assert probe.get(in_project, headers=headers).json() == {"role": "Developer"}
    assert probe.get(in_workspace, headers=headers).status_code == 403  # workspace role unchanged


def test_a_project_membership_without_an_override_changes_nothing(
    probe: TestClient, user: User, project: Project, db_session: Session
) -> None:
    db_session.add(ProjectMember(project_id=project.id, user_id=user.id))
    db_session.commit()
    response = probe.get(probe_url("projects", project.id, "doc.upload"), headers=headers_for(user))
    assert response.json() == {"role": "Business Analyst"}


# ── any-of ──────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("role", "status", "flags"),
    [
        (DefaultRole.BUSINESS_ANALYST, 200, {"upload": True, "baseline": True}),
        (DefaultRole.DEVELOPER, 200, {"upload": True, "baseline": False}),
        (DefaultRole.VIEWER, 403, None),
        (DefaultRole.COMPLIANCE_REVIEWER, 403, None),
    ],
)
def test_require_any_permission(
    probe: TestClient,
    make_user: Callable[..., User],
    workspace: Workspace,
    role: DefaultRole,
    status: int,
    flags: dict[str, bool] | None,
) -> None:
    response = probe.get(
        f"/workspaces/{workspace.id}/any", headers=headers_for(make_user(role=role))
    )
    assert response.status_code == status
    if flags is not None:
        assert response.json() == flags


def test_require_any_permission_still_hides_other_tenants(
    probe: TestClient, make_workspace: Callable[..., Workspace], user: User
) -> None:
    response = probe.get(f"/workspaces/{make_workspace().id}/any", headers=headers_for(user))
    assert response.status_code == 404


# ── the context handed to the route ─────────────────────────────────────────────────────────
def test_the_context_carries_the_effective_permissions(
    probe: TestClient, make_user: Callable[..., User], project: Project
) -> None:
    reviewer = make_user(role=DefaultRole.COMPLIANCE_REVIEWER)
    body = probe.get(
        f"/workspaces/{project.workspace_id}/context", headers=headers_for(reviewer)
    ).json()
    assert body["role"] == "Compliance Reviewer"
    assert body["project_id"] is None
    assert set(body["permissions"]) == DEFAULT_ROLE_PERMISSIONS[DefaultRole.COMPLIANCE_REVIEWER]
    assert body["protected_only"] == ["finding.review"]  # held for protected requirements only


def test_most_roles_have_no_protected_only_permissions(
    probe: TestClient, make_user: Callable[..., User], workspace: Workspace
) -> None:
    body = probe.get(
        f"/workspaces/{workspace.id}/context",
        headers=headers_for(make_user(role=DefaultRole.BUSINESS_ANALYST)),
    ).json()
    assert body["protected_only"] == []


# ── misuse is caught early ──────────────────────────────────────────────────────────────────
def test_an_unknown_permission_name_fails_when_the_route_is_defined() -> None:
    with pytest.raises(ValueError, match="Unknown permission"):
        require_permission("req.propos")  # typo
    with pytest.raises(ValueError, match="Unknown permission"):
        require_any_permission("view", "nope")
    with pytest.raises(ValueError, match="at least one"):
        require_any_permission()


def test_a_permission_route_without_a_scope_parameter_is_a_server_error_not_a_free_pass(
    probe: TestClient, user: User
) -> None:
    response = probe.get("/no-scope", headers=headers_for(user))
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"


def test_authenticated_only_needs_a_login_but_no_membership(
    probe: TestClient, make_user: Callable[..., User]
) -> None:
    loner = make_user(role=None)
    assert probe.get("/account", headers=headers_for(loner)).json() == {"email": loner.email}
    assert probe.get("/account").status_code == 401


# ── other modules can register their own resources ──────────────────────────────────────────
def test_modules_can_register_scope_resolvers_for_their_own_path_parameters(
    db_session: Session,
    project: Project,
    user: User,
    make_workspace: Callable[..., Workspace],
) -> None:
    widgets = {uuid.uuid4(): Scope(project.workspace_id, project.id)}
    foreign = {uuid.uuid4(): Scope(make_workspace().id)}

    def resolver(_db: Session, widget_id: uuid.UUID) -> Scope | None:
        return {**widgets, **foreign}.get(widget_id)

    register_scope_resolver("widget_id", resolver)
    try:
        app = FastAPI()
        install_exception_handlers(app)
        app.dependency_overrides[get_db] = lambda: db_session

        @app.get("/widgets/{widget_id}")
        def get_widget(
            ctx: Annotated[AccessContext, Depends(require_permission("view"))],
        ) -> dict[str, str]:
            return {"project_id": str(ctx.project_id)}

        with TestClient(app) as client:
            headers = headers_for(user)
            mine = next(iter(widgets))
            assert client.get(f"/widgets/{mine}", headers=headers).json() == {
                "project_id": str(project.id)
            }
            assert client.get(f"/widgets/{next(iter(foreign))}", headers=headers).status_code == 404
            assert client.get(f"/widgets/{uuid.uuid4()}", headers=headers).status_code == 404
    finally:
        access.SCOPE_RESOLVERS.pop("widget_id", None)


def test_registering_a_second_resolver_for_the_same_parameter_is_refused() -> None:
    with pytest.raises(ValueError, match="already registered"):
        register_scope_resolver("project_id", lambda _db, _id: None)
