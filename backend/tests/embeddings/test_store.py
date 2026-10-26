"""Embedding stage and vector store (Heet — FR-07, FR-08): every extracted requirement gets a
vector, re-runs are idempotent, and nearest-neighbour search never leaves the project."""

import math
from collections.abc import Callable

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.embeddings.model import HashingEmbedder
from app.embeddings.store import embed_document, nearest_requirements, nearest_sections
from app.models import (
    Document,
    DocumentFormat,
    DocumentSection,
    Embedding,
    Project,
    Requirement,
    User,
    Workspace,
)
from app.models.embedding import EMBEDDING_DIM

MakeDocument = Callable[..., tuple[Document, list[Requirement]]]


@pytest.fixture
def embedder() -> HashingEmbedder:
    return HashingEmbedder()


@pytest.fixture
def make_document(db_session: Session, user: User) -> MakeDocument:
    def build(project: Project, *bodies: str) -> tuple[Document, list[Requirement]]:
        document = Document(
            workspace_id=project.workspace_id,
            project_id=project.id,
            uploaded_by=user.id,
            filename="srs.docx",
            format=DocumentFormat.DOCX,
            size_bytes=1,
            sha256="0" * 64,
            storage_path="srs.docx",
        )
        db_session.add(document)
        db_session.flush()
        requirements = [
            Requirement(document_id=document.id, project_id=project.id, body=body, order_index=i)
            for i, body in enumerate(bodies)
        ]
        db_session.add_all(requirements)
        db_session.add(
            DocumentSection(
                document_id=document.id,
                project_id=project.id,
                heading="1.2 Scope",
                body="Mobile banking for retail customers.",
                order_index=0,
            )
        )
        db_session.commit()
        return document, requirements

    return build


def test_the_hashing_embedder_is_normalised_and_deterministic(embedder: HashingEmbedder) -> None:
    first, again = embedder.embed(["The system shall log out idle users."] * 2)
    assert len(first) == EMBEDDING_DIM
    assert math.isclose(sum(x * x for x in first), 1.0)
    assert first == again


def test_every_requirement_and_section_of_the_document_is_embedded(
    db_session: Session, project: Project, make_document: MakeDocument, embedder: HashingEmbedder
) -> None:
    document, requirements = make_document(project, "Users shall sign in.", "Sessions shall end.")

    result = embed_document(db_session, document.id, embedder)

    assert (result.requirements, result.sections) == (2, 1)
    stored = db_session.scalars(select(Embedding)).all()
    assert {row.requirement_id for row in stored} == {r.id for r in requirements}
    assert all(row.model_version == embedder.version for row in stored)
    section = db_session.scalars(
        select(DocumentSection).where(DocumentSection.document_id == document.id)
    ).one()
    assert section.embedding is not None


def test_a_second_run_embeds_nothing_new(
    db_session: Session, project: Project, make_document: MakeDocument, embedder: HashingEmbedder
) -> None:
    document, _ = make_document(project, "Users shall sign in.")
    embed_document(db_session, document.id, embedder)

    again = embed_document(db_session, document.id, embedder)

    assert (again.requirements, again.sections) == (0, 0)
    assert db_session.scalar(select(func.count(Embedding.id))) == 1


def test_vectors_from_an_older_model_are_replaced(
    db_session: Session, project: Project, make_document: MakeDocument, embedder: HashingEmbedder
) -> None:
    document, _ = make_document(project, "Users shall sign in.")
    embed_document(db_session, document.id, embedder)

    class NewModel(HashingEmbedder):
        version = "new-model"

    result = embed_document(db_session, document.id, NewModel())

    assert result.requirements == 1
    assert db_session.scalars(select(Embedding.model_version)).one() == "new-model"


def test_nearest_ranks_by_similarity_and_stays_in_the_project(
    db_session: Session,
    project: Project,
    make_project: Callable[..., Project],
    make_workspace: Callable[..., Workspace],
    make_document: MakeDocument,
    embedder: HashingEmbedder,
) -> None:
    timeout = "When the user is inactive for 30 minutes the system shall end the session."
    doc, (session_rule, payments) = make_document(
        project, timeout, "The app shall show the reason when a payment fails."
    )
    foreign = make_project(workspace=make_workspace())
    foreign_doc, (foreign_twin,) = make_document(foreign, timeout)
    embed_document(db_session, doc.id, embedder)
    embed_document(db_session, foreign_doc.id, embedder)

    query = embedder.embed(["When the user is inactive for 5 minutes the app shall log out."])[0]
    found = nearest_requirements(db_session, project.id, query, k=5)

    assert [n.requirement_id for n in found] == [session_rule.id, payments.id]
    assert found[0].similarity > found[1].similarity
    assert foreign_twin.id not in {n.requirement_id for n in found}


def test_nearest_can_exclude_and_threshold(
    db_session: Session, project: Project, make_document: MakeDocument, embedder: HashingEmbedder
) -> None:
    doc, (first, second) = make_document(project, "alpha beta gamma", "delta epsilon zeta")
    embed_document(db_session, doc.id, embedder)
    query = embedder.embed(["alpha beta gamma"])[0]

    excluded = nearest_requirements(db_session, project.id, query, exclude={first.id})
    close_only = nearest_requirements(db_session, project.id, query, min_similarity=0.9)

    assert [n.requirement_id for n in excluded] == [second.id]
    assert [n.requirement_id for n in close_only] == [first.id]


def test_nearest_sections_returns_embedded_sections_of_the_project(
    db_session: Session, project: Project, make_document: MakeDocument, embedder: HashingEmbedder
) -> None:
    doc, _ = make_document(project, "Users shall sign in.")
    embed_document(db_session, doc.id, embedder)

    sections = nearest_sections(db_session, project.id, embedder.embed(["retail banking"])[0])

    assert [s.heading for s in sections] == ["1.2 Scope"]


def test_nearest_requirements_with_multiple_projects_in_database(
    db_session: Session,
    project: Project,
    make_project: Callable[..., Project],
    make_workspace: Callable[..., Workspace],
    make_document: MakeDocument,
    embedder: HashingEmbedder,
) -> None:
    """When multiple projects share the database, post-filtered HNSW finds all k neighbours."""
    # Seed foreign projects with similar requirements
    for i in range(5):
        foreign = make_project(workspace=make_workspace())
        foreign_doc, _ = make_document(
            foreign,
            *[
                f"Foreign project {i} user auth and sign-in requirement number {j}"
                for j in range(10)
            ],
        )
        embed_document(db_session, foreign_doc.id, embedder)

    # Seed target project with 10 requirements
    target_doc, target_reqs = make_document(
        project,
        *[f"Target project user auth and sign-in requirement number {j}" for j in range(10)],
    )
    embed_document(db_session, target_doc.id, embedder)

    query = embedder.embed(["user authentication and sign-in system"])[0]
    found = nearest_requirements(db_session, project.id, query, k=10)

    # All returned requirements must belong to the target project and return k items
    assert len(found) == 10
    target_req_ids = {r.id for r in target_reqs}
    assert all(n.requirement_id in target_req_ids for n in found)
