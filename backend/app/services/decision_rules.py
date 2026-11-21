"""Decision rules and decision owners (Parth — US-57, FR-65, FR-100, DR-23; §11.1; ADR-26).

**Who decides.** Every finding, issue and change request has a *decision owner* chosen by the
project's decision rules: the most specific rule whose match fields all fit the item wins (ties:
lower ``priority``, then the older rule); the default rule matches everything. The owner is a
role (anyone holding it in the project), a person, or the owner of the requirement concerned.
:meth:`DecisionRuleEngine.sentence` says it in words: "Decides: Meera — rule *Protected
requirements*".

**What it changes.**

* *Merge* (``AgreementGuard``): the decision owner must approve the proposal revision — besides
  the required approvals and reviewers of US-35 — and every required reviewer the rule names.
  Approval counts and votes alone never satisfy a rule. A decision owner who proposed the change
  has decided by proposing it; the reviewers still review.
* *Finding closure* (dismiss, merge): when a rule other than the default chose the owner, only the
  decision owner may close the finding. The default rule keeps the US-10 review guard.
* *Reviewers*: ``ReviewPolicy`` asks the decision owner and the rule's reviewers.

**When.** The decision is stored on the item (``decision`` jsonb) the first time it is needed and
refreshed at the item's next update, so editing a rule never changes the authority over an item
half-way through (US-57: "apply to open items only after their next update"). Rule changes are
audited. A project with no rules yet behaves as if it had the default one.

**Seeded rules** for new projects: the default (requirement owner decides), protected →
Compliance Reviewer, group *Security* → Project Manager until a security lead is named, label
``deadline`` → Project Manager, category *Duplicate* → Business Analyst.
"""

import uuid
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import BadRequestError, ConflictError
from app.core.permissions import DefaultRole
from app.models import (
    AuditAction,
    AuditLog,
    ChangeRequest,
    Finding,
    Issue,
    IssueRequirement,
    Membership,
    Project,
    Requirement,
    Role,
    User,
)
from app.models.decision_rule import MATCH_FIELDS, REQUIREMENT_OWNER, ROLE, USER, DecisionRule
from app.services.access import Scope, build_access_context

DEFAULT_NAME = "Default: the requirement owner decides"


@dataclass(frozen=True)
class Facts:
    """What a rule can match on, gathered from the item and its requirements."""

    category: str | None = None
    labels: frozenset[str] = frozenset()
    groups: frozenset[str] = frozenset()
    req_types: frozenset[str] = frozenset()
    protected: bool = False
    owner_ids: frozenset[uuid.UUID] = frozenset()


@dataclass(frozen=True)
class Decision:
    """A rule's verdict, as stored on the item."""

    rule_id: str | None  # None: the built-in default of a project without rules
    rule_name: str
    is_default: bool
    owner_kind: str
    owner_role_id: str | None = None
    owner_user_id: str | None = None
    required_reviewers: list[dict[str, str]] = field(default_factory=list)
    optional_reviewers: list[dict[str, str]] = field(default_factory=list)

    def as_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Decision":
        return cls(**{k: data[k] for k in cls.__dataclass_fields__ if k in data})

    @classmethod
    def of(cls, rule: DecisionRule) -> "Decision":
        return cls(
            rule_id=str(rule.id),
            rule_name=rule.name,
            is_default=rule.is_default,
            owner_kind=rule.owner_kind,
            owner_role_id=str(rule.owner_role_id) if rule.owner_role_id else None,
            owner_user_id=str(rule.owner_user_id) if rule.owner_user_id else None,
            required_reviewers=list(rule.required_reviewers),
            optional_reviewers=list(rule.optional_reviewers),
        )


BUILT_IN = Decision(None, DEFAULT_NAME, True, REQUIREMENT_OWNER)


