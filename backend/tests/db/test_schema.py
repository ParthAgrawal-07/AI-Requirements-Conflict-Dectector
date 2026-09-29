"""Database-level guarantees: constraints, append-only audit log, cascades, pgvector."""

import uuid
from collections.abc import Callable

import pytest
from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    AuditAction,
    AuditLog,
    CandidatePair,
    Document,
    Embedding,
    Finding,
    FindingCategory,
    FindingStatus,
    Requirement,
    RequirementVersion,
    User,
    Workspace,
)
from app.models.embedding import EMBEDDING_DIM

AI_OUTPUT = {"category": "Conflicting", "confidence": 0.9}


def _finding(document_id: uuid.UUID, **overrides: object) -> Finding:
    values: dict[str, object] = {
        "document_id": document_id,
        "category": FindingCategory.CONFLICTING,
        "confidence": 0.9,
        "rationale": "REQ-1 and REQ-2 disagree on the timeout.",
        "original_ai_output": AI_OUTPUT,
    }
    values.update(overrides)
    return Finding(**values)


def _vector(hot_index: int) -> list[float]:
    vec = [0.0] * EMBEDDING_DIM
    vec[hot_index] = 1.0
    return vec


class TestUsersAndWorkspaces:
    def test_email_must_be_lowercase(self, db_session: Session, workspace: Workspace) -> None:
        with pytest.raises(IntegrityError), db_session.begin_nested():
            db_session.add(
                User(
                    email="Mixed@Case.com",
                    full_name="X",
                    hashed_password="h",
                    workspace_id=workspace.id,
                )
            )
            db_session.flush()

    def test_email_is_unique(self, db_session: Session, user: User) -> None:
        with pytest.raises(IntegrityError), db_session.begin_nested():
            db_session.add(
                User(
                    email=user.email,
                    full_name="X",
                    hashed_password="h",
                    workspace_id=user.workspace_id,
                )
            )
            db_session.flush()

    def test_role_outside_enum_rejected_by_database(self, db_session: Session, user: User) -> None:
        with pytest.raises(IntegrityError), db_session.begin_nested():
            db_session.execute(
                text("UPDATE users SET role = 'superuser' WHERE id = :id"), {"id": user.id}
            )

    def test_workspace_defaults_and_threshold_range(
        self, db_session: Session, workspace: Workspace
    ) -> None:
        assert workspace.similarity_threshold == 0.75
        with pytest.raises(IntegrityError), db_session.begin_nested():
            db_session.execute(
                text("UPDATE workspaces SET similarity_threshold = 1.5 WHERE id = :id"),
                {"id": workspace.id},
            )

    def test_workspace_with_users_cannot_be_deleted(self, db_session: Session, user: User) -> None:
        with pytest.raises(IntegrityError), db_session.begin_nested():
            db_session.execute(delete(Workspace).where(Workspace.id == user.workspace_id))


class TestDocumentsAndRequirements:
    def test_document_defaults(
        self, db_session: Session, make_requirement: Callable[..., Requirement]
    ) -> None:
        requirement = make_requirement()
        document = db_session.get(Document, requirement.document_id)
        assert document is not None
        assert document.status.value == "queued"
        assert document.progress_percent == 0
        assert requirement.current_version == 1
        assert requirement.is_protected is False

    def test_progress_must_be_a_percentage(
        self, db_session: Session, make_requirement: Callable[..., Requirement]
    ) -> None:
        requirement = make_requirement()
        with pytest.raises(IntegrityError), db_session.begin_nested():
            db_session.execute(
                text("UPDATE documents SET progress_percent = 101 WHERE id = :id"),
                {"id": requirement.document_id},
            )

    def test_version_numbers_are_unique_per_requirement(
        self, db_session: Session, make_requirement: Callable[..., Requirement]
    ) -> None:
        requirement = make_requirement()
        db_session.add(
            RequirementVersion(requirement_id=requirement.id, version_no=1, body_snapshot="v1")
        )
        db_session.commit()
        with pytest.raises(IntegrityError), db_session.begin_nested():
            db_session.add(
                RequirementVersion(requirement_id=requirement.id, version_no=1, body_snapshot="dup")
            )
            db_session.flush()

    def test_deleting_a_document_cascades_to_requirements_and_embeddings(
        self, db_session: Session, make_requirement: Callable[..., Requirement]
    ) -> None:
        requirement = make_requirement()
        db_session.add(
            Embedding(requirement_id=requirement.id, vector=_vector(0), model_version="test")
        )
        db_session.commit()

        db_session.execute(delete(Document).where(Document.id == requirement.document_id))

        assert (
            db_session.scalar(select(Requirement).where(Requirement.id == requirement.id)) is None
        )
        assert (
            db_session.scalar(select(Embedding).where(Embedding.requirement_id == requirement.id))
            is None
        )


