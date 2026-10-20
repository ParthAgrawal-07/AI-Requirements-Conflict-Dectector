"""Security invariants over *every* API route (US-27, FR-37, NFR-11).

These tests inspect the real application, so they cover routes teammates add later without
anyone remembering to extend a test list:

* every ``/api/v1`` route states who may call it — exactly one access declaration;
* the set of public and "any signed-in user" routes is a short, explicit allow-list;
* a route that needs a permission has a path parameter the access layer can resolve to a
  tenant (otherwise it would fail at request time);
* state-changing routes are never guarded by ``view`` alone.
"""

from collections.abc import Iterator
from typing import Any

from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute

from app.core.auth import AccessDeclaration, access_declaration
from app.core.permissions import PERMISSIONS
from app.services.access import SCOPE_RESOLVERS

PUBLIC = {
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/signup"),
}
# Any signed-in user, no workspace involved. Keep this list short and think before extending it.
AUTHENTICATED_ONLY = {
    ("GET", "/api/v1/auth/me"),
    ("GET", "/api/v1/me/permissions"),
    ("GET", "/api/v1/workspaces"),
    ("POST", "/api/v1/workspaces"),
}


# Routes that admit holders of a *protected-only* grant and check the requirement themselves
# (``allow_protected_only=True``). None yet — the review guard for US-10 (Sprint 3) will be the first.
# Adding one here is a conscious decision: the handler must call
# ``ctx.can(permission, protected_requirement=requirement.is_protected)``.
PROTECTED_ONLY_OPT_INS: set[tuple[str, str]] = set()


def _declarations(dependant: Dependant) -> list[AccessDeclaration]:
    found: list[AccessDeclaration] = []
    for sub in dependant.dependencies:
        declaration = access_declaration(sub.call)
        if declaration is not None:
            found.append(declaration)
        found.extend(_declarations(sub))
    return found


def _flatten(routes: Any) -> Iterator[Any]:
    """Every concrete route, whichever way this FastAPI version nests included routers.

    Older releases copy included routes into ``app.routes``; newer ones keep a lazy
    ``_IncludedRouter`` whose ``effective_route_contexts()`` yields objects with the same
    ``path`` / ``methods`` / ``dependant`` / ``param_convertors`` attributes as an ``APIRoute``.
    """
    for route in routes:
        if isinstance(route, APIRoute):
            yield route
        elif hasattr(route, "effective_route_contexts"):
            yield from route.effective_route_contexts()
        elif hasattr(route, "routes"):  # a Mount
            yield from _flatten(route.routes)


def _api_routes() -> list[tuple[str, Any]]:
    from app.main import app

    routes = [
        (method, route)
        for route in _flatten(app.routes)
        if getattr(route, "path", "").startswith("/api/v1") and getattr(route, "dependant", None)
        for method in sorted(route.methods - {"HEAD", "OPTIONS"})
    ]
    assert routes, "no API routes found — the test is not looking at the real app"
    return routes


def test_every_api_route_declares_exactly_one_kind_of_access() -> None:
    problems = [
        f"{method} {route.path}: {len(declarations)} declarations"
        for method, route in _api_routes()
        if len(declarations := _declarations(route.dependant)) != 1
    ]
    assert not problems, (
        "Every route needs exactly one of public_route / authenticated_only / "
        "require_permission(...) / require_any_permission(...):\n  " + "\n  ".join(problems)
    )


def test_the_public_routes_are_exactly_the_allow_list() -> None:
    public = {
        (method, route.path)
        for method, route in _api_routes()
        if _declarations(route.dependant)[0].kind == "public"
    }
    assert public == PUBLIC


def test_the_authenticated_only_routes_are_exactly_the_allow_list() -> None:
    authenticated = {
        (method, route.path)
        for method, route in _api_routes()
        if _declarations(route.dependant)[0].kind == "authenticated"
    }
    assert authenticated == AUTHENTICATED_ONLY


def test_permission_routes_name_catalogue_permissions_and_a_resolvable_scope() -> None:
    problems: list[str] = []
    for method, route in _api_routes():
        (declaration,) = _declarations(route.dependant)
        if declaration.kind not in ("permission", "any_permission"):
            continue
        unknown = [name for name in declaration.permissions if name not in PERMISSIONS]
        if unknown:
            problems.append(f"{method} {route.path}: unknown permission(s) {unknown}")
        if not set(route.param_convertors) & set(SCOPE_RESOLVERS):
            problems.append(
                f"{method} {route.path}: no path parameter among {sorted(SCOPE_RESOLVERS)} — "
                "the tenant cannot be resolved"
            )
    assert not problems, "\n".join(problems)


def test_only_listed_routes_admit_protected_only_grants() -> None:
    opted_in = {
        (method, route.path)
        for method, route in _api_routes()
        if _declarations(route.dependant)[0].allow_protected_only
    }
    assert opted_in == PROTECTED_ONLY_OPT_INS, (
        "A route that sets allow_protected_only=True must check the requirement itself "
        "(ctx.can(..., protected_requirement=...)) and be added to PROTECTED_ONLY_OPT_INS"
    )


def test_state_changing_routes_need_more_than_view() -> None:
    weak = [
        f"{method} {route.path}"
        for method, route in _api_routes()
        if method in {"POST", "PUT", "PATCH", "DELETE"}
        and (declaration := _declarations(route.dependant)[0]).kind
        in ("permission", "any_permission")
        and set(declaration.permissions) == {"view"}
    ]
    assert not weak, f"These change data but only require `view`: {weak}"


def test_the_sprint_1_routes_are_all_registered() -> None:
    """A guard against a router silently dropping out of ``api_router``."""
    registered = {(method, route.path) for method, route in _api_routes()}
    expected = {
        ("POST", "/api/v1/auth/signup"),
        ("GET", "/api/v1/me/permissions"),
        ("POST", "/api/v1/workspaces"),
        ("GET", "/api/v1/workspaces"),
        ("GET", "/api/v1/workspaces/{workspace_id}"),
        ("POST", "/api/v1/workspaces/{workspace_id}/projects"),
        ("GET", "/api/v1/workspaces/{workspace_id}/projects"),
        ("GET", "/api/v1/projects/{project_id}"),
        ("PATCH", "/api/v1/projects/{project_id}"),
        ("POST", "/api/v1/projects/{project_id}/documents"),
        ("GET", "/api/v1/projects/{project_id}/documents"),
        ("GET", "/api/v1/documents/{document_id}"),
        ("GET", "/api/v1/projects/{project_id}/requirements"),
    }
    assert expected <= registered, expected - registered


def test_the_detector_itself_notices_a_route_without_a_declaration() -> None:
    """A test that can never fail proves nothing: check it on throw-away routes."""
    from typing import Annotated

    from fastapi import Depends, FastAPI

    from app.core.auth import authenticated_only, require_permission

    app = FastAPI()

    @app.get("/naked")
    def naked() -> None: ...

    @app.get("/w/{workspace_id}")
    def guarded(_: Annotated[object, Depends(require_permission("view"))]) -> None: ...

    @app.get("/me")
    def mine(_: Annotated[object, Depends(authenticated_only)]) -> None: ...

    by_path = {
        route.path: _declarations(route.dependant)
        for route in _flatten(app.routes)
        if hasattr(route, "dependant")
    }
    assert by_path["/naked"] == []
    assert [d.kind for d in by_path["/w/{workspace_id}"]] == ["permission"]
    assert [d.kind for d in by_path["/me"]] == ["authenticated"]
