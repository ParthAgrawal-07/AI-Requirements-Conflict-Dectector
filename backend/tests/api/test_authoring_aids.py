"""Authoring aids (Keval — US-51): lint, pre-flight dry run and AI wording over the API."""

import json
from collections.abc import Callable, Iterator
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.classification.budget import CountingBudget, get_budget_guard
from app.classification.llm_client import FakeTransport, LLMClient, get_llm_client
from app.core import rate_limit
from app.core.permissions import DefaultRole
from app.core.rate_limit import InMemoryRateLimiter, get_rate_limiter
from app.embeddings.incremental import embed_requirements
from app.embeddings.model import HashingEmbedder, get_embedder
from app.models import (
    AnalysisRun,
    CandidatePair,
    Finding,
    Project,
    ProjectStatus,
    Requirement,
    RequirementState,
    User,
    Workspace,
)
from tests.analysis_helpers import pair_reply, single_reply
from tests.api.conftest import headers_for

DRAFT = "The app shall time out sessions after 5 minutes."


class Setup:
    def __init__(self) -> None:
        self.transport = FakeTransport([])
        self.budget = CountingBudget(100)
        self.llm: LLMClient | None = LLMClient(self.transport, self.budget)


@pytest.fixture
def setup() -> Iterator[Setup]:
    from app.main import app

    state = Setup()
    limiter = InMemoryRateLimiter()
    app.dependency_overrides[get_embedder] = HashingEmbedder
    app.dependency_overrides[get_llm_client] = lambda: state.llm
    app.dependency_overrides[get_budget_guard] = lambda: state.budget
    app.dependency_overrides[get_rate_limiter] = lambda: limiter
    yield state
    for dependency in (get_embedder, get_llm_client, get_budget_guard, get_rate_limiter):
        app.dependency_overrides.pop(dependency, None)


@pytest.fixture
def writer(make_user: Callable[..., User]) -> User:
    return make_user(role=DefaultRole.DEVELOPER)


@pytest.fixture
def baseline(
    db_session: Session, project: Project, make_requirement: Callable[..., Requirement]
) -> Requirement:
    project.similarity_threshold = 0.0  # the hashing embedder is crude; compare with everything
    requirement = make_requirement(
        "Sessions shall time out after 30 minutes.",
        source_req_id="REQ-012",
        state=RequirementState.APPROVED,
    )
    embed_requirements(db_session, [requirement.id], HashingEmbedder())
    return requirement


def url(project: Project, aid: str) -> str:
    return f"/api/v1/projects/{project.id}/{aid}"


