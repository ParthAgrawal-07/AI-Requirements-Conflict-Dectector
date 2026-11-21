"""Decision rules API (Parth — US-57, FR-65, FR-100, DR-23; design update §11.7).

==========================================  ===================================================
``GET /projects/{p}/decision-rules``        the rules, most specific first (``view``)
``POST /projects/{p}/decision-rules``       add a rule (``project.manage``)
``PATCH /decision-rules/{r}``               edit it; the default rule may change its owner and
                                            reviewers, never its match (``project.manage``)
``DELETE /decision-rules/{r}``              remove it; never the default (``project.manage``)
``GET /findings/{f}/decision``              who decides, and by which rule (``view``)
``GET /issues/{i}/decision``                the same for an issue
``GET /change-requests/{c}/decision``       the same for a change request
==========================================  ===================================================
"""

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import DbSession, requires
from app.core.errors import NotFoundError
from app.models import ChangeRequest, Finding, FindingCategory, Issue, Project, Role, User
from app.models.decision_rule import DecisionRule
from app.schemas.common import ErrorResponse
from app.services import decision_rules as rules
from app.services.access import AccessContext, Scope, register_scope_resolver

router = APIRouter(tags=["decision rules"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
}
OwnerKind = Literal["role", "user", "requirement_owner"]


class ReviewerSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["role", "user"]
    id: uuid.UUID


class RuleFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    priority: int | None = Field(default=None, ge=0, le=1000)
    match_category: FindingCategory | None = None
    match_label: str | None = Field(default=None, min_length=1, max_length=64)
    match_group: str | None = Field(default=None, min_length=1, max_length=120)
    match_req_type: Literal["functional", "non_functional", "constraint"] | None = None
    match_protected: bool | None = None
    owner_kind: OwnerKind | None = None
    owner_id: uuid.UUID | None = None
    required_reviewers: list[ReviewerSpec] | None = Field(default=None, max_length=5)
    optional_reviewers: list[ReviewerSpec] | None = Field(default=None, max_length=10)

    def changes(self) -> dict[str, Any]:
        data = self.model_dump(exclude_unset=True, mode="json")
        if "match_category" in data and data["match_category"] is not None:
            data["match_category"] = str(data["match_category"])
        return data


class RuleCreate(RuleFields):
    name: str = Field(min_length=1, max_length=120)
    owner_kind: OwnerKind


class RuleUpdate(RuleFields):
    name: str | None = Field(default=None, min_length=1, max_length=120)


class NamedRef(BaseModel):
    kind: str
    id: uuid.UUID | None
    name: str


class RuleRead(BaseModel):
    id: uuid.UUID
    name: str
    priority: int
    is_default: bool
    specificity: int
    match_category: str | None
    match_label: str | None
    match_group: str | None
    match_req_type: str | None
    match_protected: bool | None
    owner: NamedRef
    required_reviewers: list[NamedRef]
    optional_reviewers: list[NamedRef]


class PersonRef(BaseModel):
    id: uuid.UUID
    full_name: str


class DecisionRead(BaseModel):
    rule_id: uuid.UUID | None
    rule_name: str
    is_default: bool
    owner_kind: str
    owners: list[PersonRef]  # who may make the decision now
    required_reviewers: list[NamedRef]
    sentence: str  # "Decides: Meera — rule Protected requirements"


def _ref(db: Session, kind: str, raw: str | uuid.UUID | None) -> NamedRef:
    if kind == "requirement_owner" or raw is None:
        return NamedRef(kind=kind, id=None, name="the requirement owner")
    target = raw if isinstance(raw, uuid.UUID) else uuid.UUID(raw)
    row = db.get(Role, target) if kind == "role" else db.get(User, target)
    name = (row.name if isinstance(row, Role) else row.full_name) if row else "(removed)"
    return NamedRef(kind=kind, id=target, name=name)


def _rule_read(db: Session, rule: DecisionRule) -> RuleRead:
    owner = rule.owner_role_id if rule.owner_kind == "role" else rule.owner_user_id
    return RuleRead(
        id=rule.id,
        name=rule.name,
        priority=rule.priority,
        is_default=rule.is_default,
        specificity=rule.specificity,
        match_category=rule.match_category,
        match_label=rule.match_label,
        match_group=rule.match_group,
        match_req_type=rule.match_req_type,
        match_protected=rule.match_protected,
        owner=_ref(db, rule.owner_kind, owner),
        required_reviewers=[_ref(db, s["kind"], s["id"]) for s in rule.required_reviewers],
        optional_reviewers=[_ref(db, s["kind"], s["id"]) for s in rule.optional_reviewers],
    )


def _project(db: Session, project_id: uuid.UUID) -> Project:
    project = db.get(Project, project_id)
    if project is None:  # cannot happen after require_permission; defensive
        raise NotFoundError("Project not found")
    return project


def _rule(db: Session, rule_id: uuid.UUID) -> tuple[DecisionRule, Project]:
    rule = db.get(DecisionRule, rule_id)
    project = db.get(Project, rule.project_id) if rule else None
    if rule is None or project is None:  # cannot happen after require_permission; defensive
        raise NotFoundError("Decision rule not found")
    return rule, project


def decision_read(db: Session, item: Finding | Issue | ChangeRequest) -> DecisionRead:
    project = _project(db, item.project_id)
    decision, facts = rules.decision_for(db, item)
    engine = rules.DecisionRuleEngine(db)
    owners = engine.owners(project, decision, facts)
    return DecisionRead(
        rule_id=uuid.UUID(decision.rule_id) if decision.rule_id else None,
        rule_name=decision.rule_name,
        is_default=decision.is_default,
        owner_kind=decision.owner_kind,
        owners=[PersonRef(id=u.id, full_name=u.full_name) for u in owners],
        required_reviewers=[_ref(db, s["kind"], s["id"]) for s in decision.required_reviewers],
        sentence=f"Decides: {engine.owner_name(decision, owners)} — rule {decision.rule_name}",
    )


@router.get(
    "/projects/{project_id}/decision-rules",
    response_model=list[RuleRead],
    summary="The project's decision rules",
    responses=_ERRORS,
)
def list_rules(
    project_id: uuid.UUID, ctx: Annotated[AccessContext, requires("view")], db: DbSession
) -> list[RuleRead]:
    found = rules.rules_of(db, project_id)
    found.sort(key=lambda r: (r.is_default, -r.specificity, r.priority, r.created_at))
    return [_rule_read(db, rule) for rule in found]


@router.post(
    "/projects/{project_id}/decision-rules",
    response_model=RuleRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a decision rule",
    responses=_ERRORS,
)
def create_rule(
    project_id: uuid.UUID,
    body: RuleCreate,
    ctx: Annotated[AccessContext, requires("project.manage")],
    db: DbSession,
) -> RuleRead:
    rule = rules.create(db, _project(db, project_id), ctx.user, body.changes())
    return _rule_read(db, rule)


@router.patch(
    "/decision-rules/{decision_rule_id}",
    response_model=RuleRead,
    summary="Edit a decision rule (open items pick it up at their next update)",
    responses=_ERRORS,
)
def update_rule(
    decision_rule_id: uuid.UUID,
    body: RuleUpdate,
    ctx: Annotated[AccessContext, requires("project.manage")],
    db: DbSession,
) -> RuleRead:
    rule, project = _rule(db, decision_rule_id)
    return _rule_read(db, rules.update(db, project, ctx.user, rule, body.changes()))


@router.delete(
    "/decision-rules/{decision_rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a decision rule (not the default)",
    responses=_ERRORS,
)
def delete_rule(
    decision_rule_id: uuid.UUID,
    ctx: Annotated[AccessContext, requires("project.manage")],
    db: DbSession,
) -> None:
    rule, project = _rule(db, decision_rule_id)
    rules.delete(db, project, ctx.user, rule)


@router.get(
    "/findings/{finding_id}/decision",
    response_model=DecisionRead,
    summary="Who decides this finding",
    responses=_ERRORS,
)
def finding_decision(
    finding_id: uuid.UUID, ctx: Annotated[AccessContext, requires("view")], db: DbSession
) -> DecisionRead:
    finding = db.get(Finding, finding_id)
    if finding is None:  # defensive
        raise NotFoundError("Finding not found")
    return decision_read(db, finding)


@router.get(
    "/issues/{issue_id}/decision",
    response_model=DecisionRead,
    summary="Who decides this issue",
    responses=_ERRORS,
)
def issue_decision(
    issue_id: uuid.UUID, ctx: Annotated[AccessContext, requires("view")], db: DbSession
) -> DecisionRead:
    issue = db.get(Issue, issue_id)
    if issue is None:  # defensive
        raise NotFoundError("Issue not found")
    return decision_read(db, issue)


@router.get(
    "/change-requests/{change_request_id}/decision",
    response_model=DecisionRead,
    summary="Who decides this change request",
    responses=_ERRORS,
)
def change_request_decision(
    change_request_id: uuid.UUID, ctx: Annotated[AccessContext, requires("view")], db: DbSession
) -> DecisionRead:
    change_request = db.get(ChangeRequest, change_request_id)
    if change_request is None:  # defensive
        raise NotFoundError("Change request not found")
    return decision_read(db, change_request)


def _rule_scope(db: Session, rule_id: uuid.UUID) -> Scope | None:
    rule = db.get(DecisionRule, rule_id)
    project = db.get(Project, rule.project_id) if rule else None
    return None if project is None else Scope(project.workspace_id, project.id)


register_scope_resolver("decision_rule_id", _rule_scope)