class TestCandidatePairs:
    def test_ordered_helper_returns_canonical_order(self) -> None:
        a, b = uuid.uuid4(), uuid.uuid4()
        assert CandidatePair.ordered(a, b) == CandidatePair.ordered(b, a)
        low, high = CandidatePair.ordered(a, b)
        assert low < high

    def test_pairing_a_requirement_with_itself_is_refused(self) -> None:
        same = uuid.uuid4()
        with pytest.raises(ValueError):
            CandidatePair.ordered(same, same)

    def test_pair_is_stored_once_in_canonical_order(
        self, db_session: Session, make_requirement: Callable[..., Requirement]
    ) -> None:
        first, second = (
            make_requirement("First requirement text."),
            make_requirement("Second requirement text."),
        )
        low, high = CandidatePair.ordered(first.id, second.id)

        db_session.add(
            CandidatePair(requirement_a_id=low, requirement_b_id=high, similarity_score=0.83)
        )
        db_session.commit()

        with pytest.raises(IntegrityError), db_session.begin_nested():  # reversed order
            db_session.add(
                CandidatePair(requirement_a_id=high, requirement_b_id=low, similarity_score=0.83)
            )
            db_session.flush()
        with pytest.raises(IntegrityError), db_session.begin_nested():  # exact duplicate
            db_session.add(
                CandidatePair(requirement_a_id=low, requirement_b_id=high, similarity_score=0.83)
            )
            db_session.flush()


class TestFindings:
    def test_defaults_and_ai_output_round_trip(
        self, db_session: Session, make_requirement: Callable[..., Requirement]
    ) -> None:
        requirement = make_requirement()
        finding = _finding(
            requirement.document_id,
            requirement_id=requirement.id,
            category=FindingCategory.INCOMPLETE,
        )
        db_session.add(finding)
        db_session.commit()
        db_session.expire(finding)

        assert finding.status is FindingStatus.FLAGGED
        assert finding.original_ai_output == AI_OUTPUT
        assert finding.severity is None

    def test_must_reference_exactly_one_subject(
        self, db_session: Session, make_requirement: Callable[..., Requirement]
    ) -> None:
        first, second = (
            make_requirement("First requirement text."),
            make_requirement("Second requirement text."),
        )
        low, high = CandidatePair.ordered(first.id, second.id)
        pair = CandidatePair(requirement_a_id=low, requirement_b_id=high, similarity_score=0.9)
        db_session.add(pair)
        db_session.commit()

        for bad in (
            _finding(first.document_id),  # neither
            _finding(first.document_id, candidate_pair_id=pair.id, requirement_id=first.id),  # both
        ):
            with pytest.raises(IntegrityError), db_session.begin_nested():
                db_session.add(bad)
                db_session.flush()

        db_session.add(
            _finding(first.document_id, candidate_pair_id=pair.id)
        )  # a pair alone is fine
        db_session.commit()

    @pytest.mark.parametrize("confidence", [-0.01, 1.01])
    def test_confidence_must_be_between_0_and_1(
        self, db_session: Session, make_requirement: Callable[..., Requirement], confidence: float
    ) -> None:
        requirement = make_requirement()
        with pytest.raises(IntegrityError), db_session.begin_nested():
            db_session.add(
                _finding(
                    requirement.document_id, requirement_id=requirement.id, confidence=confidence
                )
            )
            db_session.flush()