def matches(rule: DecisionRule, facts: Facts) -> bool:
    return (
        (rule.match_category is None or rule.match_category == facts.category)
        and (rule.match_label is None or rule.match_label.lower() in facts.labels)
        and (rule.match_group is None or rule.match_group.lower() in facts.groups)
        and (rule.match_req_type is None or rule.match_req_type in facts.req_types)
        and (rule.match_protected is None or rule.match_protected == facts.protected)
    )


def rules_of(db: Session, project_id: uuid.UUID) -> list[DecisionRule]:
    return list(
        db.scalars(
            select(DecisionRule)
            .where(DecisionRule.project_id == project_id)
            .order_by(DecisionRule.is_default, DecisionRule.priority, DecisionRule.created_at)
        )
    )


# ── facts ───────────────────────────────────────────────────────────────────────────────────
def facts_for(
    requirements: Iterable[Requirement],
    *,
    category: str | None = None,
    labels: Iterable[str] = (),
) -> Facts:
    rows = list(requirements)
    return Facts(
        category=category,
        labels=frozenset(label.lower() for label in labels),
        groups=frozenset(r.stakeholder_group.lower() for r in rows if r.stakeholder_group),
        req_types=frozenset(r.req_type for r in rows if r.req_type),
        protected=any(r.is_protected for r in rows),
        owner_ids=frozenset(r.owner_id for r in rows if r.owner_id),
    )


def _issue_labels(db: Session, finding_id: uuid.UUID) -> list[str]:
    labels = db.scalars(select(Issue.labels).where(Issue.finding_id == finding_id)).all()
    return [label for row in labels for label in row]


def facts_for_finding(db: Session, finding: Finding) -> Facts:
    from app.services.review_state import involved_requirements  # it imports this module

    return facts_for(
        involved_requirements(db, finding),
        category=finding.category.value,
        labels=_issue_labels(db, finding.id),
    )


def facts_for_issue(db: Session, issue: Issue) -> Facts:
    ids = db.scalars(
        select(IssueRequirement.requirement_id).where(IssueRequirement.issue_id == issue.id)
    ).all()
    finding = db.get(Finding, issue.finding_id) if issue.finding_id else None
    return facts_for(
        db.scalars(select(Requirement).where(Requirement.id.in_(ids))),
        category=finding.category.value if finding else None,
        labels=issue.labels,
    )


def facts_for_change_request(db: Session, change_request: ChangeRequest) -> Facts:
    from app.intake.change_intake import resolves

    requirement = db.get(Requirement, change_request.requirement_id)
    resolved = resolves(db, change_request.id)
    findings = [db.get(Finding, i.finding_id) for i in resolved if i.finding_id]
    return facts_for(
        [requirement] if requirement else [],
        category=next((f.category.value for f in findings if f is not None), None),
        labels=[label for issue in resolved for label in issue.labels],
    )


