"""Membership service: the one place memberships are created (US-27, SX-06)."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.core.permissions import DefaultRole, role_allowed_via_code
from app.models import (
    AuditAction,
    AuditLog,
    Membership,
    Project,
    ProjectMember,
    Role,
    User,
    Workspace,
)
from app.services.membership import (
    active_membership,
    add_member,
    add_project_member,
    ensure_role_allowed_via_code,
    get_default_role,
    get_role,
    list_active_memberships,
)


def test_adding_a_member_creates_an_active_membership_and_an_audit_row_without_text(
    db_session: Session, workspace: Workspace, make_user: Callable[..., User]
) -> None:
    newcomer = make_user(role=None)
    role = get_default_role(db_session, DefaultRole.QA_ENGINEER)

    membership = add_member(
        db_session,
        workspace_id=workspace.id,
        user_id=newcomer.id,
        role_id=role.id,
        stakeholder_group="Finance",
    )

    assert membership.is_active and membership.stakeholder_group == "Finance"
    audit = db_session.scalars(
        select(AuditLog).where(AuditLog.action == AuditAction.MEMBER_ADDED)
    ).one()
    assert audit.workspace_id == workspace.id
    assert audit.actor_id == newcomer.id  # defaults to the new member
    assert audit.details == {"user_id": str(newcomer.id), "role_id": str(role.id)}


def test_the_actor_can_be_someone_else(
    db_session: Session, workspace: Workspace, make_user: Callable[..., User]
) -> None:
    inviter, newcomer = make_user(), make_user(role=None)
    add_member(
        db_session,
        workspace_id=workspace.id,
        user_id=newcomer.id,
        role_id=get_default_role(db_session, DefaultRole.VIEWER).id,
        actor_id=inviter.id,
    )
    audits = db_session.scalars(
        select(AuditLog).where(AuditLog.action == AuditAction.MEMBER_ADDED)
    ).all()
    by_member = {row.details["user_id"]: row.actor_id for row in audits}
    assert by_member[str(newcomer.id)] == inviter.id  # who invited them, not the new member


def test_a_user_cannot_be_added_twice_to_the_same_workspace(
    db_session: Session, workspace: Workspace, user: User
) -> None:
    with pytest.raises(ConflictError, match="already a member"):
        add_member(
            db_session,
            workspace_id=workspace.id,
            user_id=user.id,
            role_id=get_default_role(db_session, DefaultRole.VIEWER).id,
        )


def test_a_removed_member_can_be_added_again(
    db_session: Session, workspace: Workspace, user: User
) -> None:
    old = db_session.scalars(select(Membership).where(Membership.user_id == user.id)).one()
    old.ended_at = datetime.now(UTC)
    db_session.commit()

    new = add_member(
        db_session,
        workspace_id=workspace.id,
        user_id=user.id,
        role_id=get_default_role(db_session, DefaultRole.VIEWER).id,
    )

    assert new.id != old.id and new.is_active
    assert active_membership(db_session, user.id, workspace.id) is not None


def test_roles_from_another_workspace_cannot_be_assigned(
    db_session: Session,
    workspace: Workspace,
    make_workspace: Callable[..., Workspace],
    make_user: Callable[..., User],
) -> None:
    foreign_role = Role(name="Foreign", workspace_id=make_workspace().id)
    db_session.add(foreign_role)
    db_session.commit()
    with pytest.raises(NotFoundError):
        add_member(
            db_session,
            workspace_id=workspace.id,
            user_id=make_user(role=None).id,
            role_id=foreign_role.id,
        )


def test_a_custom_role_of_the_same_workspace_can_be_assigned(
    db_session: Session, workspace: Workspace, make_user: Callable[..., User]
) -> None:
    custom = Role(name="Client reviewer", workspace_id=workspace.id)
    db_session.add(custom)
    db_session.commit()
    membership = add_member(
        db_session,
        workspace_id=workspace.id,
        user_id=make_user(role=None).id,
        role_id=custom.id,
    )
    assert membership.role_id == custom.id
    assert get_role(db_session, workspace.id, custom.id).name == "Client reviewer"


def test_an_unknown_role_is_not_found(db_session: Session, workspace: Workspace) -> None:
    with pytest.raises(NotFoundError):
        get_role(db_session, workspace.id, uuid.uuid4())


def test_the_same_user_can_have_a_different_role_in_each_workspace(
    db_session: Session,
    workspace: Workspace,
    make_workspace: Callable[..., Workspace],
    make_user: Callable[..., User],
) -> None:
    person = make_user(role=DefaultRole.DEVELOPER)
    second = make_workspace()
    add_member(
        db_session,
        workspace_id=second.id,
        user_id=person.id,
        role_id=get_default_role(db_session, DefaultRole.OWNER).id,
    )
    roles = {m.workspace_id: m.role.name for m in list_active_memberships(db_session, person.id)}
    assert roles == {workspace.id: "Developer", second.id: "Owner"}


def test_listing_skips_ended_memberships_and_orders_by_join_time(
    db_session: Session,
    workspace: Workspace,
    make_workspace: Callable[..., Workspace],
    make_user: Callable[..., User],
) -> None:
    person = make_user(role=DefaultRole.DEVELOPER)
    left, later = make_workspace(), make_workspace()
    viewer = get_default_role(db_session, DefaultRole.VIEWER).id
    first = active_membership(db_session, person.id, workspace.id)
    gone = add_member(db_session, workspace_id=left.id, user_id=person.id, role_id=viewer)
    last = add_member(db_session, workspace_id=later.id, user_id=person.id, role_id=viewer)
    # Inside one test transaction now() is constant, so set the join times explicitly.
    assert first is not None
    first.joined_at = datetime(2026, 1, 1, tzinfo=UTC)
    gone.joined_at = datetime(2026, 1, 2, tzinfo=UTC)
    gone.ended_at = datetime(2026, 1, 3, tzinfo=UTC)
    last.joined_at = datetime(2026, 1, 4, tzinfo=UTC)
    db_session.commit()

    ids = [m.workspace_id for m in list_active_memberships(db_session, person.id)]
    assert ids == [workspace.id, later.id]


def test_active_membership_ignores_ended_rows_and_other_users(
    db_session: Session, workspace: Workspace, user: User, make_user: Callable[..., User]
) -> None:
    assert active_membership(db_session, user.id, workspace.id) is not None
    assert active_membership(db_session, make_user(role=None).id, workspace.id) is None
    assert active_membership(db_session, user.id, uuid.uuid4()) is None


def test_missing_default_role_is_a_deployment_error(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_session.execute(select(Role))  # session is live
    from sqlalchemy import update

    db_session.execute(update(Role).where(Role.name == "Viewer").values(name="Viewer (renamed)"))
    with pytest.raises(RuntimeError, match="alembic upgrade head"):
        get_default_role(db_session, DefaultRole.VIEWER)


def test_adding_to_a_project_team_is_idempotent(
    db_session: Session, project: Project, user: User
) -> None:
    first = add_project_member(db_session, project=project, user=user)
    again = add_project_member(db_session, project=project, user=user)
    assert (first.project_id, first.user_id) == (again.project_id, again.user_id)
    assert (
        len(
            db_session.scalars(
                select(ProjectMember).where(ProjectMember.project_id == project.id)
            ).all()
        )
        == 1
    )


# ── add_project_member validates everything add_member does (PR review #1) ───────────────────
class TestAddProjectMember:
    def test_the_user_must_already_be_a_member_of_the_projects_workspace(
        self, db_session: Session, project: Project, make_user: Callable[..., User]
    ) -> None:
        outsider = make_user(role=None)
        with pytest.raises(NotFoundError, match="not a member"):
            add_project_member(db_session, project=project, user=outsider)
        assert db_session.get(ProjectMember, (project.id, outsider.id)) is None

    def test_a_member_of_another_workspace_cannot_be_put_on_the_team(
        self,
        db_session: Session,
        project: Project,
        make_workspace: Callable[..., Workspace],
        make_user: Callable[..., User],
    ) -> None:
        elsewhere = make_user(workspace=make_workspace())
        with pytest.raises(NotFoundError):
            add_project_member(db_session, project=project, user=elsewhere)

    def test_a_removed_member_cannot_be_put_on_the_team(
        self, db_session: Session, project: Project, user: User
    ) -> None:
        membership = active_membership(db_session, user.id, project.workspace_id)
        assert membership is not None
        membership.ended_at = datetime.now(UTC)
        db_session.commit()
        with pytest.raises(NotFoundError):
            add_project_member(db_session, project=project, user=user)

    def test_another_workspaces_custom_role_cannot_be_the_override(
        self,
        db_session: Session,
        project: Project,
        user: User,
        make_workspace: Callable[..., Workspace],
    ) -> None:
        foreign = Role(name="Foreign", workspace_id=make_workspace().id)
        db_session.add(foreign)
        db_session.commit()
        with pytest.raises(NotFoundError):
            add_project_member(db_session, project=project, user=user, role_override_id=foreign.id)

    def test_an_unknown_role_id_is_not_found(
        self, db_session: Session, project: Project, user: User
    ) -> None:
        with pytest.raises(NotFoundError):
            add_project_member(
                db_session, project=project, user=user, role_override_id=uuid.uuid4()
            )

    def test_ownership_cannot_be_granted_for_a_single_project(
        self, db_session: Session, project: Project, user: User
    ) -> None:
        owner = get_default_role(db_session, DefaultRole.OWNER)
        with pytest.raises(ConflictError, match="Ownership"):
            add_project_member(db_session, project=project, user=user, role_override_id=owner.id)
        assert db_session.get(ProjectMember, (project.id, user.id)) is None

    @pytest.mark.parametrize("role", [DefaultRole.OWNER, DefaultRole.ADMIN])
    def test_a_join_code_can_never_put_someone_on_a_project_as_owner_or_admin(
        self, db_session: Session, project: Project, user: User, role: DefaultRole
    ) -> None:
        privileged = get_default_role(db_session, role)
        with pytest.raises(ConflictError):
            add_project_member(
                db_session,
                project=project,
                user=user,
                role_override_id=privileged.id,
                via_join_code=True,
            )

    def test_a_valid_override_is_stored_and_audited_with_identifiers_only(
        self, db_session: Session, project: Project, user: User, make_user: Callable[..., User]
    ) -> None:
        manager = make_user(role=DefaultRole.PROJECT_MANAGER)
        reviewer = get_default_role(db_session, DefaultRole.COMPLIANCE_REVIEWER)

        member = add_project_member(
            db_session,
            project=project,
            user=user,
            role_override_id=reviewer.id,
            actor_id=manager.id,
            via_join_code=True,
        )

        assert member.role_override_id == reviewer.id
        audit = db_session.scalars(
            select(AuditLog).where(AuditLog.action == AuditAction.PROJECT_MEMBER_SET)
        ).one()
        assert audit.actor_id == manager.id and audit.workspace_id == project.workspace_id
        assert audit.details == {
            "project_id": str(project.id),
            "user_id": str(user.id),
            "role_override_id": str(reviewer.id),
        }

    def test_adding_to_the_team_without_an_override_is_audited_too(
        self, db_session: Session, project: Project, user: User
    ) -> None:
        add_project_member(db_session, project=project, user=user)
        audit = db_session.scalars(
            select(AuditLog).where(AuditLog.action == AuditAction.PROJECT_MEMBER_SET)
        ).one()
        assert audit.details["role_override_id"] is None

    def test_repeating_the_same_call_changes_and_audits_nothing(
        self, db_session: Session, project: Project, user: User
    ) -> None:
        developer = get_default_role(db_session, DefaultRole.DEVELOPER)
        add_project_member(db_session, project=project, user=user, role_override_id=developer.id)
        add_project_member(db_session, project=project, user=user, role_override_id=developer.id)
        add_project_member(db_session, project=project, user=user)  # no override given: keep it
        member = db_session.get(ProjectMember, (project.id, user.id))
        assert member is not None and member.role_override_id == developer.id
        audits = db_session.scalars(
            select(AuditLog).where(AuditLog.action == AuditAction.PROJECT_MEMBER_SET)
        ).all()
        assert len(audits) == 1

    def test_a_different_override_replaces_the_old_one_and_is_audited(
        self, db_session: Session, project: Project, user: User
    ) -> None:
        developer = get_default_role(db_session, DefaultRole.DEVELOPER)
        qa = get_default_role(db_session, DefaultRole.QA_ENGINEER)
        add_project_member(db_session, project=project, user=user, role_override_id=developer.id)
        member = add_project_member(db_session, project=project, user=user, role_override_id=qa.id)
        assert member.role_override_id == qa.id
        assert (
            len(
                db_session.scalars(
                    select(AuditLog).where(AuditLog.action == AuditAction.PROJECT_MEMBER_SET)
                ).all()
            )
            == 2
        )


# ── join codes never grant a privileged role (PR review #1) ──────────────────────────────────
class TestJoinCodeRoleRule:
    @pytest.mark.parametrize("role", [DefaultRole.OWNER, DefaultRole.ADMIN])
    def test_owner_and_admin_are_refused_for_a_join_code(
        self,
        db_session: Session,
        workspace: Workspace,
        make_user: Callable[..., User],
        role: DefaultRole,
    ) -> None:
        newcomer = make_user(role=None)
        with pytest.raises(ConflictError, match="join code"):
            add_member(
                db_session,
                workspace_id=workspace.id,
                user_id=newcomer.id,
                role_id=get_default_role(db_session, role).id,
                via_join_code=True,
            )
        assert active_membership(db_session, newcomer.id, workspace.id) is None

    @pytest.mark.parametrize(
        "role",
        [r for r in DefaultRole if r not in (DefaultRole.OWNER, DefaultRole.ADMIN)],
    )
    def test_every_other_default_role_may_be_granted_by_a_code(
        self,
        db_session: Session,
        workspace: Workspace,
        make_user: Callable[..., User],
        role: DefaultRole,
    ) -> None:
        newcomer = make_user(role=None)
        membership = add_member(
            db_session,
            workspace_id=workspace.id,
            user_id=newcomer.id,
            role_id=get_default_role(db_session, role).id,
            via_join_code=True,
        )
        assert membership.is_active

    def test_a_custom_role_with_admin_level_permissions_is_refused_too(
        self, db_session: Session, workspace: Workspace, make_user: Callable[..., User]
    ) -> None:
        """The rule is about permissions, not the names Owner and Admin."""
        from app.models import RolePermission

        sneaky = Role(name="Sneaky admin", workspace_id=workspace.id)
        db_session.add(sneaky)
        db_session.flush()
        db_session.add_all(
            [RolePermission(role_id=sneaky.id, permission=p) for p in ("view", "roles.manage")]
        )
        db_session.commit()
        with pytest.raises(ConflictError):
            ensure_role_allowed_via_code(sneaky)
        with pytest.raises(ConflictError):
            add_member(
                db_session,
                workspace_id=workspace.id,
                user_id=make_user(role=None).id,
                role_id=sneaky.id,
                via_join_code=True,
            )

    def test_without_the_flag_an_owner_can_still_be_added_for_example_when_creating_a_workspace(
        self,
        db_session: Session,
        make_workspace: Callable[..., Workspace],
        make_user: Callable[..., User],
    ) -> None:
        creator = make_user(role=None)
        membership = add_member(
            db_session,
            workspace_id=make_workspace().id,
            user_id=creator.id,
            role_id=get_default_role(db_session, DefaultRole.OWNER).id,
        )
        assert membership.is_active

    def test_the_permission_rule_agrees_with_the_named_default_roles(self) -> None:
        from app.core.permissions import DEFAULT_ROLE_PERMISSIONS, JOIN_CODE_FORBIDDEN_ROLES

        refused = {
            r for r, held in DEFAULT_ROLE_PERMISSIONS.items() if not role_allowed_via_code(held)
        }
        assert refused == set(JOIN_CODE_FORBIDDEN_ROLES)
