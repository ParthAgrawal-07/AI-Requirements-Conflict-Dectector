"""Database-level guarantees: constraints, append-only audit log, cascades, pgvector."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime

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
    ImportMode,
    Membership,
    Project,
    ProjectMember,
    ProjectStatus,
    Requirement,
    RequirementOrigin,
    RequirementState,
    RequirementVersion,
    Role,
    RolePermission,
    Severity,
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
    def test_email_must_be_lowercase(self, db_session: Session) -> None:
        with pytest.raises(IntegrityError), db_session.begin_nested():
            db_session.add(User(email="Mixed@Case.com", full_name="X", hashed_password="h"))
            db_session.flush()

    def test_email_is_unique(self, db_session: Session, user: User) -> None:
        with pytest.raises(IntegrityError), db_session.begin_nested():
            db_session.add(User(email=user.email, full_name="X", hashed_password="h"))
            db_session.flush()

    def test_platform_role_outside_enum_rejected_by_database(
        self, db_session: Session, user: User
    ) -> None:
        with pytest.raises(IntegrityError), db_session.begin_nested():
            db_session.execute(
                text("UPDATE users SET platform_role = 'superuser' WHERE id = :id"), {"id": user.id}
            )

    def test_users_have_no_workspace_or_role_columns_any_more(self, db_session: Session) -> None:
        columns = {
            row[0]
            for row in db_session.execute(
                text(
                    "SELECT column_name FROM information_schema.columns WHERE table_name = 'users'"
                )
            )
        }
        assert "role" not in columns and "workspace_id" not in columns
        assert "platform_role" in columns

    def test_workspace_defaults_and_threshold_range(
        self, db_session: Session, workspace: Workspace
    ) -> None:
        assert workspace.similarity_threshold == 0.75
        with pytest.raises(IntegrityError), db_session.begin_nested():
            db_session.execute(
                text("UPDATE workspaces SET similarity_threshold = 1.5 WHERE id = :id"),
                {"id": workspace.id},
            )

    def test_workspace_names_are_not_unique(self, db_session: Session) -> None:
        """A unique name would let one tenant learn that another tenant's workspace exists."""
        db_session.add_all([Workspace(name="Same name"), Workspace(name="Same name")])
        db_session.commit()
        assert (
            len(db_session.scalars(select(Workspace).where(Workspace.name == "Same name")).all())
            == 2
        )

    def test_workspace_with_members_cannot_be_deleted(
        self, db_session: Session, user: User, workspace: Workspace
    ) -> None:
        with pytest.raises(IntegrityError), db_session.begin_nested():
            db_session.execute(delete(Workspace).where(Workspace.id == workspace.id))

    def test_workspace_with_projects_cannot_be_deleted(
        self, db_session: Session, project: Project, workspace: Workspace
    ) -> None:
        with pytest.raises(IntegrityError), db_session.begin_nested():
            db_session.execute(delete(Workspace).where(Workspace.id == workspace.id))


class TestProjects:
    def test_defaults(self, db_session: Session, workspace: Workspace) -> None:
        project = Project(workspace_id=workspace.id, name="P")
        db_session.add(project)
        db_session.commit()
        db_session.refresh(project)
        assert project.status is ProjectStatus.SETUP  # FR-103: a new project starts in Setup
        assert project.context_version == 0
        assert (project.similarity_threshold, project.confidence_threshold) == (0.75, 0.5)
        assert project.llm_budget_monthly_calls == 2000
        assert project.required_approvals == 1
        assert project.chat_detection_enabled is False  # SX-04: chat analysis is opt-in

    def test_names_are_unique_per_workspace_but_not_across_workspaces(
        self,
        db_session: Session,
        project: Project,
        make_project: Callable[..., Project],
        make_workspace: Callable[..., Workspace],
    ) -> None:
        make_project(workspace=make_workspace(), name=project.name)  # same name, other tenant: ok
        with pytest.raises(IntegrityError), db_session.begin_nested():
            db_session.add(Project(workspace_id=project.workspace_id, name=project.name))
            db_session.flush()

    @pytest.mark.parametrize(
        "assignment",
        [
            "status = 'deleted'",
            "similarity_threshold = 1.5",
            "confidence_threshold = -0.1",
            "llm_budget_monthly_calls = -1",
            "required_approvals = 0",
            "required_approvals = 4",
            "context_version = -1",
        ],
    )
    def test_check_constraints(
        self, db_session: Session, project: Project, assignment: str
    ) -> None:
        with pytest.raises(IntegrityError), db_session.begin_nested():
            db_session.execute(
                text(f"UPDATE projects SET {assignment} WHERE id = :id"), {"id": project.id}
            )

    def test_a_project_with_documents_cannot_be_deleted(
        self, db_session: Session, project: Project, make_requirement: Callable[..., Requirement]
    ) -> None:
        make_requirement()
        with pytest.raises(IntegrityError), db_session.begin_nested():
            db_session.execute(delete(Project).where(Project.id == project.id))


