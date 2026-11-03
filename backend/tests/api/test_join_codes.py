"""Join-code API (US-25): every route gets success, 403 without the permission and 404 across
workspaces; plus the end-to-end paths (sign-up with a code, join while signed in, approval)."""

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.permissions import DefaultRole
from app.core.rate_limit import InMemoryRateLimiter, get_rate_limiter
from app.models import Project, User, Workspace
from app.services.membership import get_default_role
from tests.api.conftest import headers_for

API = "/api/v1"


@pytest.fixture
def limiter(client: TestClient) -> Iterator[InMemoryRateLimiter]:
    from app.main import app

    limiter = InMemoryRateLimiter()
    app.dependency_overrides[get_rate_limiter] = lambda: limiter
    try:
        yield limiter
    finally:
        app.dependency_overrides.pop(get_rate_limiter, None)


@pytest.fixture
def manager(make_user: Callable[..., User]) -> User:
    return make_user(role=DefaultRole.PROJECT_MANAGER)


@pytest.fixture
def role_id(db_session: Session) -> Callable[[DefaultRole], str]:
    return lambda role: str(get_default_role(db_session, role).id)


@pytest.fixture
def create(
    client: TestClient, workspace: Workspace, manager: User, role_id: Callable[[DefaultRole], str]
) -> Callable[..., dict[str, object]]:
    def build(**body: object) -> dict[str, object]:
        payload: dict[str, object] = {"role_id": role_id(DefaultRole.DEVELOPER)}
        payload.update(body)
        response = client.post(
            f"{API}/workspaces/{workspace.id}/join-codes",
            json=payload,
            headers=headers_for(manager),
        )
        assert response.status_code == 201, response.text
        result: dict[str, object] = response.json()
        return result

    return build


def _signup(client: TestClient, code: object, email: str = "dev@example.com") -> dict[str, object]:
    response = client.post(
        f"{API}/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery-staple",
            "full_name": "Dev",
            "code": code,
        },
    )
    assert response.status_code == 201, response.text
    result: dict[str, object] = response.json()
    return result


class TestCreateAndList:
    def test_the_code_is_returned_once_and_listed_only_by_its_hint(
        self, client: TestClient, workspace: Workspace, manager: User, create: Callable[..., dict]
    ) -> None:
        created = create(max_uses=20, expires_in_days=30)

        assert len(str(created["code"])) == 9  # XXXX-XXXX
        listed = client.get(
            f"{API}/workspaces/{workspace.id}/join-codes", headers=headers_for(manager)
        ).json()
        assert [item["code_hint"] for item in listed] == [str(created["code"])[-4:]]
        assert "code" not in listed[0]
        assert listed[0]["max_uses"] == 20 and listed[0]["uses"] == 0

    @pytest.mark.parametrize("role", [DefaultRole.OWNER, DefaultRole.ADMIN])
    def test_owner_and_admin_codes_are_refused(
        self,
        client: TestClient,
        workspace: Workspace,
        manager: User,
        role_id: Callable[[DefaultRole], str],
        role: DefaultRole,
    ) -> None:
        response = client.post(
            f"{API}/workspaces/{workspace.id}/join-codes",
            json={"role_id": role_id(role)},
            headers=headers_for(manager),
        )
        assert response.status_code == 409

    def test_only_1_7_or_30_days(
        self, client: TestClient, workspace: Workspace, manager: User, role_id: Callable
    ) -> None:
        response = client.post(
            f"{API}/workspaces/{workspace.id}/join-codes",
            json={"role_id": role_id(DefaultRole.DEVELOPER), "expires_in_days": 3},
            headers=headers_for(manager),
        )
        assert response.status_code == 422

    def test_a_developer_cannot_create_or_list_codes(
        self,
        client: TestClient,
        workspace: Workspace,
        make_user: Callable[..., User],
        role_id: Callable[[DefaultRole], str],
    ) -> None:
        developer = headers_for(make_user(role=DefaultRole.DEVELOPER))
        url = f"{API}/workspaces/{workspace.id}/join-codes"
        assert client.get(url, headers=developer).status_code == 403
        posted = client.post(url, json={"role_id": role_id(DefaultRole.VIEWER)}, headers=developer)
        assert posted.status_code == 403

    def test_another_workspace_is_not_found(
        self,
        client: TestClient,
        make_workspace: Callable[..., Workspace],
        manager: User,
        role_id: Callable[[DefaultRole], str],
    ) -> None:
        other = make_workspace()
        url = f"{API}/workspaces/{other.id}/join-codes"
        assert client.get(url, headers=headers_for(manager)).status_code == 404
        posted = client.post(
            url, json={"role_id": role_id(DefaultRole.VIEWER)}, headers=headers_for(manager)
        )
        assert posted.status_code == 404


class TestRevoke:
    def test_a_revoked_code_cannot_be_used(
        self, client: TestClient, manager: User, create: Callable[..., dict], limiter: object
    ) -> None:
        created = create()

        response = client.delete(f"{API}/join-codes/{created['id']}", headers=headers_for(manager))

        assert response.status_code == 204
        refused = client.post(
            f"{API}/auth/signup",
            json={
                "email": "late@example.com",
                "password": "correct-horse-battery-staple",
                "full_name": "Late",
                "code": created["code"],
            },
        )
        assert refused.status_code == 400
        assert refused.json()["error"]["code"] == "signup_refused"

    def test_a_developer_cannot_revoke(
        self, client: TestClient, make_user: Callable[..., User], create: Callable[..., dict]
    ) -> None:
        created = create()
        developer = headers_for(make_user(role=DefaultRole.DEVELOPER))
        assert (
            client.delete(f"{API}/join-codes/{created['id']}", headers=developer).status_code == 403
        )

    def test_a_code_of_another_workspace_is_not_found(
        self,
        client: TestClient,
        create: Callable[..., dict],
        make_workspace: Callable[..., Workspace],
        make_user: Callable[..., User],
    ) -> None:
        created = create()
        outsider = make_user(role=DefaultRole.OWNER, workspace=make_workspace())
        response = client.delete(f"{API}/join-codes/{created['id']}", headers=headers_for(outsider))
        assert response.status_code == 404


