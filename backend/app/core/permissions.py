"""Permission catalogue and the nine default roles (Parth — US-27, FR-48, ADR-20).

This module is **pure data**: no database, no FastAPI. It is the single source of truth for

* the 27 permissions (``IT314_RCD_Requirements_Spec_v5.md`` §1.22),
* which default role holds which permission,
* the few rules the spec attaches to specific roles (join codes never grant Owner/Admin;
  Compliance Reviewer holds ``finding.review`` for protected requirements only).

How it is used
--------------
* Migration ``0004_tenancy_roles`` seeds ``roles`` / ``role_permissions`` from a *frozen copy*
  of this data (migrations must not change when this file changes). A test asserts that the
  seeded rows equal these constants, so the two cannot drift silently.
* ``app.core.auth.require_permission`` checks a permission **name** against the caller's
  effective permission set. No code compares role names (ADR-20); the role names below exist
  only to seed the database and for display.
* Affan's permission matrix test is generated from :data:`PERMISSIONS` x
  :data:`DEFAULT_ROLE_PERMISSIONS`.

Adding a permission: add it to :data:`PERMISSIONS` and to :data:`_GRANTS`, then write a new
migration that inserts the new ``role_permissions`` rows (never edit a merged migration).
"""

from collections.abc import Iterable, Mapping
from enum import StrEnum
from types import MappingProxyType


class DefaultRole(StrEnum):
    """Names of the nine platform-wide default roles. Values are the stored ``roles.name``."""

    OWNER = "Owner"
    ADMIN = "Admin"
    PROJECT_MANAGER = "Project Manager"
    BUSINESS_ANALYST = "Business Analyst"
    DEVELOPER = "Developer"
    QA_ENGINEER = "QA Engineer"
    STAKEHOLDER = "Stakeholder"
    COMPLIANCE_REVIEWER = "Compliance Reviewer"
    VIEWER = "Viewer"


_R = DefaultRole

# ── The catalogue: permission name -> what it allows (spec §1.22) ───────────────────────────
PERMISSIONS: Mapping[str, str] = MappingProxyType(
    {
        "workspace.manage": "Workspace settings, transfer ownership, delete",
        "roles.manage": "Create and edit custom roles",
        "members.manage": "Change roles, remove members, approve join requests (PM: own projects)",
        "joincode.manage": "Create and revoke join codes (PM: own projects)",
        "project.manage": "Create projects, edit settings, budget, approvals",
        "project.context": "Write or edit the project brief and context; confirm AI-drafted fields",
        "srs.generate": "Generate an updated SRS draft; edit and accept its sections",
        "srs.publish": "Publish an SRS version; override the readiness checklist with a reason",
        "channel.manage": "Create, rename, archive channels",
        "message.post": "Post, reply, mention",
        "req.propose": "Propose requirements, drafts, lint, pre-flight",
        "req.comment": "Comment on requirements",
        "req.vote": "Support or oppose",
        "req.link": "Assert links between requirements",
        "doc.upload": "Upload SRS as proposals",
        "baseline.manage": "Upload SRS as baseline, freeze snapshots, approve Proposed requirements",
        "issue.open": "Open issues, comment on issues",
        "issue.manage": "Assign, label, close any issue",
        "rcr.open": "Open change requests",
        "rcr.review": "Review when requested (approval counts if eligible under FR-65)",
        "rcr.merge": "Merge an approved change request",
        "finding.review": "Confirm, dismiss, merge, reclassify findings",
        "req.protect": "Mark requirements protected",
        "protected.signoff": "Sign off findings and changes on protected requirements",
        "req.implement": "Mark Approved → Implemented",
        "audit.export": "Export the audit trail",
        "view": "See dashboards, map, analytics, timelines; export reports",
    }
)

