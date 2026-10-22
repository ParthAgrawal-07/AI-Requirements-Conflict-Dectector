"""ProjectContextService against PostgreSQL (US-60, FR-103 to FR-105)."""

from collections.abc import Callable

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.context import service
from app.context.brief import BriefField, BriefValues
from app.context.drafter import BriefDrafter
from app.core.errors import BadRequestError, ConflictError
from app.ingestion import DocumentSection
from app.models import AuditAction, AuditLog, Project, ProjectContext, ProjectStatus, User
from app.services.projects import ProjectInSetupError

FULL = {
    "purpose": "Mobile banking for retail customers.",
    "scope_in": "Accounts and transfers.",
    "scope_out": "Loans.",
    "actors": ["Customer", "Support agent"],
    "environment": "Android and iOS; retail banking.",
}


@pytest.fixture
def setup_project(make_project: Callable[..., Project]) -> Project:
    return make_project(status=ProjectStatus.SETUP)


def _save(db: Session, project: Project, actor: User, **kwargs: object) -> service.SaveResult:
    fields = kwargs.pop("fields", {})
    return service.save_context(
        db,
        project_id=project.id,
        actor=actor,
        changes=BriefValues.model_validate(fields),
        **kwargs,  # type: ignore[arg-type]
    )


class TestSetup:
    def test_a_partial_brief_is_saved_but_the_project_stays_in_setup(
        self, db_session: Session, setup_project: Project, user: User
    ) -> None:
        result = _save(db_session, setup_project, user, fields={"purpose": FULL["purpose"]})
        assert result.created and not result.activated
        assert result.context.version == 1
        assert result.context.field_status == {"purpose": "confirmed"}
        db_session.refresh(setup_project)
        assert setup_project.status is ProjectStatus.SETUP
        assert setup_project.context_version == 0

    def test_the_last_required_field_activates_the_project(
        self, db_session: Session, setup_project: Project, user: User
    ) -> None:
        _save(db_session, setup_project, user, fields={k: FULL[k] for k in ("purpose", "actors")})
        result = _save(
            db_session,
            setup_project,
            user,
            fields={k: FULL[k] for k in ("scope_in", "scope_out", "environment")},
        )
        assert result.activated and result.context.version == 2
        db_session.refresh(setup_project)
        assert setup_project.status is ProjectStatus.ACTIVE
        assert setup_project.context_version == 2
        assert result.context.summary is not None
        assert result.context.summary.startswith("Mobile banking for retail customers.")
        assert "Actors: Customer, Support agent." in result.context.summary
        actions = db_session.scalars(select(AuditLog.action)).all()
        assert AuditAction.PROJECT_ACTIVATED in actions

    def test_the_gate_names_what_is_still_missing(
        self, db_session: Session, setup_project: Project, user: User
    ) -> None:
        _save(db_session, setup_project, user, fields={"purpose": "x", "scope_in": "y"})
        with pytest.raises(ProjectInSetupError) as raised:
            service.ensure_analysis_allowed(db_session, setup_project)
        assert raised.value.missing_fields == [
            "Scope (in and out)",
            "User classes and actors",
            "Operating environment and domain",
        ]

    def test_an_empty_field_cannot_be_confirmed(
        self, db_session: Session, setup_project: Project, user: User
    ) -> None:
        with pytest.raises(BadRequestError) as raised:
            _save(db_session, setup_project, user, confirm=[BriefField.ACTORS])
        assert raised.value.code == "context_field_empty"

    def test_an_archived_project_cannot_change_its_context(
        self, db_session: Session, make_project: Callable[..., Project], user: User
    ) -> None:
        archived = make_project(status=ProjectStatus.ARCHIVED)
        with pytest.raises(ConflictError):
            _save(db_session, archived, user, fields={"purpose": "x"})


class TestAiDraft:
    SECTIONS = [
        DocumentSection(
            heading="1.1 Purpose", body="PayLite is a bank app.", location="p 1", order_index=0
        ),
        DocumentSection(
            heading="2.3 User Classes", body="- Customer\n- Teller", location="p 2", order_index=1
        ),
    ]

    def test_a_draft_is_marked_ai_drafted_and_never_activates(
        self, db_session: Session, setup_project: Project
    ) -> None:
        context = service.draft_from_sections(
            db_session, project_id=setup_project.id, sections=self.SECTIONS, drafter=BriefDrafter()
        )
        assert context is not None and context.version == 1
        assert context.created_by is None and context.reason == "AI draft from a document"
        assert context.field_status == {"purpose": "ai_drafted", "actors": "ai_drafted"}
        db_session.refresh(setup_project)
        assert setup_project.status is ProjectStatus.SETUP

    def test_confirming_accepts_ai_drafted_values_as_they_are(
        self, db_session: Session, setup_project: Project, user: User
    ) -> None:
        service.draft_from_sections(
            db_session, project_id=setup_project.id, sections=self.SECTIONS, drafter=BriefDrafter()
        )
        result = _save(db_session, setup_project, user, confirm=[BriefField.ACTORS])
        assert result.context.actors == ["Customer", "Teller"]
        assert result.context.field_status == {"purpose": "ai_drafted", "actors": "confirmed"}

    def test_a_redraft_never_overwrites_a_confirmed_field(
        self, db_session: Session, setup_project: Project, user: User
    ) -> None:
        _save(db_session, setup_project, user, fields={"purpose": "Written by the PM."})
        context = service.draft_from_sections(
            db_session, project_id=setup_project.id, sections=self.SECTIONS, drafter=BriefDrafter()
        )
        assert context is not None
        assert context.purpose == "Written by the PM."
        assert context.field_status == {"purpose": "confirmed", "actors": "ai_drafted"}

    def test_a_draft_that_adds_nothing_creates_no_version(
        self, db_session: Session, setup_project: Project
    ) -> None:
        kwargs = {
            "project_id": setup_project.id,
            "sections": self.SECTIONS,
            "drafter": BriefDrafter(),
        }
        assert service.draft_from_sections(db_session, **kwargs) is not None  # type: ignore[arg-type]
        assert service.draft_from_sections(db_session, **kwargs) is None  # type: ignore[arg-type]