# ── lint ────────────────────────────────────────────────────────────────────────────────────
def test_the_catalogue_is_served_to_any_signed_in_user(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    response = client.get("/api/v1/lint/catalogue", headers=headers_for(make_user(role=None)))
    assert response.status_code == 200
    assert response.json()["version"] == 2


def test_server_lint(client: TestClient, project: Project, writer: User) -> None:
    response = client.post(
        url(project, "lint"), json={"text": "It shall be fast etc."}, headers=headers_for(writer)
    )
    assert response.status_code == 200
    body = response.json()
    assert {"vague.speed", "unbounded.etc", "actor.missing"} <= {
        i["rule_id"] for i in body["issues"]
    }
    assert body["quality"] in {"fair", "poor"}


def test_lint_needs_req_propose(
    client: TestClient, project: Project, make_user: Callable[..., User]
) -> None:
    viewer = make_user(role=DefaultRole.VIEWER)
    response = client.post(url(project, "lint"), json={"text": "x"}, headers=headers_for(viewer))
    assert response.status_code == 403


def test_another_workspace_is_404(
    client: TestClient,
    make_project: Callable[..., Project],
    make_workspace: Callable[..., Workspace],
    writer: User,
) -> None:
    other = make_project(workspace=make_workspace())
    for aid in ("lint", "preflight", "improve-wording"):
        response = client.post(url(other, aid), json={"text": "x"}, headers=headers_for(writer))
        assert response.status_code == 404, aid


# ── pre-flight ──────────────────────────────────────────────────────────────────────────────
def test_preflight_finds_the_likely_conflict_and_stores_nothing(
    client: TestClient,
    db_session: Session,
    project: Project,
    writer: User,
    baseline: Requirement,
    setup: Setup,
) -> None:
    setup.transport.replies.extend([pair_reply("Conflicting", 0.9), single_reply()])
    before = {
        model: db_session.scalar(select(func.count()).select_from(model))
        for model in (Finding, CandidatePair, AnalysisRun, Requirement)
    }

    response = client.post(url(project, "preflight"), json={"text": DRAFT},
                           headers=headers_for(writer))  # fmt: skip

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "done" and body["label"] == "AI"
    assert [(f["category"], f["label"]) for f in body["likely_findings"]] == [
        ("Conflicting", "REQ-012")
    ]
    assert body["compared"] == [str(baseline.id)]
    assert body["llm_calls"] == 2
    assert body["budget"] == {"remaining": 98, "monthly": project.llm_budget_monthly_calls}
    after = {
        model: db_session.scalar(select(func.count()).select_from(model))
        for model in (Finding, CandidatePair, AnalysisRun, Requirement)
    }
    assert after == before
    assert "DRAFT" in setup.transport.calls[0][1]


def test_preflight_is_limited_by_the_budget(
    client: TestClient, project: Project, writer: User, baseline: Requirement, setup: Setup
) -> None:
    setup.budget = CountingBudget(0)
    setup.llm = LLMClient(setup.transport, setup.budget)

    body = client.post(
        url(project, "preflight"), json={"text": DRAFT}, headers=headers_for(writer)
    ).json()

    assert body["status"] == "budget"
    assert body["likely_findings"] == [] and body["budget"]["remaining"] == 0
    assert setup.transport.calls == []


def test_preflight_without_a_model_still_lints(
    client: TestClient, project: Project, writer: User, setup: Setup
) -> None:
    setup.llm = None
    body = client.post(
        url(project, "preflight"), json={"text": "It shall be fast."}, headers=headers_for(writer)
    ).json()
    assert body["status"] == "unavailable"
    assert body["lint"]["issues"]


def test_preflight_waits_for_the_project_context(
    client: TestClient,
    make_project: Callable[..., Project],
    writer: User,
    setup: Setup,
) -> None:
    in_setup = make_project(status=ProjectStatus.SETUP)
    response = client.post(
        url(in_setup, "preflight"), json={"text": DRAFT}, headers=headers_for(writer)
    )
    assert response.status_code == 409


def test_preflight_is_rate_limited(
    client: TestClient, project: Project, writer: User, setup: Setup, monkeypatch: pytest.MonkeyPatch
) -> None:
    # All seven requests must hit the same fixed rate-limit window.
    monkeypatch.setattr(rate_limit, "time", SimpleNamespace(time=lambda: 120.0))
    setup.llm = None
    codes = [
        client.post(url(project, "preflight"), json={"text": DRAFT},
                    headers=headers_for(writer)).status_code
        for _ in range(7)
    ]  # fmt: skip
    assert codes[:6] == [200] * 6 and codes[6] == 429


# ── improve wording ─────────────────────────────────────────────────────────────────────────
def test_improve_wording_returns_original_and_proposed(
    client: TestClient, project: Project, writer: User, setup: Setup
) -> None:
    proposed = "The app shall display the account summary within [TBD — confirm]."
    setup.transport.replies.append(
        json.dumps(
            {
                "rewrite": proposed,
                "template": "ubiquitous",
                "changes": ["Measurable"],
                "tbd_slots": ["load time"],
            }
        )  # fmt: skip
    )
    response = client.post(
        url(project, "improve-wording"),
        json={"text": "The app should load the summary quickly."},
        headers=headers_for(writer),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["original"] == "The app should load the summary quickly."
    assert body["proposed"] == proposed and body["label"] == "AI"


def test_improve_wording_without_a_model_or_budget(
    client: TestClient, project: Project, writer: User, setup: Setup
) -> None:
    setup.llm = None
    response = client.post(url(project, "improve-wording"), json={"text": DRAFT},
                           headers=headers_for(writer))  # fmt: skip
    assert (response.status_code, response.json()["error"]["code"]) == (503, "ai_unavailable")

    setup.budget = CountingBudget(0)
    setup.llm = LLMClient(FakeTransport(["{}"]), setup.budget)
    response = client.post(url(project, "improve-wording"), json={"text": DRAFT},
                           headers=headers_for(writer))  # fmt: skip
    assert (response.status_code, response.json()["error"]["code"]) == (429, "budget_exhausted")