# ── the engine ──────────────────────────────────────────────────────────────────────────────
class DecisionRuleEngine:
    def __init__(self, db: Session) -> None:
        self.db = db

    def resolve(self, project_id: uuid.UUID, facts: Facts) -> Decision:
        candidates = [rule for rule in rules_of(self.db, project_id) if matches(rule, facts)]
        if not candidates:
            return BUILT_IN
        best = sorted(candidates, key=lambda r: (-r.specificity, r.priority, r.created_at))[0]
        return Decision.of(best)

    def _members(self, project: Project) -> list[User]:
        return list(
            self.db.scalars(
                select(User)
                .join(Membership, Membership.user_id == User.id)
                .where(
                    Membership.workspace_id == project.workspace_id, Membership.ended_at.is_(None)
                )
                .order_by(User.full_name, User.id)
            )
        )

    def spec_users(self, project: Project, spec: dict[str, str]) -> list[User]:
        """The current members a ``{"kind": "role" | "user", "id": …}`` spec names."""
        members = self._members(project)
        if spec.get("kind") == USER:
            return [u for u in members if str(u.id) == spec.get("id")]
        scope = Scope(project.workspace_id, project.id)
        return [
            u
            for u in members
            if str(build_access_context(self.db, u, scope).role.id) == spec.get("id")
        ]

    def owners(self, project: Project, decision: Decision, facts: Facts) -> list[User]:
        """Who may make the decision now."""
        if decision.owner_kind == REQUIREMENT_OWNER:
            return [u for u in self._members(project) if u.id in facts.owner_ids]
        spec_id = decision.owner_role_id if decision.owner_kind == ROLE else decision.owner_user_id
        return self.spec_users(project, {"kind": decision.owner_kind, "id": spec_id or ""})

    def owner_name(self, decision: Decision, owners: list[User]) -> str:
        if decision.owner_kind == ROLE and decision.owner_role_id:
            role = self.db.get(Role, uuid.UUID(decision.owner_role_id))
            names = ", ".join(u.full_name for u in owners) or "nobody holds it yet"
            return f"{role.name if role else 'a deleted role'} ({names})"
        if decision.owner_kind == REQUIREMENT_OWNER:
            names = " or ".join(u.full_name for u in owners)
            return f"the requirement owner ({names})" if names else "the requirement owner"
        return owners[0].full_name if owners else "a former member"

    def sentence(self, project: Project, decision: Decision, facts: Facts) -> str:
        owners = self.owners(project, decision, facts)
        return f"Decides: {self.owner_name(decision, owners)} — rule {decision.rule_name}"

    # ── seeding ──────────────────────────────────────────────────────────────────────────
    def seed(self, project: Project, *, actor_id: uuid.UUID | None = None) -> list[DecisionRule]:
        """The default rule and the four examples of US-57, for a new project (no commit)."""
        from app.services.membership import get_default_role

        def role(name: DefaultRole) -> uuid.UUID:
            return get_default_role(self.db, name).id

        rows = [
            DecisionRule(name=DEFAULT_NAME, owner_kind=REQUIREMENT_OWNER, is_default=True),
            DecisionRule(name="Protected requirements", match_protected=True, owner_kind=ROLE,
                         owner_role_id=role(DefaultRole.COMPLIANCE_REVIEWER)),
            DecisionRule(name="Security exceptions (name your security lead)",
                         match_group="Security", owner_kind=ROLE,
                         owner_role_id=role(DefaultRole.PROJECT_MANAGER)),
            DecisionRule(name="Deadline trade-offs", match_label="deadline", owner_kind=ROLE,
                         owner_role_id=role(DefaultRole.PROJECT_MANAGER)),
            DecisionRule(name="Duplicates", match_category="Duplicate", owner_kind=ROLE,
                         owner_role_id=role(DefaultRole.BUSINESS_ANALYST)),
        ]  # fmt: skip
        for row in rows:
            row.project_id, row.created_by = project.id, actor_id
            self.db.add(row)
        self.db.flush()
        return rows


# ── decisions stored on items ───────────────────────────────────────────────────────────────
Decidable = Finding | Issue | ChangeRequest


def _facts(db: Session, item: Decidable) -> Facts:
    if isinstance(item, Finding):
        return facts_for_finding(db, item)
    if isinstance(item, Issue):
        return facts_for_issue(db, item)
    return facts_for_change_request(db, item)


def decision_for(db: Session, item: Decidable, *, store: bool = True) -> tuple[Decision, Facts]:
    """The item's stored decision. One it does not have yet is resolved now — and stored (a
    commit) unless ``store=False``, for callers inside a locked transaction such as the merge."""
    facts = _facts(db, item)
    if item.decision is not None:
        return Decision.from_json(item.decision), facts
    if not store:
        return DecisionRuleEngine(db).resolve(item.project_id, facts), facts
    return refresh(db, item, facts), facts


def refresh(db: Session, item: Decidable, facts: Facts | None = None) -> Decision:
    """Re-resolve the item's decision under the current rules — at its next update (commits)."""
    decision = DecisionRuleEngine(db).resolve(item.project_id, facts or _facts(db, item))
    item.decision = decision.as_json()
    db.commit()
    return decision