# ── Who holds what (one row per permission, same order as the spec table) ──────────────────
_ALL_BUT_VIEWER = (
    _R.OWNER,
    _R.ADMIN,
    _R.PROJECT_MANAGER,
    _R.BUSINESS_ANALYST,
    _R.DEVELOPER,
    _R.QA_ENGINEER,
    _R.STAKEHOLDER,
    _R.COMPLIANCE_REVIEWER,
)
_CONTRIBUTORS = (  # may propose / vote / open change requests
    _R.OWNER,
    _R.ADMIN,
    _R.PROJECT_MANAGER,
    _R.BUSINESS_ANALYST,
    _R.DEVELOPER,
    _R.QA_ENGINEER,
    _R.STAKEHOLDER,
)
_ANALYSTS_AND_UP = (_R.OWNER, _R.ADMIN, _R.PROJECT_MANAGER, _R.BUSINESS_ANALYST)
_MANAGERS = (_R.OWNER, _R.ADMIN, _R.PROJECT_MANAGER)

_GRANTS: Mapping[str, tuple[DefaultRole, ...]] = MappingProxyType(
    {
        "workspace.manage": (_R.OWNER,),
        "roles.manage": (_R.OWNER, _R.ADMIN),
        "members.manage": _MANAGERS,
        "joincode.manage": _MANAGERS,
        "project.manage": _MANAGERS,
        "project.context": _MANAGERS,
        "srs.generate": _ANALYSTS_AND_UP,
        "srs.publish": _MANAGERS,
        "channel.manage": _ANALYSTS_AND_UP,
        "message.post": _ALL_BUT_VIEWER,
        "req.propose": _CONTRIBUTORS,
        "req.comment": _ALL_BUT_VIEWER,
        "req.vote": _CONTRIBUTORS,
        "req.link": (*_ANALYSTS_AND_UP, _R.DEVELOPER, _R.QA_ENGINEER),
        "doc.upload": _CONTRIBUTORS,
        "baseline.manage": _ANALYSTS_AND_UP,
        "issue.open": _ALL_BUT_VIEWER,
        "issue.manage": _ANALYSTS_AND_UP,
        "rcr.open": _CONTRIBUTORS,
        "rcr.review": _ALL_BUT_VIEWER,
        "rcr.merge": _ANALYSTS_AND_UP,
        "finding.review": (*_ANALYSTS_AND_UP, _R.COMPLIANCE_REVIEWER),
        "req.protect": (_R.OWNER, _R.ADMIN, _R.COMPLIANCE_REVIEWER),
        "protected.signoff": (_R.COMPLIANCE_REVIEWER,),
        "req.implement": (*_ANALYSTS_AND_UP, _R.DEVELOPER),
        "audit.export": (_R.OWNER, _R.ADMIN, _R.COMPLIANCE_REVIEWER),
        "view": tuple(DefaultRole),
    }
)

# Spec §1.22 grants the Compliance Reviewer ``finding.review`` "protected only": the permission
# is held, but may be exercised only on protected requirements. The US-10 guard (Sprint 3)
# reads ``AccessContext.protected_only`` — it never compares role names.
_PROTECTED_ONLY: frozenset[tuple[DefaultRole, str]] = frozenset(
    {(_R.COMPLIANCE_REVIEWER, "finding.review")}
)

DEFAULT_ROLE_DESCRIPTIONS: Mapping[DefaultRole, str] = MappingProxyType(
    {
        _R.OWNER: (
            "Runs the workspace: every permission except the compliance sign-off, including "
            "settings and ownership transfer."
        ),
        _R.ADMIN: "Manages members, roles and projects; cannot transfer or delete the workspace.",
        _R.PROJECT_MANAGER: "Runs a project: context, join codes, members, settings and SRS publishing.",
        _R.BUSINESS_ANALYST: "Reviews findings, manages the baseline and merges approved changes.",
        _R.DEVELOPER: "Proposes requirements, opens issues and change requests, reviews changes.",
        _R.QA_ENGINEER: "Proposes requirements, opens issues and change requests, reviews changes.",
        _R.STAKEHOLDER: "Client or domain expert: proposes, discusses, votes and reviews.",
        _R.COMPLIANCE_REVIEWER: "Signs off protected requirements; discusses and reviews; no proposing.",
        _R.VIEWER: "Read-only access to dashboards, the map and reports.",
    }
)

