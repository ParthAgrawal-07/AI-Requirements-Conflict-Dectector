"""Join-code service (US-25, NFR-35): code format, hashing, lifecycle and redemption rules."""

import math
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, InvalidJoinCodeError
from app.core.permissions import DefaultRole
from app.models import (
    AuditAction,
    AuditLog,
    JoinCode,
    JoinCodeStatus,
    JoinRequest,
    JoinRequestStatus,
    Membership,
    Project,
    ProjectMember,
    User,
    Workspace,
)
from app.services import join_codes as service
from app.services.access import active_membership
from app.services.membership import add_member, get_default_role
from app.services.users import create_user


# ── Pure helpers ────────────────────────────────────────────────────────────────────────────
class TestCodeFormat:
    def test_the_alphabet_has_32_unambiguous_symbols_so_a_code_has_40_bits(self) -> None:
        assert len(set(service.ALPHABET)) == len(service.ALPHABET) == 32
        assert not set("01IO") & set(service.ALPHABET)
        assert service.CODE_LENGTH * math.log2(len(service.ALPHABET)) >= 40

    def test_generated_codes_use_only_the_alphabet_and_differ(self) -> None:
        codes = {service.generate_code() for _ in range(200)}
        assert len(codes) == 200
        assert all(len(c) == 8 and set(c) <= set(service.ALPHABET) for c in codes)

    @pytest.mark.parametrize("raw", ["k7qm-4xpa", "  K7QM 4XPA ", "K7QM4XPA"])
    def test_input_is_canonicalised(self, raw: str) -> None:
        assert service.canonicalize(raw) == "K7QM4XPA"

    @pytest.mark.parametrize("raw", ["", "K7QM", "K7QM-4XPA-9", "K7QM-4XP0", "K7QM-4XPI"])
    def test_malformed_input_is_not_a_code(self, raw: str) -> None:
        assert service.canonicalize(raw) is None

    def test_the_hash_is_keyed_by_the_pepper(self) -> None:
        assert service.hash_code("K7QM4XPA", "pepper-a") != service.hash_code(
            "K7QM4XPA", "pepper-b"
        )
        assert len(service.hash_code("K7QM4XPA")) == 64

    def test_the_code_is_shown_in_two_groups(self) -> None:
        assert service.format_code("K7QM4XPA") == "K7QM-4XPA"


# ── Database ────────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def manager(make_user: Callable[..., User]) -> User:
    return make_user(role=DefaultRole.PROJECT_MANAGER)


@pytest.fixture
def newcomer(db_session: Session) -> User:
    return create_user(
        db_session,
        email=f"new-{uuid.uuid4().hex[:8]}@example.com",
        password="correct-horse-battery-staple",
        full_name="New Person",
    )


@pytest.fixture
def issue(
    db_session: Session, workspace: Workspace, manager: User
) -> Callable[..., service.CreatedCode]:
    def build(role: DefaultRole = DefaultRole.DEVELOPER, **kwargs: object) -> service.CreatedCode:
        values: dict[str, object] = {"expires_in_days": 7}
        values.update(kwargs)
        return service.create_code(
            db_session,
            workspace_id=workspace.id,
            creator=manager,
            role_id=get_default_role(db_session, role).id,
            **values,  # type: ignore[arg-type]
        )

    return build


class TestCreate:
    def test_only_the_hash_and_a_hint_are_stored(
        self, issue: Callable[..., service.CreatedCode], db_session: Session
    ) -> None:
        created = issue()

        canonical = service.canonicalize(created.code)
        assert canonical is not None
        row = db_session.get(JoinCode, created.join_code.id)
        assert row is not None
        assert row.code_hash == service.hash_code(canonical)
        assert row.code_hint == canonical[-4:]
        assert canonical not in repr(row)

    @pytest.mark.parametrize("role", [DefaultRole.OWNER, DefaultRole.ADMIN])
    def test_a_code_can_never_grant_owner_or_admin(
        self, issue: Callable[..., service.CreatedCode], role: DefaultRole
    ) -> None:
        with pytest.raises(ConflictError):
            issue(role=role)

    def test_a_project_of_another_workspace_is_refused(
        self,
        issue: Callable[..., service.CreatedCode],
        make_workspace: Callable[..., Workspace],
        make_project: Callable[..., Project],
    ) -> None:
        foreign = make_project(workspace=make_workspace())
        with pytest.raises(Exception, match="not found"):
            issue(project_id=foreign.id)

    def test_creation_is_audited_without_the_code(
        self, issue: Callable[..., service.CreatedCode], db_session: Session, workspace: Workspace
    ) -> None:
        created = issue()
        rows = db_session.scalars(
            select(AuditLog).where(AuditLog.workspace_id == workspace.id)
        ).all()
        assert any(row.action == "join_code_created" for row in rows)
        assert created.code not in str([row.details for row in rows])
        assert created.join_code.code_hint not in str([row.details for row in rows])