# ── editing rules ───────────────────────────────────────────────────────────────────────────
def _check_spec(db: Session, project: Project, spec: dict[str, Any]) -> dict[str, str]:
    kind, raw = spec.get("kind"), spec.get("id")
    try:
        target = uuid.UUID(str(raw))
    except ValueError:
        raise BadRequestError(
            "A reviewer needs a role or a member id", code="bad_reviewer"
        ) from None
    if kind == ROLE:
        found = db.get(Role, target)
        if found is None or found.workspace_id not in (None, project.workspace_id):
            raise BadRequestError("That role is not in this workspace", code="unknown_role")
    elif kind == USER:
        member = db.scalar(
            select(Membership.user_id).where(
                Membership.workspace_id == project.workspace_id,
                Membership.user_id == target,
                Membership.ended_at.is_(None),
            )
        )
        if member is None:
            raise BadRequestError("That person is not a member here", code="unknown_member")
    else:
        raise BadRequestError("A reviewer is a role or a user", code="bad_reviewer")
    return {"kind": str(kind), "id": str(target)}


def _audit(
    db: Session, project: Project, actor: User, action: AuditAction, rule: DecisionRule
) -> None:
    db.add(
        AuditLog(
            workspace_id=project.workspace_id,
            actor_id=actor.id,
            action=action,
            details={"project_id": str(project.id), "decision_rule_id": str(rule.id)},
        )
    )


def apply(
    db: Session, project: Project, rule: DecisionRule, changes: dict[str, Any]
) -> DecisionRule:
    """Validate and apply fields (no commit). Unknown keys are the caller's bug."""
    if rule.is_default and any(changes.get(name) is not None for name in MATCH_FIELDS):
        raise BadRequestError("The default rule matches everything", code="default_has_no_match")
    for name in ("name", "priority", *MATCH_FIELDS):
        if name in changes:
            setattr(rule, name, changes[name])
    if "owner_kind" in changes or "owner_id" in changes:
        kind = changes.get("owner_kind", rule.owner_kind)
        owner = changes.get("owner_id")
        rule.owner_kind = kind
        rule.owner_role_id = rule.owner_user_id = None
        if kind in (ROLE, USER):
            checked = _check_spec(db, project, {"kind": kind, "id": owner})
            if kind == ROLE:
                rule.owner_role_id = uuid.UUID(checked["id"])
            else:
                rule.owner_user_id = uuid.UUID(checked["id"])
        elif kind != REQUIREMENT_OWNER:
            raise BadRequestError("Unknown decision owner kind", code="bad_owner")
    for name in ("required_reviewers", "optional_reviewers"):
        if name in changes:
            setattr(rule, name, [_check_spec(db, project, spec) for spec in changes[name]])
    return rule


def create(db: Session, project: Project, actor: User, data: dict[str, Any]) -> DecisionRule:
    rule = DecisionRule(project_id=project.id, created_by=actor.id, name=data["name"],
                        owner_kind=REQUIREMENT_OWNER)  # fmt: skip
    apply(db, project, rule, data)
    if rule.specificity == 0:
        raise BadRequestError(
            "A rule must match something: the default rule already matches everything",
            code="match_required",
        )
    db.add(rule)
    db.flush()
    _audit(db, project, actor, AuditAction.DECISION_RULE_CREATED, rule)
    db.commit()
    return rule


def update(
    db: Session, project: Project, actor: User, rule: DecisionRule, data: dict[str, Any]
) -> DecisionRule:
    apply(db, project, rule, data)
    if not rule.is_default and rule.specificity == 0:
        raise BadRequestError("A rule must match something", code="match_required")
    _audit(db, project, actor, AuditAction.DECISION_RULE_UPDATED, rule)
    db.commit()
    return rule


def delete(db: Session, project: Project, actor: User, rule: DecisionRule) -> None:
    if rule.is_default:
        raise ConflictError("The default rule cannot be deleted", code="default_rule")
    _audit(db, project, actor, AuditAction.DECISION_RULE_DELETED, rule)
    db.delete(rule)
    db.commit()
