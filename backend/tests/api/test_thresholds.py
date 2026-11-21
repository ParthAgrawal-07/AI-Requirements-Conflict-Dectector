"""Threshold tuning (Heet — US-06): preview before saving, re-analyse without re-uploading."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.permissions import DefaultRole
from app.embeddings.incremental import embed_requirements
from app.embeddings.model import HashingEmbedder
from app.models import (
    Document,
    DocumentStatus,
    Finding,
    FindingCategory,
    Project,
    ProjectStatus,
    Requirement,
    User,
    Workspace,
)
from app.services import analysis_orchestrator
from tests.api.conftest import headers_for


@pytest.fixture
def manager(make_user: Callable[..., User]) -> User:
    return make_user(role=DefaultRole.PROJECT_MANAGER)


@pytest.fixture
def requirements(
    db_session: Session, make_requirement: Callable[..., Requirement]
) -> list[Requirement]:
    rows = [
        make_requirement(body, source_req_id=f"REQ-{n}", order_index=n)
        for n, body in enumerate(
            [
                "Sessions shall time out after 30 minutes.",
                "Sessions shall time out after 5 minutes.",
                "Invoices shall be exported as PDF.",
                "The dashboard shall show open findings.",
            ],
            start=1,
        )
    ]
    embed_requirements(db_session, [r.id for r in rows], HashingEmbedder())
    return rows


def preview(client: TestClient, project: Project, user: User, **params: float) -> dict[str, object]:
    response = client.get(
        f"/api/v1/projects/{project.id}/thresholds/preview",
        params=params,
        headers=headers_for(user),
    )
    assert response.status_code == 200, response.text
    body: dict[str, object] = response.json()
    return body


def test_a_lower_threshold_selects_more_pairs(
    client: TestClient, project: Project, manager: User, requirements: list[Requirement]
) -> None:
    low = preview(client, project, manager, similarity=0.0)["similarity"]
    high = preview(client, project, manager, similarity=0.99)["similarity"]

    assert isinstance(low, dict) and isinstance(high, dict)
    assert low["pairs_compared"] == high["pairs_compared"] == 6
    assert low["pairs_above"] == 6 and high["pairs_above"] < 6
    assert low["below"] == [] and len(low["above"]) == 5
    assert high["current"] == project.similarity_threshold
    for example in [*high["above"], *high["below"]]:
        assert example["a_label"].startswith("REQ-") and -1 <= example["similarity"] <= 1


def test_examples_say_what_was_found_on_the_pair(
    client: TestClient,
    db_session: Session,
    project: Project,
    manager: User,
    requirements: list[Requirement],
) -> None:
    from app.models import CandidatePair

    first, second = CandidatePair.ordered(requirements[0].id, requirements[1].id)
    pair = CandidatePair(requirement_a_id=first, requirement_b_id=second, similarity_score=0.9)
    db_session.add(pair)
    db_session.flush()
    db_session.add(
        Finding(
            project_id=project.id,
            candidate_pair_id=pair.id,
            confidence=0.4,
            rationale="r",
            category=FindingCategory.CONFLICTING,
            original_ai_output={},
        )  # fmt: skip
    )
    db_session.commit()

    body = preview(client, project, manager, similarity=0.6, confidence=0.5)
    similarity, confidence = body["similarity"], body["confidence"]
    assert isinstance(similarity, dict) and isinstance(confidence, dict)
    # Six pairs, up to five examples on each side of the threshold: every pair is shown.
    flagged = [e for e in [*similarity["above"], *similarity["below"]] if e["finding"]]
    assert [(e["finding"], e["found_by"]) for e in flagged] == [("Conflicting", "ai")]
    assert (confidence["confident"], confidence["low_confidence"]) == (0, 1)


def test_preview_needs_project_manage(
    client: TestClient, project: Project, make_user: Callable[..., User]
) -> None:
    developer = make_user(role=DefaultRole.DEVELOPER)
    response = client.get(
        f"/api/v1/projects/{project.id}/thresholds/preview", headers=headers_for(developer)
    )
    assert response.status_code == 403


def test_another_workspace_is_404(
    client: TestClient,
    make_project: Callable[..., Project],
    make_workspace: Callable[..., Workspace],
    manager: User,
) -> None:
    other = make_project(workspace=make_workspace())
    for method, path in (("GET", "thresholds/preview"), ("POST", "reanalyse")):
        response = client.request(
            method, f"/api/v1/projects/{other.id}/{path}", headers=headers_for(manager)
        )
        assert response.status_code == 404


def test_reanalyse_queues_every_document_again(
    client: TestClient,
    db_session: Session,
    project: Project,
    manager: User,
    requirements: list[Requirement],
    followups: list[tuple[str, list[str]]],
) -> None:
    document = db_session.get(Document, requirements[0].document_id)
    assert document is not None
    document.status = DocumentStatus.DONE
    db_session.commit()

    response = client.post(f"/api/v1/projects/{project.id}/reanalyse", headers=headers_for(manager))

    assert response.status_code == 202 and response.json() == {"queued": 1}
    assert followups == [(analysis_orchestrator.RUN_DOCUMENT, [str(document.id)])]


def test_reanalyse_waits_for_the_context(
    client: TestClient, make_project: Callable[..., Project], manager: User
) -> None:
    in_setup = make_project(status=ProjectStatus.SETUP)
    response = client.post(
        f"/api/v1/projects/{in_setup.id}/reanalyse", headers=headers_for(manager)
    )
    assert response.status_code == 409