class TestRedeem:
    def test_a_valid_code_creates_the_membership_with_the_codes_role(
        self,
        issue: Callable[..., service.CreatedCode],
        db_session: Session,
        newcomer: User,
        workspace: Workspace,
    ) -> None:
        created = issue(role=DefaultRole.QA_ENGINEER)

        outcome = service.redeem(db_session, created.code.lower(), newcomer)

        assert isinstance(outcome, Membership)
        assert outcome.workspace_id == workspace.id
        assert outcome.role.name == DefaultRole.QA_ENGINEER.value
        assert created.join_code.uses == 1

    def test_redeem_never_commits(
        self, issue: Callable[..., service.CreatedCode], db_session: Session, newcomer: User
    ) -> None:
        created = issue()
        db_session.commit()
        savepoint = db_session.begin_nested()

        service.redeem(db_session, created.code, newcomer)
        savepoint.rollback()

        assert active_membership(db_session, newcomer.id, created.join_code.workspace_id) is None

    @pytest.mark.parametrize("code", ["", "nonsense", "ZZZZ-ZZZZ"])
    def test_unknown_or_malformed_codes_get_the_one_generic_error(
        self, db_session: Session, newcomer: User, code: str
    ) -> None:
        with pytest.raises(InvalidJoinCodeError) as error:
            service.redeem(db_session, code, newcomer)
        assert error.value.message == InvalidJoinCodeError().message

    def test_expired_used_up_and_revoked_codes_get_the_same_error(
        self,
        issue: Callable[..., service.CreatedCode],
        db_session: Session,
        manager: User,
        make_user: Callable[..., User],
    ) -> None:
        expired = issue()
        expired.join_code.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        used_up = issue(max_uses=1)
        service.redeem(db_session, used_up.code, make_user(role=None))
        revoked = issue()
        service.revoke_code(db_session, join_code=revoked.join_code, actor=manager)

        messages = set()
        for created in (expired, used_up, revoked):
            with pytest.raises(InvalidJoinCodeError) as error:
                service.redeem(db_session, created.code, make_user(role=None))
            messages.add(error.value.message)
        assert len(messages) == 1

    def test_the_last_use_exhausts_the_code(
        self,
        issue: Callable[..., service.CreatedCode],
        db_session: Session,
        make_user: Callable[..., User],
    ) -> None:
        created = issue(max_uses=2)
        service.redeem(db_session, created.code, make_user(role=None))
        assert created.join_code.status is JoinCodeStatus.ACTIVE
        service.redeem(db_session, created.code, make_user(role=None))
        assert created.join_code.status is JoinCodeStatus.EXHAUSTED

    def test_an_existing_member_cannot_use_a_workspace_code_again(
        self, issue: Callable[..., service.CreatedCode], db_session: Session, manager: User
    ) -> None:
        created = issue()
        with pytest.raises(ConflictError):
            service.redeem(db_session, created.code, manager)
        assert created.join_code.uses == 0

    def test_a_project_code_also_adds_the_person_to_the_project_team(
        self,
        issue: Callable[..., service.CreatedCode],
        db_session: Session,
        newcomer: User,
        project: Project,
    ) -> None:
        created = issue(project_id=project.id)

        service.redeem(db_session, created.code, newcomer)

        assert db_session.get(ProjectMember, (project.id, newcomer.id)) is not None

    def test_a_team_member_cannot_burn_a_project_codes_uses(
        self,
        issue: Callable[..., service.CreatedCode],
        db_session: Session,
        make_user: Callable[..., User],
        project: Project,
    ) -> None:
        created = issue(project_id=project.id, max_uses=2)
        member = make_user(role=DefaultRole.DEVELOPER)
        service.redeem(db_session, created.code, member)
        assert db_session.get(ProjectMember, (project.id, member.id)) is not None

        with pytest.raises(ConflictError):
            service.redeem(db_session, created.code, member)

        assert created.join_code.uses == 1
        assert created.join_code.status is JoinCodeStatus.ACTIVE

    def test_a_lost_race_for_the_pending_request_is_a_conflict_not_a_500(
        self,
        issue: Callable[..., service.CreatedCode],
        db_session: Session,
        newcomer: User,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        service.redeem(db_session, issue(requires_approval=True).code, newcomer)
        second = issue(requires_approval=True).code
        # Simulate the concurrent transaction: its pending request was not visible to the check.
        monkeypatch.setattr(service, "_pending_request", lambda *_: None)

        with pytest.raises(ConflictError):
            service.redeem(db_session, second, newcomer)

    def test_a_code_needing_approval_creates_a_pending_request_and_no_membership(
        self,
        issue: Callable[..., service.CreatedCode],
        db_session: Session,
        newcomer: User,
        workspace: Workspace,
    ) -> None:
        created = issue(requires_approval=True)

        outcome = service.redeem(db_session, created.code, newcomer)

        assert isinstance(outcome, JoinRequest)
        assert outcome.status is JoinRequestStatus.PENDING
        assert active_membership(db_session, newcomer.id, workspace.id) is None
        with pytest.raises(ConflictError):  # one pending request per workspace
            service.redeem(db_session, created.code, newcomer)


class TestDecide:
    def test_approving_with_another_role_creates_that_membership(
        self,
        issue: Callable[..., service.CreatedCode],
        db_session: Session,
        newcomer: User,
        manager: User,
        workspace: Workspace,
    ) -> None:
        request = service.redeem(db_session, issue(requires_approval=True).code, newcomer)
        assert isinstance(request, JoinRequest)
        stakeholder = get_default_role(db_session, DefaultRole.STAKEHOLDER)

        service.decide(
            db_session, request=request, actor=manager, approve=True, role_id=stakeholder.id
        )

        membership = active_membership(db_session, newcomer.id, workspace.id)
        assert membership is not None and membership.role_id == stakeholder.id
        assert request.status is JoinRequestStatus.APPROVED and request.decided_by == manager.id

    def test_approval_can_never_grant_admin(
        self,
        issue: Callable[..., service.CreatedCode],
        db_session: Session,
        newcomer: User,
        manager: User,
    ) -> None:
        request = service.redeem(db_session, issue(requires_approval=True).code, newcomer)
        assert isinstance(request, JoinRequest)
        admin = get_default_role(db_session, DefaultRole.ADMIN)

        with pytest.raises(ConflictError):
            service.decide(
                db_session, request=request, actor=manager, approve=True, role_id=admin.id
            )

    def test_a_denied_request_cannot_be_decided_again(
        self,
        issue: Callable[..., service.CreatedCode],
        db_session: Session,
        newcomer: User,
        manager: User,
        workspace: Workspace,
    ) -> None:
        request = service.redeem(db_session, issue(requires_approval=True).code, newcomer)
        assert isinstance(request, JoinRequest)

        service.decide(db_session, request=request, actor=manager, approve=False)

        assert request.status is JoinRequestStatus.DENIED
        assert active_membership(db_session, newcomer.id, workspace.id) is None
        with pytest.raises(ConflictError):
            service.decide(db_session, request=request, actor=manager, approve=True)

    def test_approving_an_existing_member_keeps_and_audits_their_real_role(
        self,
        issue: Callable[..., service.CreatedCode],
        db_session: Session,
        newcomer: User,
        manager: User,
        workspace: Workspace,
        project: Project,
    ) -> None:
        request = service.redeem(
            db_session, issue(project_id=project.id, requires_approval=True).code, newcomer
        )
        assert isinstance(request, JoinRequest)
        stakeholder = get_default_role(db_session, DefaultRole.STAKEHOLDER)
        add_member(
            db_session,
            workspace_id=workspace.id,
            user_id=newcomer.id,
            role_id=stakeholder.id,
            commit=False,
        )
        developer = get_default_role(db_session, DefaultRole.DEVELOPER)

        with pytest.raises(ConflictError):  # the override would silently not apply
            service.decide(
                db_session, request=request, actor=manager, approve=True, role_id=developer.id
            )
        service.decide(db_session, request=request, actor=manager, approve=True)

        membership = active_membership(db_session, newcomer.id, workspace.id)
        assert membership is not None
        assert membership.role_id == stakeholder.id
        assert db_session.get(ProjectMember, (project.id, newcomer.id)) is not None
        audit = db_session.scalars(
            select(AuditLog).where(
                AuditLog.action == AuditAction.JOIN_REQUEST_APPROVED,
                AuditLog.workspace_id == workspace.id,
            )
        ).one()
        assert audit.details["role_id"] == str(stakeholder.id)

    def test_a_request_past_its_ttl_cannot_be_approved_before_the_beat_runs(
        self,
        issue: Callable[..., service.CreatedCode],
        db_session: Session,
        newcomer: User,
        manager: User,
    ) -> None:
        request = service.redeem(db_session, issue(requires_approval=True).code, newcomer)
        assert isinstance(request, JoinRequest)
        request.created_at = datetime.now(UTC) - service.JOIN_REQUEST_TTL - timedelta(minutes=1)
        db_session.flush()

        with pytest.raises(ConflictError):
            service.decide(db_session, request=request, actor=manager, approve=True)


class TestExpiry:
    def test_stale_codes_and_old_requests_are_expired(
        self,
        issue: Callable[..., service.CreatedCode],
        db_session: Session,
        newcomer: User,
    ) -> None:
        stale = issue()
        stale.join_code.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        fresh = issue()
        request = service.redeem(db_session, issue(requires_approval=True).code, newcomer)
        assert isinstance(request, JoinRequest)
        request.created_at = datetime.now(UTC) - timedelta(days=15)
        db_session.flush()

        codes, requests = service.expire_stale(db_session)

        assert (codes, requests) == (1, 1)
        db_session.refresh(stale.join_code)
        db_session.refresh(fresh.join_code)
        db_session.refresh(request)
        assert stale.join_code.status is JoinCodeStatus.EXPIRED
        assert fresh.join_code.status is JoinCodeStatus.ACTIVE
        assert request.status is JoinRequestStatus.EXPIRED

    def test_an_active_code_past_expiry_reads_as_expired_before_the_beat_runs(
        self, issue: Callable[..., service.CreatedCode]
    ) -> None:
        created = issue()
        created.join_code.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        assert service.effective_status(created.join_code) is JoinCodeStatus.EXPIRED