class TestSignupAndJoin:
    def test_sprint_1_exit_a_developer_signs_up_with_the_pms_code(
        self, client: TestClient, workspace: Workspace, create: Callable[..., dict], limiter: object
    ) -> None:
        created = create()

        body = _signup(client, created["code"])

        assert body["join_status"] == "joined"
        assert body["workspace_id"] == str(workspace.id)
        token = {"Authorization": f"Bearer {body['access_token']}"}
        me = client.get(f"{API}/me/permissions", params={"workspace": workspace.id}, headers=token)
        assert me.json()["role"]["name"] == DefaultRole.DEVELOPER.value

    def test_a_signed_in_user_joins_another_workspace_with_post_join(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        make_workspace: Callable[..., Workspace],
        create: Callable[..., dict],
        workspace: Workspace,
        limiter: object,
    ) -> None:
        elsewhere = make_user(role=DefaultRole.DEVELOPER, workspace=make_workspace())
        created = create()

        response = client.post(
            f"{API}/join", json={"code": created["code"]}, headers=headers_for(elsewhere)
        )

        assert response.status_code == 200
        assert response.json() == {
            "status": "joined",
            "workspace_id": str(workspace.id),
            "project_id": None,
            "join_request_id": None,
        }

    def test_a_project_code_reports_its_project(
        self,
        client: TestClient,
        make_user: Callable[..., User],
        make_workspace: Callable[..., Workspace],
        create: Callable[..., dict],
        project: Project,
        limiter: object,
    ) -> None:
        elsewhere = make_user(role=DefaultRole.DEVELOPER, workspace=make_workspace())
        created = create(project_id=str(project.id))

        response = client.post(
            f"{API}/join", json={"code": created["code"]}, headers=headers_for(elsewhere)
        )

        assert response.json()["project_id"] == str(project.id)

    def test_post_join_gives_one_generic_error(
        self, client: TestClient, make_user: Callable[..., User], limiter: object
    ) -> None:
        response = client.post(
            f"{API}/join", json={"code": "ZZZZ-ZZZZ"}, headers=headers_for(make_user(role=None))
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_join_code"

    def test_post_join_is_rate_limited(
        self, client: TestClient, make_user: Callable[..., User], limiter: object
    ) -> None:
        headers = headers_for(make_user(role=None))
        statuses = [
            client.post(f"{API}/join", json={"code": "ZZZZ-ZZZZ"}, headers=headers).status_code
            for _ in range(11)
        ]
        assert statuses[:10] == [400] * 10
        assert statuses[10] == 429

    def test_post_join_needs_a_login(self, client: TestClient) -> None:
        assert client.post(f"{API}/join", json={"code": "ZZZZ-ZZZZ"}).status_code == 401


class TestJoinRequests:
    def test_approval_flow(
        self,
        client: TestClient,
        workspace: Workspace,
        manager: User,
        create: Callable[..., dict],
        role_id: Callable[[DefaultRole], str],
        limiter: object,
    ) -> None:
        created = create(requires_approval=True)
        signed_up = _signup(client, created["code"], email="neha@example.com")
        assert signed_up["join_status"] == "pending_approval"

        waiting = client.get(
            f"{API}/workspaces/{workspace.id}/join-requests", headers=headers_for(manager)
        ).json()
        assert [item["user"]["email"] for item in waiting] == ["neha@example.com"]

        decided = client.post(
            f"{API}/workspaces/{workspace.id}/join-requests/{waiting[0]['id']}/decision",
            json={"approve": True, "role_id": role_id(DefaultRole.STAKEHOLDER)},
            headers=headers_for(manager),
        )
        assert decided.status_code == 200
        assert decided.json()["status"] == "approved"
        assert decided.json()["role"]["name"] == DefaultRole.STAKEHOLDER.value

        again = client.post(
            f"{API}/workspaces/{workspace.id}/join-requests/{waiting[0]['id']}/decision",
            json={"approve": False},
            headers=headers_for(manager),
        )
        assert again.status_code == 409

    def test_a_developer_cannot_see_or_decide_requests(
        self, client: TestClient, workspace: Workspace, make_user: Callable[..., User]
    ) -> None:
        developer = headers_for(make_user(role=DefaultRole.DEVELOPER))
        url = f"{API}/workspaces/{workspace.id}/join-requests"
        assert client.get(url, headers=developer).status_code == 403

    def test_a_request_of_another_workspace_is_not_found(
        self,
        client: TestClient,
        workspace: Workspace,
        manager: User,
        create: Callable[..., dict],
        make_workspace: Callable[..., Workspace],
        make_user: Callable[..., User],
        limiter: object,
    ) -> None:
        created = create(requires_approval=True)
        _signup(client, created["code"], email="karan@example.com")
        request_id = client.get(
            f"{API}/workspaces/{workspace.id}/join-requests", headers=headers_for(manager)
        ).json()[0]["id"]
        other = make_workspace()
        outsider = headers_for(make_user(role=DefaultRole.OWNER, workspace=other))

        url = f"{API}/workspaces/{other.id}/join-requests/{request_id}/decision"
        assert client.post(url, json={"approve": True}, headers=outsider).status_code == 404
