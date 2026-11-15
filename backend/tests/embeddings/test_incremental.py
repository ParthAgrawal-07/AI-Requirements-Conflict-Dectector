"""Incremental retrieval (Heet — US-31, FR-56, FR-83): one requirement or one draft against the
project's baseline and open proposals, never another project's, and fast enough for live use."""

import time
import uuid
from collections.abc import Callable

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.embeddings.incremental import (
    candidates_for_requirement,
    embed_requirements,
    similar_to_text,
)
from app.embeddings.model import HashingEmbedder
from app.embeddings.store import embed_document
from app.models import (
    CandidatePair,
    ClassificationStatus,
    Document,
    DocumentFormat,
    Embedding,
    Project,
    Requirement,
    RequirementOrigin,
    RequirementState,
    User,
)

TIMEOUT = "API requests shall time out after 2 seconds."
TIMEOUT_POST = "API requests shall time out after 10 seconds."
UNRELATED = "Invoices are exported as PDF files every month."

MakeBaseline = Callable[..., list[Requirement]]


@pytest.fixture
def embedder() -> HashingEmbedder:
    return HashingEmbedder()


@pytest.fixture
def baseline(db_session: Session, user: User, embedder: HashingEmbedder) -> MakeBaseline:
    """Extracted requirements of one document in ``project``, embedded."""

    def build(
        project: Project, *bodies: str, state: RequirementState = RequirementState.APPROVED
    ) -> list[Requirement]:
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
            Requirement(
                document_id=document.id,
                project_id=project.id,
                body=body,
                order_index=i,
                state=state,
                source_req_id=f"REQ-{i + 1:03d}",
            )
            for i, body in enumerate(bodies)
        ]
        db_session.add_all(rows)
        db_session.commit()
        embed_document(db_session, document.id, embedder)
        return rows

    return build


@pytest.fixture
def post(db_session: Session) -> Callable[[Project, str], Requirement]:
    """A posted requirement: no document, origin ``post``, not embedded yet."""

    def build(project: Project, body: str) -> Requirement:
        requirement = Requirement(
            project_id=project.id, document_id=None, origin=RequirementOrigin.POST, body=body
        )
        db_session.add(requirement)
        db_session.commit()
        return requirement

    return build


def pending_pairs(db: Session, requirement: Requirement) -> list[CandidatePair]:
    return list(
        db.scalars(
            select(CandidatePair).where(
                (CandidatePair.requirement_a_id == requirement.id)
                | (CandidatePair.requirement_b_id == requirement.id),
                CandidatePair.classification_status == ClassificationStatus.PENDING,
            )
        )
    )


def test_a_post_is_embedded_and_paired_with_its_baseline_neighbour(
    db_session: Session,
    project: Project,
    baseline: MakeBaseline,
    post: Callable[[Project, str], Requirement],
    embedder: HashingEmbedder,
) -> None:
    approved, _unrelated = baseline(project, TIMEOUT, UNRELATED)
    new = post(project, TIMEOUT_POST)

    result = candidates_for_requirement(db_session, new, embedder, k=5)

    assert db_session.scalar(select(Embedding).where(Embedding.requirement_id == new.id))
    paired = {(p.requirement_a_id, p.requirement_b_id) for p in pending_pairs(db_session, new)}
    assert paired == {CandidatePair.ordered(new.id, approved.id)}
    assert result.pending and result.created == 1


def test_open_proposals_are_neighbours_but_rejected_and_deprecated_are_not(
    db_session: Session,
    project: Project,
    baseline: MakeBaseline,
    post: Callable[[Project, str], Requirement],
    embedder: HashingEmbedder,
) -> None:
    (proposal,) = baseline(project, TIMEOUT, state=RequirementState.UNDER_REVIEW)
    (rejected,) = baseline(project, TIMEOUT, state=RequirementState.REJECTED)
    (deprecated,) = baseline(project, TIMEOUT, state=RequirementState.DEPRECATED)
    new = post(project, TIMEOUT_POST)

    candidates_for_requirement(db_session, new, embedder, k=5)

    others = {
        p.requirement_a_id if p.requirement_b_id == new.id else p.requirement_b_id
        for p in pending_pairs(db_session, new)
    }
    assert proposal.id in others
    assert rejected.id not in others and deprecated.id not in others