class TestAuditLog:
    @pytest.fixture
    def entry(self, db_session: Session, workspace: Workspace, user: User) -> AuditLog:
        row = AuditLog(
            workspace_id=workspace.id,
            actor_id=user.id,
            action=AuditAction.VIEWED_PROTECTED,
            details={"reason": "review"},
        )
        db_session.add(row)
        db_session.commit()
        return row

    def test_rows_can_be_appended_and_read_back(self, db_session: Session, entry: AuditLog) -> None:
        stored = db_session.scalar(select(AuditLog).where(AuditLog.id == entry.id))
        assert stored is not None
        assert stored.action == "viewed_protected"
        assert stored.details == {"reason": "review"}
        assert stored.at is not None

    def test_update_is_rejected_by_the_database(self, db_session: Session, entry: AuditLog) -> None:
        with pytest.raises(IntegrityError, match="append-only"), db_session.begin_nested():
            db_session.execute(
                update(AuditLog).where(AuditLog.id == entry.id).values(action="tampered")
            )

    def test_delete_is_rejected_by_the_database(self, db_session: Session, entry: AuditLog) -> None:
        with pytest.raises(IntegrityError, match="append-only"), db_session.begin_nested():
            db_session.execute(delete(AuditLog).where(AuditLog.id == entry.id))

    def test_truncate_is_rejected_by_the_database(
        self, db_session: Session, entry: AuditLog
    ) -> None:
        with pytest.raises(IntegrityError, match="append-only"), db_session.begin_nested():
            db_session.execute(text("TRUNCATE audit_log"))

    def test_actor_with_audit_history_cannot_be_deleted(
        self, db_session: Session, entry: AuditLog, user: User
    ) -> None:
        with pytest.raises(IntegrityError), db_session.begin_nested():
            db_session.execute(delete(User).where(User.id == user.id))


class TestPgvector:
    def test_vector_dimension_is_enforced(
        self, db_session: Session, make_requirement: Callable[..., Requirement]
    ) -> None:
        requirement = make_requirement()
        with pytest.raises(DataError), db_session.begin_nested():
            db_session.add(
                Embedding(requirement_id=requirement.id, vector=[0.1, 0.2, 0.3], model_version="x")
            )
            db_session.flush()

    def test_one_embedding_per_requirement(
        self, db_session: Session, make_requirement: Callable[..., Requirement]
    ) -> None:
        requirement = make_requirement()
        db_session.add(
            Embedding(requirement_id=requirement.id, vector=_vector(0), model_version="v1")
        )
        db_session.commit()
        with pytest.raises(IntegrityError), db_session.begin_nested():
            db_session.add(
                Embedding(requirement_id=requirement.id, vector=_vector(1), model_version="v1")
            )
            db_session.flush()

    def test_cosine_nearest_neighbour_query(
        self, db_session: Session, make_requirement: Callable[..., Requirement]
    ) -> None:
        """The exact query shape Role 2's candidate filter will use."""
        near, far = (
            make_requirement("Near requirement text."),
            make_requirement("Far requirement text."),
        )
        query = _vector(0)
        near_vec = [0.0] * EMBEDDING_DIM
        near_vec[0], near_vec[1] = 0.9, 0.1
        db_session.add_all(
            [
                Embedding(requirement_id=near.id, vector=near_vec, model_version="t"),
                Embedding(requirement_id=far.id, vector=_vector(200), model_version="t"),
            ]
        )
        db_session.commit()

        distance = Embedding.vector.cosine_distance(query)
        rows = db_session.execute(
            select(Embedding.requirement_id, distance).order_by(distance).limit(2)
        ).all()

        assert [row[0] for row in rows] == [near.id, far.id]
        assert rows[0][1] < 0.1 < rows[1][1]