class TestActive:
    @pytest.fixture
    def active(self, db_session: Session, setup_project: Project, user: User) -> Project:
        _save(db_session, setup_project, user, fields=FULL)
        db_session.refresh(setup_project)
        return setup_project

    def test_an_edit_needs_a_reason_and_creates_a_new_version(
        self, db_session: Session, active: Project, user: User
    ) -> None:
        with pytest.raises(BadRequestError) as raised:
            _save(db_session, active, user, fields={"environment": "Web too."})
        assert raised.value.code == "context_reason_required"

        result = _save(
            db_session, active, user, fields={"environment": "Web too."}, reason="New channel"
        )
        assert result.created and not result.activated and result.context.version == 2
        assert result.context.reason == "New channel"
        db_session.refresh(active)
        assert active.context_version == 2
        old = db_session.scalar(
            select(ProjectContext).where(
                ProjectContext.project_id == active.id, ProjectContext.version == 1
            )
        )
        assert old is not None and old.environment == FULL["environment"]  # history kept

    def test_required_fields_cannot_be_emptied(
        self, db_session: Session, active: Project, user: User
    ) -> None:
        with pytest.raises(BadRequestError) as raised:
            _save(db_session, active, user, fields={"actors": []}, reason="oops")
        assert raised.value.code == "context_required_field_empty"

    def test_a_request_that_changes_nothing_creates_no_version(
        self, db_session: Session, active: Project, user: User
    ) -> None:
        result = _save(db_session, active, user, fields={"purpose": FULL["purpose"]})
        assert not result.created and result.context.version == 1

    def test_the_gate_lets_an_active_project_through(
        self, db_session: Session, active: Project
    ) -> None:
        service.ensure_analysis_allowed(db_session, active)
        confirmed = service.confirmed_context(db_session, active)
        assert confirmed is not None and confirmed.version == 1


class TestRegressions:
    """Bugs found in review of the first US-60 version."""

    def test_a_stale_status_in_the_session_does_not_skip_the_active_rules(
        self, db_session: Session, setup_project: Project, user: User
    ) -> None:
        """The lock re-reads the row; a save that waited for it sees the project is active."""
        from sqlalchemy.orm.attributes import set_committed_value

        _save(db_session, setup_project, user, fields=FULL)  # activates
        # Simulate a request that loaded the project before another request activated it.
        set_committed_value(setup_project, "status", ProjectStatus.SETUP)
        with pytest.raises(BadRequestError) as raised:
            _save(db_session, setup_project, user, fields={"environment": "Web too."})
        assert raised.value.code == "context_reason_required"
        db_session.refresh(setup_project)
        assert setup_project.context_version == 1

    def test_a_refused_save_releases_the_lock(
        self, db_session: Session, setup_project: Project, user: User
    ) -> None:
        with pytest.raises(BadRequestError):
            _save(db_session, setup_project, user, confirm=[BriefField.ACTORS])
        assert not db_session.in_transaction()

    def test_confirmed_findings_count_as_open(
        self,
        db_session: Session,
        setup_project: Project,
        user: User,
        make_requirement: Callable[..., object],
    ) -> None:
        from app.models import Finding, FindingCategory, FindingStatus, Requirement

        _save(db_session, setup_project, user, fields=FULL)
        requirement = make_requirement()
        assert isinstance(requirement, Requirement)
        for status in (FindingStatus.FLAGGED, FindingStatus.CONFIRMED, FindingStatus.DISMISSED):
            db_session.add(
                Finding(
                    document_id=requirement.document_id,
                    requirement_id=requirement.id,
                    category=FindingCategory.AMBIGUOUS,
                    confidence=0.9,
                    rationale="r",
                    status=status,
                    original_ai_output={},
                )
            )
        db_session.commit()
        assert service.count_open_findings(db_session, requirement.project_id) == 2

    def test_the_context_pack_never_sees_ai_drafted_fields(
        self, db_session: Session, setup_project: Project, user: User
    ) -> None:
        _save(db_session, setup_project, user, fields=FULL)
        glossary = [
            DocumentSection(
                heading="1.3 Definitions",
                body="OTP: One-time password",
                location="p 1",
                order_index=0,
            )
        ]
        service.draft_from_sections(
            db_session, project_id=setup_project.id, sections=glossary, drafter=BriefDrafter()
        )
        _save(db_session, setup_project, user, fields={"environment": "Web too."}, reason="r")
        db_session.refresh(setup_project)
        in_force = service.confirmed_context(db_session, setup_project)
        assert in_force is not None and in_force.glossary  # stored, but only as a draft
        assert in_force.field_status["glossary"] == "ai_drafted"
        assert service.confirmed_values(in_force).glossary is None
        assert service.confirmed_values(in_force).environment == "Web too."