def test_rejected_look_alikes_do_not_crowd_out_the_real_neighbours(
    db_session: Session,
    project: Project,
    baseline: MakeBaseline,
    post: Callable[[Project, str], Requirement],
    embedder: HashingEmbedder,
) -> None:
    baseline(project, *[TIMEOUT_POST] * 6, state=RequirementState.REJECTED)
    (approved,) = baseline(project, TIMEOUT)
    new = post(project, TIMEOUT_POST)

    candidates_for_requirement(db_session, new, embedder, k=2)

    assert len(pending_pairs(db_session, new)) == 1
    assert pending_pairs(db_session, new)[0].requirement_a_id in (approved.id, new.id)


def test_another_projects_requirements_are_never_candidates(
    db_session: Session,
    project: Project,
    make_project: Callable[..., Project],
    baseline: MakeBaseline,
    post: Callable[[Project, str], Requirement],
    embedder: HashingEmbedder,
) -> None:
    other = make_project()
    baseline(other, TIMEOUT)
    new = post(project, TIMEOUT_POST)

    result = candidates_for_requirement(db_session, new, embedder)

    assert result.pending == [] and pending_pairs(db_session, new) == []


def test_analysing_the_same_text_twice_costs_nothing_the_second_time(
    db_session: Session,
    project: Project,
    baseline: MakeBaseline,
    post: Callable[[Project, str], Requirement],
    embedder: HashingEmbedder,
) -> None:
    baseline(project, TIMEOUT)
    new = post(project, TIMEOUT_POST)
    first = candidates_for_requirement(db_session, new, embedder)
    for pair in db_session.scalars(select(CandidatePair)):
        pair.classification_status = ClassificationStatus.DONE
        pair.a_version = pair.b_version = 1
    db_session.commit()

    second = candidates_for_requirement(db_session, new, embedder)

    assert len(first.pending) == 1
    assert second.pending == [] and second.unchanged == 1
    assert embed_requirements(db_session, [new.id], embedder) == 0  # vector already current


def test_a_rejected_requirement_is_embedded_but_never_paired(
    db_session: Session,
    project: Project,
    baseline: MakeBaseline,
    post: Callable[[Project, str], Requirement],
    embedder: HashingEmbedder,
) -> None:
    baseline(project, TIMEOUT)
    new = post(project, TIMEOUT_POST)
    new.state = RequirementState.REJECTED
    db_session.commit()

    assert candidates_for_requirement(db_session, new, embedder).pending == []


def test_similar_hints_rank_by_similarity_store_nothing_and_skip_rejected(
    db_session: Session, project: Project, baseline: MakeBaseline, embedder: HashingEmbedder
) -> None:
    close, _far = baseline(project, TIMEOUT, UNRELATED)
    baseline(project, TIMEOUT, state=RequirementState.REJECTED)
    stored_before = db_session.scalar(select(func.count(Requirement.id)))

    hints = similar_to_text(db_session, project.id, TIMEOUT_POST, embedder, k=3)

    assert [h.requirement_id for h in hints] == [close.id]  # the unrelated one is below the floor
    assert hints[0].label == "REQ-001" and 0.5 <= hints[0].similarity <= 1
    assert db_session.scalar(select(func.count(Requirement.id))) == stored_before


def test_similar_hints_of_blank_text_are_empty(
    db_session: Session, project: Project, embedder: HashingEmbedder
) -> None:
    assert similar_to_text(db_session, project.id, "   ", embedder) == []


def test_candidates_for_one_requirement_take_under_a_second(
    db_session: Session,
    project: Project,
    baseline: MakeBaseline,
    post: Callable[[Project, str], Requirement],
    embedder: HashingEmbedder,
) -> None:
    """US-31 'done when': single-requirement candidates in under 1 s (500-requirement baseline)."""
    baseline(
        project,
        *[f"The system shall process batch {i} within {i % 60 + 1} seconds." for i in range(500)],
    )
    new = post(project, "The system shall process batch 7 within 8 seconds.")

    started = time.perf_counter()
    result = candidates_for_requirement(db_session, new, embedder)
    elapsed = time.perf_counter() - started

    assert result.pending
    assert elapsed < 1.0, f"{elapsed:.2f} s"
