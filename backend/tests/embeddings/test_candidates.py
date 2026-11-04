"""Candidate pairs (Heet — US-05, FR-09, FR-10): top-k neighbours above the threshold, stored once,
never re-classified for unchanged versions, and never across projects."""

import uuid
from collections.abc import Callable

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.celery_app import celery_app
from app.embeddings.candidates import generate_candidates
from app.embeddings.model import HashingEmbedder
from app.embeddings.store import embed_document
from app.embeddings.tasks import generate_candidates_task
from app.models import (
    CandidatePair,
    ClassificationStatus,
    Document,
    DocumentFormat,
    Project,
    Requirement,
    RequirementState,
    User,
)

TIMEOUT_A = "API requests shall time out after 2 seconds."
TIMEOUT_B = "API requests may take up to 10 seconds before they time out."
UNRELATED = "Invoices are exported as PDF files every month."


@pytest.fixture
def add_document(db_session: Session, user: User) -> Callable[..., list[Requirement]]:
    def build(project: Project, *bodies: str) -> list[Requirement]:
        document = Document(
            workspace_id=project.workspace_id,
            project_id=project.id,
            uploaded_by=user.id,
            filename="srs.docx",
            format=DocumentFormat.DOCX,
            size_bytes=1,
            sha256=uuid.uuid4().hex * 2,
            storage_path="srs.docx",
        )
        db_session.add(document)
        db_session.flush()
        rows = [
            Requirement(document_id=document.id, project_id=project.id, body=body, order_index=i)
            for i, body in enumerate(bodies)
        ]
        db_session.add_all(rows)
        db_session.commit()
        embed_document(db_session, document.id, HashingEmbedder())
        return rows

    return build


def pairs(db: Session) -> list[CandidatePair]:
    return list(db.scalars(select(CandidatePair)))


def test_similar_requirements_become_one_canonical_pending_pair(
    db_session: Session, project: Project, add_document: Callable[..., list[Requirement]]
) -> None:
    a, b, _ = add_document(project, TIMEOUT_A, TIMEOUT_B, UNRELATED)

    result = generate_candidates(db_session, project.id, threshold=0.3)

    (pair,) = pairs(db_session)
    assert (pair.requirement_a_id, pair.requirement_b_id) == CandidatePair.ordered(a.id, b.id)
    assert pair.classification_status is ClassificationStatus.PENDING
    assert 0.3 <= pair.similarity_score <= 1
    assert result.pending == [pair.id] and result.created == 1


def test_the_threshold_and_k_limit_the_pairs(
    db_session: Session, project: Project, add_document: Callable[..., list[Requirement]]
) -> None:
    add_document(project, TIMEOUT_A, TIMEOUT_B, UNRELATED)

    assert generate_candidates(db_session, project.id, threshold=0.99).pending == []
    assert pairs(db_session) == []
    loose = generate_candidates(db_session, project.id, threshold=-1, k=1)
    assert 1 <= len(loose.pending) <= 3  # every requirement keeps only its best neighbour


def test_an_unchanged_classified_pair_is_not_sent_again_but_an_edited_one_is(
    db_session: Session, project: Project, add_document: Callable[..., list[Requirement]]
) -> None:
    a, b, _ = add_document(project, TIMEOUT_A, TIMEOUT_B, UNRELATED)
    generate_candidates(db_session, project.id, threshold=0.3)
    (pair,) = pairs(db_session)
    pair.classification_status = ClassificationStatus.DONE
    pair.a_version, pair.b_version = 1, 1
    db_session.commit()

    again = generate_candidates(db_session, project.id, threshold=0.3)
    assert again.pending == [] and again.unchanged == 1

    b.current_version = 2  # the text changed through a merged change request (S4)
    db_session.commit()
    edited = generate_candidates(db_session, project.id, threshold=0.3)
    assert edited.pending == [pair.id] and edited.reopened == 1
    db_session.refresh(pair)
    assert pair.classification_status is ClassificationStatus.PENDING


def test_a_failed_pair_is_retried(
    db_session: Session, project: Project, add_document: Callable[..., list[Requirement]]
) -> None:
    add_document(project, TIMEOUT_A, TIMEOUT_B)
    generate_candidates(db_session, project.id, threshold=0.3)
    (pair,) = pairs(db_session)
    pair.classification_status, pair.attempts, pair.last_error = (
        ClassificationStatus.FAILED,
        3,
        "invalid_output",
    )
    db_session.commit()

    assert generate_candidates(db_session, project.id, threshold=0.3).pending == [pair.id]
    db_session.refresh(pair)
    assert (pair.attempts, pair.last_error) == (0, None)


def test_rejected_and_deprecated_requirements_are_not_paired(
    db_session: Session, project: Project, add_document: Callable[..., list[Requirement]]
) -> None:
    a, _ = add_document(project, TIMEOUT_A, TIMEOUT_B)
    a.state = RequirementState.DEPRECATED
    db_session.commit()

    assert generate_candidates(db_session, project.id, threshold=0.3).pending == []


def test_pairs_never_cross_projects(
    db_session: Session,
    make_project: Callable[..., Project],
    add_document: Callable[..., list[Requirement]],
) -> None:
    first, second = make_project(), make_project()
    add_document(first, TIMEOUT_A)
    add_document(second, TIMEOUT_B)

    assert generate_candidates(db_session, first.id, threshold=-1).pending == []
    assert pairs(db_session) == []


def test_scope_can_be_one_documents_requirements(
    db_session: Session, project: Project, add_document: Callable[..., list[Requirement]]
) -> None:
    (old,) = add_document(project, TIMEOUT_A)
    (new,) = add_document(project, TIMEOUT_B)

    result = generate_candidates(db_session, project.id, requirement_ids=[new.id], threshold=0.3)

    (pair,) = pairs(db_session)
    assert {pair.requirement_a_id, pair.requirement_b_id} == {old.id, new.id}
    assert result.pending == [pair.id]


def test_the_task_is_named_and_routed_to_the_analysis_queue() -> None:
    assert generate_candidates_task.name == "embeddings.generate_candidates"
    route = celery_app.amqp.router.route({}, "embeddings.generate_candidates")
    assert route["queue"].name == "analysis"
