"""The permission catalogue and default roles (spec §1.22) — pure data, no database."""

import pytest

from app.core import permissions as perms
from app.core.permissions import (
    DEFAULT_ROLE_DESCRIPTIONS,
    DEFAULT_ROLE_PERMISSIONS,
    JOIN_CODE_FORBIDDEN_PERMISSIONS,
    JOIN_CODE_FORBIDDEN_ROLES,
    PERMISSIONS,
    PROTECTED_ONLY_GRANTS,
    DefaultRole,
    holders_of,
    is_valid_permission,
    unknown_permissions,
)

ALL_ROLES = set(DefaultRole)


def test_catalogue_has_the_27_permissions_of_the_spec() -> None:
    assert len(PERMISSIONS) == 27
    assert all(description for description in PERMISSIONS.values())


def test_there_are_nine_default_roles_each_with_a_description() -> None:
    assert len(DefaultRole) == 9
    assert set(DEFAULT_ROLE_DESCRIPTIONS) == ALL_ROLES
    assert set(DEFAULT_ROLE_PERMISSIONS) == ALL_ROLES


def test_every_granted_permission_exists_in_the_catalogue() -> None:
    granted = set().union(*DEFAULT_ROLE_PERMISSIONS.values())
    assert granted <= set(PERMISSIONS)
    assert set(PERMISSIONS) <= granted, "a permission nobody holds is dead weight"


def test_role_major_and_permission_major_views_agree() -> None:
    for permission in PERMISSIONS:
        by_role = {role for role, held in DEFAULT_ROLE_PERMISSIONS.items() if permission in held}
        assert by_role == set(holders_of(permission)), permission


def test_everyone_may_view() -> None:
    assert set(holders_of("view")) == ALL_ROLES


def test_the_viewer_is_read_only() -> None:
    assert DEFAULT_ROLE_PERMISSIONS[DefaultRole.VIEWER] == {"view"}


def test_only_the_owner_manages_the_workspace() -> None:
    assert holders_of("workspace.manage") == (DefaultRole.OWNER,)


def test_only_the_compliance_reviewer_signs_off_protected_requirements() -> None:
    assert holders_of("protected.signoff") == (DefaultRole.COMPLIANCE_REVIEWER,)


def test_owner_holds_everything_except_the_compliance_signoff() -> None:
    assert DEFAULT_ROLE_PERMISSIONS[DefaultRole.OWNER] == set(PERMISSIONS) - {"protected.signoff"}


def test_admin_is_owner_minus_workspace_management_and_signoff() -> None:
    assert DEFAULT_ROLE_PERMISSIONS[DefaultRole.ADMIN] == set(PERMISSIONS) - {
        "workspace.manage",
        "protected.signoff",
    }


@pytest.mark.parametrize(
    ("role", "permission", "expected"),
    [
        (DefaultRole.PROJECT_MANAGER, "joincode.manage", True),
        (DefaultRole.PROJECT_MANAGER, "roles.manage", False),
        (DefaultRole.BUSINESS_ANALYST, "rcr.merge", True),
        (DefaultRole.DEVELOPER, "rcr.merge", False),
        (DefaultRole.DEVELOPER, "req.implement", True),
        (DefaultRole.QA_ENGINEER, "req.implement", False),
        (DefaultRole.STAKEHOLDER, "req.link", False),
        (DefaultRole.STAKEHOLDER, "req.propose", True),
        (DefaultRole.COMPLIANCE_REVIEWER, "req.propose", False),
        (DefaultRole.COMPLIANCE_REVIEWER, "req.comment", True),
        (DefaultRole.COMPLIANCE_REVIEWER, "audit.export", True),
        (DefaultRole.COMPLIANCE_REVIEWER, "doc.upload", False),
        (DefaultRole.VIEWER, "message.post", False),
    ],
)
def test_selected_cells_of_the_spec_table(
    role: DefaultRole, permission: str, expected: bool
) -> None:
    assert (permission in DEFAULT_ROLE_PERMISSIONS[role]) is expected


def test_compliance_reviewers_finding_review_is_protected_only() -> None:
    assert {(DefaultRole.COMPLIANCE_REVIEWER, "finding.review")} == PROTECTED_ONLY_GRANTS
    assert "finding.review" in DEFAULT_ROLE_PERMISSIONS[DefaultRole.COMPLIANCE_REVIEWER]


def test_join_codes_can_never_grant_owner_or_admin() -> None:
    assert {DefaultRole.OWNER, DefaultRole.ADMIN} == JOIN_CODE_FORBIDDEN_ROLES


def test_validation_helpers() -> None:
    assert is_valid_permission("view") and not is_valid_permission("view.everything")
    assert unknown_permissions(["view", "nope", "also.nope", "nope"]) == ["also.nope", "nope"]


def test_the_tables_are_read_only() -> None:
    with pytest.raises(TypeError):
        PERMISSIONS["new.permission"] = "x"  # type: ignore[index]
    with pytest.raises(TypeError):
        DEFAULT_ROLE_DESCRIPTIONS[DefaultRole.OWNER] = "x"  # type: ignore[index]
    assert isinstance(DEFAULT_ROLE_PERMISSIONS[DefaultRole.OWNER], frozenset)


def test_the_self_check_rejects_inconsistent_tables(monkeypatch: pytest.MonkeyPatch) -> None:
    """A permission added to one table but not the other must fail loudly at import time."""
    broken = dict(perms._GRANTS)
    broken.pop("view")
    monkeypatch.setattr(perms, "_GRANTS", broken)
    with pytest.raises(RuntimeError, match="permission tables disagree"):
        perms._self_check()


def test_the_join_code_rule_is_defined_on_permissions_and_matches_the_named_roles() -> None:
    assert {"workspace.manage", "roles.manage"} == JOIN_CODE_FORBIDDEN_PERMISSIONS
    refused = {
        role
        for role, held in DEFAULT_ROLE_PERMISSIONS.items()
        if not perms.role_allowed_via_code(held)
    }
    assert refused == set(JOIN_CODE_FORBIDDEN_ROLES)
    assert perms.role_allowed_via_code({"view", "doc.upload"})
    assert not perms.role_allowed_via_code({"view", "roles.manage"})


def test_the_self_check_notices_when_the_join_code_rule_and_the_roles_diverge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(perms, "JOIN_CODE_FORBIDDEN_PERMISSIONS", frozenset({"workspace.manage"}))
    with pytest.raises(RuntimeError, match="JOIN_CODE_FORBIDDEN_ROLES"):
        perms._self_check()


def test_the_owner_description_does_not_claim_everything() -> None:
    """The Owner never holds the compliance sign-off (spec §1.22), so the wording must not say so."""
    description = DEFAULT_ROLE_DESCRIPTIONS[DefaultRole.OWNER]
    assert "everything" not in description
    assert "compliance sign-off" in description