# Join codes can grant any role except these (FR-44, SX-14, NFR-35). This names the *default*
# roles for display and documentation; the rule itself is enforced on permissions below, so it
# also covers custom roles.
JOIN_CODE_FORBIDDEN_ROLES: frozenset[DefaultRole] = frozenset({_R.OWNER, _R.ADMIN})

# A role that holds any of these is "privileged": a join code may never hand it out (the Owner
# runs the workspace, the Admin manages roles). Enforced by ``membership.add_member`` and
# ``membership.add_project_member`` when ``via_join_code=True`` — see ``role_allowed_via_code``.
JOIN_CODE_FORBIDDEN_PERMISSIONS: frozenset[str] = frozenset({"workspace.manage", "roles.manage"})

# Permissions that exist only at workspace level: a project-level role override (FR-79) can
# never carry them, because ownership of the workspace is not a per-project notion.
WORKSPACE_LEVEL_ONLY_PERMISSIONS: frozenset[str] = frozenset({"workspace.manage"})


def _build_role_permissions() -> Mapping[DefaultRole, frozenset[str]]:
    by_role: dict[DefaultRole, set[str]] = {role: set() for role in DefaultRole}
    for permission, roles in _GRANTS.items():
        for role in roles:
            by_role[role].add(permission)
    return MappingProxyType({role: frozenset(perms) for role, perms in by_role.items()})


#: role -> the permissions it holds (role-major view of the spec table)
DEFAULT_ROLE_PERMISSIONS: Mapping[DefaultRole, frozenset[str]] = _build_role_permissions()

#: (role, permission) pairs that are held for protected requirements only
PROTECTED_ONLY_GRANTS: frozenset[tuple[DefaultRole, str]] = _PROTECTED_ONLY


def role_allowed_via_code(permissions: Iterable[str]) -> bool:
    """May a join code grant a role holding ``permissions``? (Never a privileged one.)"""
    return JOIN_CODE_FORBIDDEN_PERMISSIONS.isdisjoint(permissions)


def is_valid_permission(name: str) -> bool:
    return name in PERMISSIONS


def unknown_permissions(names: Iterable[str]) -> list[str]:
    """Names not in the catalogue, sorted — custom roles may only use catalogue permissions."""
    return sorted({name for name in names if name not in PERMISSIONS})


def holders_of(permission: str) -> tuple[DefaultRole, ...]:
    """The default roles that hold ``permission`` (used by tests and documentation)."""
    return _GRANTS[permission]


def _self_check() -> None:
    """Fail at import time if the tables above are inconsistent (a typo here is a security bug)."""
    missing = set(PERMISSIONS) - set(_GRANTS)
    extra = set(_GRANTS) - set(PERMISSIONS)
    if missing or extra:
        raise RuntimeError(f"permission tables disagree: missing={missing} extra={extra}")
    for role, permission in _PROTECTED_ONLY:
        if permission not in DEFAULT_ROLE_PERMISSIONS[role]:
            raise RuntimeError(f"{role} is protected-only for {permission} but does not hold it")
    if not set(DefaultRole) >= JOIN_CODE_FORBIDDEN_ROLES:
        raise RuntimeError("JOIN_CODE_FORBIDDEN_ROLES must name default roles")
    if not set(PERMISSIONS) >= JOIN_CODE_FORBIDDEN_PERMISSIONS:
        raise RuntimeError("JOIN_CODE_FORBIDDEN_PERMISSIONS must be catalogue permissions")
    privileged = {
        role for role, held in DEFAULT_ROLE_PERMISSIONS.items() if not role_allowed_via_code(held)
    }
    if privileged != set(JOIN_CODE_FORBIDDEN_ROLES):
        raise RuntimeError(
            f"the roles holding privileged permissions {sorted(privileged)} differ from "
            f"JOIN_CODE_FORBIDDEN_ROLES {sorted(JOIN_CODE_FORBIDDEN_ROLES)}"
        )


_self_check()