class TestRolesAndMemberships:
    def test_the_nine_default_roles_are_seeded_and_global(self, db_session: Session) -> None:
        roles = db_session.scalars(select(Role).where(Role.is_default)).all()
        assert len(roles) == 9
        assert all(role.workspace_id is None for role in roles)

    def test_a_default_role_cannot_belong_to_a_workspace(
        self, db_session: Session, workspace: Workspace
    ) -> None:
        with pytest.raises(IntegrityError), db_session.begin_nested():
            db_session.add(Role(name="Odd", is_default=True, workspace_id=workspace.id))
            db_session.flush()

    def test_a_custom_role_must_belong_to_a_workspace(self, db_session: Session) -> None:
        with pytest.raises(IntegrityError), db_session.begin_nested():
            db_session.add(Role(name="Orphan", is_default=False, workspace_id=None))
            db_session.flush()

    def test_role_names_are_unique_among_defaults_and_per_workspace(
        self, db_session: Session, workspace: Workspace
    ) -> None:
        with pytest.raises(IntegrityError), db_session.begin_nested():
            db_session.add(Role(name="Owner", is_default=True, workspace_id=None))
            db_session.flush()
        db_session.add(Role(name="Client reviewer", workspace_id=workspace.id))
        db_session.commit()
        with pytest.raises(IntegrityError), db_session.begin_nested():
            db_session.add(Role(name="Client reviewer", workspace_id=workspace.id))
            db_session.flush()

    def test_the_same_custom_name_may_exist_in_two_workspaces(
        self,
        db_session: Session,
        workspace: Workspace,
        make_workspace: Callable[..., Workspace],
    ) -> None:
        db_session.add(Role(name="Auditor", workspace_id=workspace.id))
        db_session.add(Role(name="Auditor", workspace_id=make_workspace().id))
        db_session.commit()

    def test_a_role_in_use_cannot_be_deleted(self, db_session: Session, user: User) -> None:
        membership = db_session.scalars(
            select(Membership).where(Membership.user_id == user.id)
        ).one()
        with pytest.raises(IntegrityError), db_session.begin_nested():
            db_session.execute(delete(Role).where(Role.id == membership.role_id))

    def test_deleting_a_role_removes_its_permission_rows(
        self, db_session: Session, workspace: Workspace
    ) -> None:
        role = Role(name="Temp", workspace_id=workspace.id)
        db_session.add(role)
        db_session.flush()
        db_session.add(RolePermission(role_id=role.id, permission="view"))
        db_session.commit()

        db_session.execute(delete(Role).where(Role.id == role.id))

        assert (
            db_session.scalars(
                select(RolePermission).where(RolePermission.role_id == role.id)
            ).all()
            == []
        )

    def test_a_user_has_at_most_one_active_membership_per_workspace(
        self, db_session: Session, user: User, workspace: Workspace
    ) -> None:
        existing = db_session.scalars(select(Membership).where(Membership.user_id == user.id)).one()
        with pytest.raises(IntegrityError), db_session.begin_nested():
            db_session.add(
                Membership(user_id=user.id, workspace_id=workspace.id, role_id=existing.role_id)
            )
            db_session.flush()

    def test_history_rows_do_not_block_rejoining(
        self, db_session: Session, user: User, workspace: Workspace
    ) -> None:
        existing = db_session.scalars(select(Membership).where(Membership.user_id == user.id)).one()
        existing.ended_at = datetime.now(UTC)
        db_session.commit()

        db_session.add(
            Membership(user_id=user.id, workspace_id=workspace.id, role_id=existing.role_id)
        )
        db_session.commit()  # no IntegrityError: only *active* memberships are unique

    def test_project_members_are_unique_per_project_and_user(
        self, db_session: Session, project: Project, user: User
    ) -> None:
        db_session.add(ProjectMember(project_id=project.id, user_id=user.id))
        db_session.commit()
        with pytest.raises(IntegrityError), db_session.begin_nested():
            db_session.add(ProjectMember(project_id=project.id, user_id=user.id))
            db_session.flush()


class TestSeverityAndLifecycleColumns:
    def test_severity_is_low_medium_high_only(
        self, db_session: Session, make_requirement: Callable[..., Requirement]
    ) -> None:
        requirement = make_requirement()
        for level in ("low", "medium", "high"):
            db_session.add(
                _finding(
                    requirement.document_id,
                    requirement_id=requirement.id,
                    severity=Severity(level),
                )
            )
        db_session.commit()
        with pytest.raises(IntegrityError), db_session.begin_nested():
            db_session.execute(text("UPDATE findings SET severity = 'critical'"))

    def test_requirement_state_and_origin_defaults_and_checks(
        self, db_session: Session, make_requirement: Callable[..., Requirement]
    ) -> None:
        requirement = make_requirement()
        db_session.refresh(requirement)
        assert requirement.state is RequirementState.PROPOSED
        assert requirement.origin is RequirementOrigin.DOCUMENT
        assert requirement.owner_id is None
        for bad in ("state = 'Done'", "origin = 'email'"):
            with pytest.raises(IntegrityError), db_session.begin_nested():
                db_session.execute(
                    text(f"UPDATE requirements SET {bad} WHERE id = :id"), {"id": requirement.id}
                )

    def test_document_import_mode_default_and_check(
        self, db_session: Session, make_requirement: Callable[..., Requirement]
    ) -> None:
        document = db_session.get(Document, make_requirement().document_id)
        assert document is not None and document.import_mode is ImportMode.PROPOSALS
        with pytest.raises(IntegrityError), db_session.begin_nested():
            db_session.execute(
                text("UPDATE documents SET import_mode = 'merge' WHERE id = :id"),
                {"id": document.id},
            )


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
