"""Permission matrix (Affan — US-27, FR-48, NFR-27; generated from the catalogue).

Two layers:

1. **Catalogue × role.** For every default role and every permission, the effective permissions
   the access layer computes from the seeded database equal the spec table
   (``DEFAULT_ROLE_PERMISSIONS``) — including the Compliance Reviewer's protected-only grant.
2. **Routes × role.** Every Sprint 1 route that declares a permission is called by a member of
   each default role: holders get through (not 403/404), everyone else gets 403. The permission a
   route needs is read from the route's own declaration, so the matrix cannot drift from the code;
   ``test_every_permission_route_is_in_the_matrix`` fails when a new route is added without a case.
"""

import io
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.classification.budget import UnlimitedBudget, get_budget_guard
from app.classification.llm_client import get_llm_client
from app.core import security
from app.core.permissions import (
    DEFAULT_ROLE_PERMISSIONS,
    PERMISSIONS,
    PROTECTED_ONLY_GRANTS,
    DefaultRole,
)
from app.embeddings.model import HashingEmbedder, get_embedder
from app.models import (
    AnalysisRun,
    AnalysisRunStatus,
    AnalysisScope,
    Baseline,
    ChangeRequest,
    Channel,
    Clarification,
    DecisionRule,
    Document,
    DocumentFormat,
    Finding,
    FindingCategory,
    GraphState,
    Issue,
    IssueRequirement,
    JoinRequest,
    Message,
    OwnershipRequest,
    Project,
    Requirement,
    RequirementLink,
    Role,
    RolePermission,
    SrsDocument,
    SrsSection,
    Suggestion,
    User,
    Workspace,
)
from app.services import documents as document_service
from app.services import join_codes as join_code_service
from app.services.access import Scope, build_access_context
from app.services.membership import add_member, get_default_role
from app.services.storage import LocalFileStorage, get_storage
from app.services.users import create_user
from tests.api.test_access_invariants import _api_routes, _declarations
from tests.factories import make_docx


# ── 1. Catalogue × role ─────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("role", list(DefaultRole), ids=lambda role: role.value)
def test_each_default_role_holds_exactly_its_catalogue_permissions(
    db_session: Session, make_user: Callable[..., User], workspace: Workspace, role: DefaultRole
) -> None:
    member = make_user(role=role)

    context = build_access_context(db_session, member, Scope(workspace.id))

    expected = DEFAULT_ROLE_PERMISSIONS[role]
    for permission in PERMISSIONS:
        assert (permission in context.permissions) == (permission in expected), permission
    held_freely = {p for p in PERMISSIONS if context.can(p)}
    protected_only = {"finding.review"} if role is DefaultRole.COMPLIANCE_REVIEWER else set()
    assert held_freely == expected - protected_only


# ── 2. Routes × role ────────────────────────────────────────────────────────────────────────
@dataclass
class World:
    workspace: Workspace
    project: Project
    document: Document
    join_code_id: uuid.UUID
    join_request: JoinRequest
    viewer_role_id: uuid.UUID
    channel: Channel  # public, in the project
    target: User  # a Developer that member routes act on
    custom_role: Role  # an unused custom role ("Client reviewer")
    message: Message  # a chat message by the Owner in `channel`
    finding: Finding  # an Ambiguous finding about a requirement of `document`
    ownership_request: OwnershipRequest  # `target` asks to own that requirement
    run: AnalysisRun  # a finished analysis of `document`
    clarification: Clarification  # the question about `finding`
    issue: Issue  # ISS-1 by the Owner about the finding's requirement
    change_request: ChangeRequest  # RCR-1 by the Owner on the finding's requirement
    suggestion: Suggestion  # ready AI options for `finding`
    decision_rule: DecisionRule  # a non-default rule of the project
    baselines: tuple[Baseline, Baseline]  # two empty snapshots to compare
    graph_snapshot: GraphState  # the map frozen with the first baseline (US-50)
    other_requirement: Requirement  # a second requirement of `document` (links)
    link: RequirementLink  # the finding's requirement depends on `other_requirement`
    srs: tuple[SrsDocument, SrsDocument]  # a draft (with section 1.1_purpose) and another
    db: Session


@dataclass(frozen=True)
class Case:
    method: str
    path: str  # with {workspace_id}, {project_id}, {document_id}, {join_code_id}, {join_request_id}
    body: Callable[[World], dict[str, Any] | None] = lambda _: None
    upload: bool = False
    # For require_any_permission routes: the permission this particular request needs.
    needs: str | None = None
    # Author-only routes: {message_id} is a message the calling member posted just before.
    own_message: bool = False
    # Proposer-only routes: {change_request_id} is a change request the calling member opened.
    own_change_request: bool = False
    # The status a holder of the permission must get, when the request is meant to succeed; so a
    # 500 inside the route cannot pass as "allowed".
    ok: int | None = None


CASES = [
    Case("GET", "/api/v1/workspaces/{workspace_id}"),
    Case("PATCH", "/api/v1/workspaces/{workspace_id}", lambda _: {"name": "Renamed"}),
    Case("GET", "/api/v1/workspaces/{workspace_id}/roles"),
    Case("POST", "/api/v1/workspaces/{workspace_id}/projects", lambda _: {"name": "New"}),
    Case("GET", "/api/v1/workspaces/{workspace_id}/projects"),
    Case("GET", "/api/v1/projects/{project_id}"),
    Case("PATCH", "/api/v1/projects/{project_id}", lambda _: {"description": "x"}),
    Case("GET", "/api/v1/projects/{project_id}/context"),
    Case("PUT", "/api/v1/projects/{project_id}/context", lambda _: {"fields": {"purpose": "x"}}),
    Case("GET", "/api/v1/projects/{project_id}/context/versions"),
    Case(
        "POST",
        "/api/v1/projects/{project_id}/context/draft",
        lambda w: {"document_id": str(w.document.id)},
    ),
    Case("POST", "/api/v1/projects/{project_id}/documents", upload=True, needs="doc.upload"),
    Case("GET", "/api/v1/projects/{project_id}/documents"),
    Case("GET", "/api/v1/documents/{document_id}"),
    Case("GET", "/api/v1/projects/{project_id}/requirements"),
    Case(
        "POST",
        "/api/v1/workspaces/{workspace_id}/join-codes",
        lambda w: {"role_id": str(w.viewer_role_id)},
    ),
    Case("GET", "/api/v1/workspaces/{workspace_id}/join-codes"),
    Case("DELETE", "/api/v1/join-codes/{join_code_id}"),
    Case("GET", "/api/v1/workspaces/{workspace_id}/join-requests"),
    Case("GET", "/api/v1/workspaces/{workspace_id}/join-requests/{join_request_id}/decision"),
    Case(
        "POST",
        "/api/v1/workspaces/{workspace_id}/join-requests/{join_request_id}/decision",
        lambda _: {"approve": False},
    ),
    # Sprint 2 — channels (US-28)
    Case("POST", "/api/v1/projects/{project_id}/channels", lambda _: {"name": "new-one"}),
    Case("GET", "/api/v1/projects/{project_id}/channels"),
    Case("GET", "/api/v1/channels/{channel_id}"),
    Case("PATCH", "/api/v1/channels/{channel_id}", lambda _: {"topic": "t"}),
    Case("POST", "/api/v1/channels/{channel_id}/archive"),
    Case("POST", "/api/v1/channels/{channel_id}/read"),
    Case("GET", "/api/v1/channels/{channel_id}/members"),
    Case("POST", "/api/v1/channels/{channel_id}/members", lambda w: {"user_id": str(w.target.id)}),
    Case("DELETE", "/api/v1/channels/{channel_id}/members/{user_id}"),
    # Sprint 2 — members, roles, project-level roles (US-26, US-49)
    Case("GET", "/api/v1/workspaces/{workspace_id}/members"),
    Case(
        "PATCH",
        "/api/v1/workspaces/{workspace_id}/members/{user_id}",
        lambda w: {"role_id": str(w.viewer_role_id)},
    ),
    Case("DELETE", "/api/v1/workspaces/{workspace_id}/members/{user_id}"),
    Case("GET", "/api/v1/workspaces/{workspace_id}/needs-reassignment"),
    Case(
        "POST",
        "/api/v1/workspaces/{workspace_id}/roles",
        lambda _: {"name": "Tech lead", "permissions": ["view", "rcr.review"]},
    ),
    Case("PATCH", "/api/v1/roles/{role_id}", lambda _: {"description": "Reviews only"}),
    Case("DELETE", "/api/v1/roles/{role_id}"),
    Case("GET", "/api/v1/projects/{project_id}/members"),
    Case("PUT", "/api/v1/projects/{project_id}/members/{user_id}", lambda _: {}),
    # Sprint 2 — messages and the map (US-29, US-14 v0)
    Case("GET", "/api/v1/channels/{channel_id}/messages"),
    Case("POST", "/api/v1/channels/{channel_id}/messages", lambda _: {"body": "hi"}),
    Case("GET", "/api/v1/messages/{message_id}"),
    Case("GET", "/api/v1/messages/{message_id}/thread"),
    Case("PATCH", "/api/v1/messages/{message_id}", lambda _: {"body": "edited"}, own_message=True),
    Case("DELETE", "/api/v1/messages/{message_id}", own_message=True),
    Case("GET", "/api/v1/projects/{project_id}/graph"),
    # Sprint 2 — requirement posts (US-30 backend)
    Case(
        "POST",
        "/api/v1/channels/{channel_id}/requirement-posts",
        lambda _: {
            "fields": {
                "template": "free_text",
                "slots": {"statement": "The system shall keep audit logs for seven years."},
                "type": "functional",
                "priority": "must",
            }
        },
    ),
    # Sprint 2 — findings (US-07)
    Case("GET", "/api/v1/projects/{project_id}/findings"),
    Case("GET", "/api/v1/findings/{finding_id}"),
    # Sprint 3 — lifecycle, sign-off and review (Parth, US-37, US-10). The world's requirement is
    # Proposed and not protected: holders of baseline.manage may start its review; the sign-off is
    # refused with 409 (not protected) — past the permission check; the review confirms the finding.
    Case("GET", "/api/v1/requirements/{requirement_id}"),
    Case(
        "PATCH",
        "/api/v1/requirements/{requirement_id}",
        lambda _: {"state": "Under_Review", "version": 1},
        needs="baseline.manage",
    ),
    Case("POST", "/api/v1/requirements/{requirement_id}/signoff", lambda _: {"version": 1}),
    Case("POST", "/api/v1/findings/{finding_id}/review", lambda _: {"action": "confirm"}),
    Case("GET", "/api/v1/findings/{finding_id}/reviews"),
    # Sprint 3 — clarification questions (Madhav, US-09). The world's finding already has one,
    # so requesting another is a 409 — past the permission check.
    Case("GET", "/api/v1/findings/{finding_id}/clarification"),
    Case("POST", "/api/v1/findings/{finding_id}/clarification"),
    Case(
        "POST",
        "/api/v1/clarifications/{clarification_id}/answer",
        lambda _: {"resolution": "Under 2 seconds at p95"},
    ),
    # Sprint 3 — a run's results, behind the result card (Keval, US-31)
    Case("GET", "/api/v1/analysis-runs/{analysis_run_id}"),
    # Sprint 3 — the composer and ownership (Bansil, US-30, US-36). Deciding is for the owner or
    # whoever may reassign; the world's requirement has no owner, so it needs baseline.manage.
    Case(
        "POST",
        "/api/v1/projects/{project_id}/requirements",
        lambda w: {
            "fields": {
                "template": "free_text",
                "slots": {"statement": "The system shall keep audit logs for seven years."},
                "type": "functional",
                "priority": "must",
                "channel_id": str(w.channel.id),
            }
        },
    ),
    Case("POST", "/api/v1/requirements/{requirement_id}/ownership-requests", lambda _: {}),
    Case("GET", "/api/v1/requirements/{requirement_id}/ownership-requests"),
    Case(
        "POST",
        "/api/v1/ownership-requests/{ownership_request_id}/decision",
        lambda _: {"accept": True},
        needs="baseline.manage",
    ),
    # Sprint 3 — the live map's shared layout (Dhavni, US-14)
    Case(
        "PUT",
        "/api/v1/projects/{project_id}/graph/positions",
        lambda w: {
            "positions": [{"requirement_id": str(w.finding.requirement_id), "x": 1, "y": 2}]
        },
    ),
    # Sprint 3 — similar-requirement hints (Heet, FR-83)
    Case("POST", "/api/v1/projects/{project_id}/similar", lambda _: {"text": "audit logs"}),
    # Sprint 4 — issues (Dhavni, US-52). Labels are for issue managers; the world's issue is
    # the Owner's, so nobody else may edit its title either.
    Case("GET", "/api/v1/projects/{project_id}/issues"),
    Case(
        "POST",
        "/api/v1/projects/{project_id}/issues",
        lambda w: {"title": "Unclear speed", "requirement_ids": [str(w.finding.requirement_id)]},
    ),
    Case("GET", "/api/v1/issues/{issue_id}"),
    Case("PATCH", "/api/v1/issues/{issue_id}", lambda _: {"labels": ["ux"]}, needs="issue.manage"),
    Case("GET", "/api/v1/issues/{issue_id}/comments"),
    Case("POST", "/api/v1/issues/{issue_id}/comments", lambda _: {"body": "Agreed."}),
    # Sprint 4 — change requests and raised concerns (Bansil, US-33, US-56)
    Case(
        "POST",
        "/api/v1/requirements/{requirement_id}/change-requests",
        lambda _: {"proposed_body": "It shall answer within 2 s.", "reason": "Make it measurable"},
    ),
    Case("GET", "/api/v1/projects/{project_id}/change-requests"),
    Case("GET", "/api/v1/change-requests/{change_request_id}"),
    Case(
        "POST",
        "/api/v1/projects/{project_id}/concerns",
        lambda w: {
            "category": "Ambiguous",
            "requirement_ids": [str(w.finding.requirement_id)],
            "explanation": "Nobody can test what fast means here.",
        },
    ),
    # Sprint 4 — impact and consequence checks (Madhav, US-11, US-34)
    Case("GET", "/api/v1/requirements/{requirement_id}/impact"),
    Case("GET", "/api/v1/change-requests/{change_request_id}/checks"),
    Case("POST", "/api/v1/change-requests/{change_request_id}/checks/rerun"),
    # Sprint 4 — review, merge and versions (Parth, US-35, US-12). The world's request is not
    # approved, so a merger gets 409 (unmet conditions) — through the permission, refused later.
    Case(
        "PATCH",
        "/api/v1/change-requests/{change_request_id}",
        lambda _: {"reason": "A clearer reason"},
        own_change_request=True,
    ),
    Case("GET", "/api/v1/change-requests/{change_request_id}/reviews"),
    Case(
        "POST",
        "/api/v1/change-requests/{change_request_id}/reviews",
        lambda _: {"decision": "comment", "rationale": "Reads well."},
    ),
    Case(
        "POST",
        "/api/v1/change-requests/{change_request_id}/reviewers",
        lambda w: {"reviewer_id": str(w.target.id)},
        needs="rcr.merge",
    ),
    Case("GET", "/api/v1/change-requests/{change_request_id}/agreement"),
    Case("POST", "/api/v1/change-requests/{change_request_id}/merge", lambda _: {}),
    Case(
        "POST",
        "/api/v1/change-requests/{change_request_id}/close",
        lambda _: {"reason": "Not needed after all"},
    ),
    Case("POST", "/api/v1/change-requests/{change_request_id}/withdraw", own_change_request=True),
    Case("GET", "/api/v1/requirements/{requirement_id}/versions"),
    Case("POST", "/api/v1/projects/{project_id}/lint", lambda _: {"text": "It shall be fast."}),
    Case(
        "POST", "/api/v1/projects/{project_id}/preflight", lambda _: {"text": "It shall be fast."}
    ),
    Case(
        "POST",
        "/api/v1/projects/{project_id}/improve-wording",
        lambda _: {"text": "It shall be fast."},
    ),
    Case("GET", "/api/v1/projects/{project_id}/thresholds/preview"),
    Case("POST", "/api/v1/projects/{project_id}/reanalyse"),
    Case("GET", "/api/v1/findings/{finding_id}/suggestions"),
    Case(
        "POST",
        "/api/v1/findings/{finding_id}/suggestions/regenerate",
        lambda _: {"instruction": "Keep it short"},
    ),
    Case("POST", "/api/v1/suggestions/{suggestion_id}/feedback", lambda _: {"action": "deferred"}),
    Case(
        "POST",
        "/api/v1/suggestions/{suggestion_id}/rating",
        lambda _: {"option_index": 0, "rating": 4},
    ),
    Case("GET", "/api/v1/projects/{project_id}/suggestions/stats"),
    Case("GET", "/api/v1/projects/{project_id}/decision-rules"),
    Case(
        "POST",
        "/api/v1/projects/{project_id}/decision-rules",
        lambda _: {"name": "M", "match_label": "x", "owner_kind": "requirement_owner"},
    ),
    Case("PATCH", "/api/v1/decision-rules/{decision_rule_id}", lambda _: {"priority": 7}),
    Case("DELETE", "/api/v1/decision-rules/{decision_rule_id}"),
    Case("GET", "/api/v1/findings/{finding_id}/decision"),
    Case("GET", "/api/v1/issues/{issue_id}/decision"),
    Case("GET", "/api/v1/change-requests/{change_request_id}/decision"),
    Case("POST", "/api/v1/projects/{project_id}/baselines", lambda _: {"label": "v-matrix"}),
    Case("GET", "/api/v1/projects/{project_id}/baselines"),
    Case("GET", "/api/v1/baselines/{baseline_id}"),
    Case("GET", "/api/v1/baselines/{baseline_id}/compare/{other_baseline_id}"),
    Case("GET", "/api/v1/projects/{project_id}/analytics"),
    Case("GET", "/api/v1/workspaces/{workspace_id}/analytics"),
    # Sprint 6 — change log, time slider, preview, timeline (Dhavni)
    Case("GET", "/api/v1/projects/{project_id}/changes"),
    Case("GET", "/api/v1/projects/{project_id}/changes/summary"),
    Case("PUT", "/api/v1/projects/{project_id}/changes/seen"),
    Case("GET", "/api/v1/projects/{project_id}/graph/revisions"),
    Case("GET", "/api/v1/projects/{project_id}/graph/revisions/{graph_snapshot_id}"),
    Case("GET", "/api/v1/change-requests/{change_request_id}/graph-preview"),
    Case("GET", "/api/v1/requirements/{requirement_id}/timeline"),
    # Sprint 6 — discussion, votes, watch and links (Madhav)
    Case("GET", "/api/v1/requirements/{requirement_id}/social"),
    Case("GET", "/api/v1/requirements/{requirement_id}/comments"),
    Case("POST", "/api/v1/requirements/{requirement_id}/comments", lambda _: {"body": "Agreed."}),
    Case("GET", "/api/v1/requirements/{requirement_id}/votes"),
    Case("PUT", "/api/v1/requirements/{requirement_id}/vote", lambda _: {"stance": "support"}),
    Case("DELETE", "/api/v1/requirements/{requirement_id}/vote"),
    Case("GET", "/api/v1/change-requests/{change_request_id}/votes"),
    Case("PUT", "/api/v1/change-requests/{change_request_id}/vote", lambda _: {"stance": "oppose"}),
    Case("DELETE", "/api/v1/change-requests/{change_request_id}/vote"),
    Case("GET", "/api/v1/requirements/{requirement_id}/watch"),
    Case("PUT", "/api/v1/requirements/{requirement_id}/watch"),
    Case("DELETE", "/api/v1/requirements/{requirement_id}/watch"),
    Case("GET", "/api/v1/issues/{issue_id}/watch"),
    Case("PUT", "/api/v1/issues/{issue_id}/watch"),
    Case("DELETE", "/api/v1/issues/{issue_id}/watch"),
    Case("GET", "/api/v1/change-requests/{change_request_id}/watch"),
    Case("PUT", "/api/v1/change-requests/{change_request_id}/watch"),
    Case("DELETE", "/api/v1/change-requests/{change_request_id}/watch"),
    Case("GET", "/api/v1/requirements/{requirement_id}/links"),
    Case(
        "POST",
        "/api/v1/requirements/{requirement_id}/links",
        lambda w: {"target_id": str(w.other_requirement.id), "kind": "related_to"},
    ),
    Case("DELETE", "/api/v1/requirements/{requirement_id}/links/{link_id}"),
    # Sprint 6 — severity, AI feedback, change summary paragraph (Keval)
    Case(
        "PATCH",
        "/api/v1/findings/{finding_id}/severity",
        lambda _: {"severity": "high", "reason": "Patient safety"},
    ),
    Case("GET", "/api/v1/projects/{project_id}/ai-feedback"),
    Case("PUT", "/api/v1/projects/{project_id}/ai-feedback/threshold", lambda _: {"threshold": 3}),
    Case("POST", "/api/v1/projects/{project_id}/changes/summary", lambda _: {"narrative": False}),
    # Sprint 6 — compliance protection (Parth)
    Case(
        "PUT",
        "/api/v1/requirements/{requirement_id}/protection",
        lambda _: {"protected": True, "reason": "GDPR"},
    ),
    Case(
        "POST",
        "/api/v1/projects/{project_id}/protection",
        lambda w: {"requirement_ids": [str(w.finding.requirement_id)]},
    ),
    Case("GET", "/api/v1/projects/{project_id}/compliance/queue", needs="req.protect"),
    Case("GET", "/api/v1/projects/{project_id}/compliance/audit"),
    # Sprint 6 — updated SRS, exports, open items (Bansil)
    Case("GET", "/api/v1/projects/{project_id}/srs/readiness"),
    Case("POST", "/api/v1/projects/{project_id}/srs", lambda _: {}),
    Case("GET", "/api/v1/projects/{project_id}/srs"),
    Case("GET", "/api/v1/srs/{srs_id}"),
    Case("PATCH", "/api/v1/srs/{srs_id}/sections/{key}", lambda _: {"action": "accept"}),
    Case("POST", "/api/v1/srs/{srs_id}/fidelity"),
    Case("POST", "/api/v1/srs/{srs_id}/publish"),
    Case("POST", "/api/v1/srs/{srs_id}/discard"),
    Case("GET", "/api/v1/srs/{srs_id}/compare/{other_srs_id}"),
    Case("GET", "/api/v1/srs/{srs_id}/export"),
    Case("GET", "/api/v1/srs/{srs_id}/open-items"),
    Case("GET", "/api/v1/baselines/{baseline_id}/export"),
    Case("GET", "/api/v1/projects/{project_id}/export"),
    Case("GET", "/api/v1/baselines/{baseline_id}/open-items"),
    Case("GET", "/api/v1/projects/{project_id}/open-items"),
]


def _declared_permission(method: str, path: str) -> tuple[str, ...]:
    for route_method, route in _api_routes():
        if route_method == method and route.path == path:
            return _declarations(route.dependant)[0].permissions
    raise AssertionError(f"{method} {path} is not a route of the app")


@pytest.fixture
def world(
    db_session: Session,
    workspace: Workspace,
    project: Project,
    make_user: Callable[..., User],
) -> World:
    owner = make_user(role=DefaultRole.OWNER)
    document = Document(
        workspace_id=workspace.id,
        project_id=project.id,
        uploaded_by=owner.id,
        filename="srs.docx",
        format=DocumentFormat.DOCX,
        size_bytes=1,
        sha256="0" * 64,
        storage_path="srs.docx",
    )
    db_session.add(document)
    db_session.commit()
    developer_role = get_default_role(db_session, DefaultRole.DEVELOPER).id
    code = join_code_service.create_code(
        db_session, workspace_id=workspace.id, creator=owner, role_id=developer_role,
        expires_in_days=7,
    )  # fmt: skip
    gated = join_code_service.create_code(
        db_session, workspace_id=workspace.id, creator=owner, role_id=developer_role,
        expires_in_days=7, requires_approval=True,
    )  # fmt: skip
    newcomer = create_user(
        db_session,
        email=f"new-{uuid.uuid4().hex[:8]}@example.com",
        password="correct-horse-battery-staple",
        full_name="Newcomer",
    )
    request = join_code_service.redeem(db_session, gated.code, newcomer)
    assert isinstance(request, JoinRequest)
    db_session.commit()
    viewer = get_default_role(db_session, DefaultRole.VIEWER).id
    channel = Channel(project_id=project.id, name="matrix", created_by=owner.id)
    db_session.add(channel)
    db_session.commit()
    target = make_user(role=DefaultRole.DEVELOPER)
    custom_role = Role(
        workspace_id=workspace.id,
        name="Client reviewer",
        permissions=[RolePermission(permission=p) for p in ("view", "rcr.review")],
    )
    db_session.add(custom_role)
    db_session.commit()
    message = Message(channel_id=channel.id, author_id=owner.id, body="hello")
    db_session.add(message)
    db_session.commit()
    vague = Requirement(document_id=document.id, project_id=project.id, body="It shall be fast.")
    db_session.add(vague)
    db_session.flush()
    finding = Finding(
        project_id=project.id,
        document_id=document.id,
        requirement_id=vague.id,
        category=FindingCategory.AMBIGUOUS,
        confidence=0.8,
        rationale="fast",
        original_ai_output={},
    )
    db_session.add(finding)
    db_session.commit()
    ownership_request = OwnershipRequest(requirement_id=vague.id, requester_id=target.id)
    run = AnalysisRun(
        project_id=project.id,
        scope=AnalysisScope.DOCUMENT,
        subject_id=document.id,
        status=AnalysisRunStatus.DONE,
    )
    clarification = Clarification(finding_id=finding.id, question="What does 'fast' mean?")
    db_session.add_all([ownership_request, run, clarification])
    db_session.commit()
    issue = Issue(project_id=project.id, number=1, title="Matrix issue", author_id=owner.id)
    db_session.add(issue)
    db_session.flush()
    db_session.add(IssueRequirement(issue_id=issue.id, requirement_id=vague.id))
    change_request = ChangeRequest(
        project_id=project.id,
        requirement_id=vague.id,
        number=1,
        proposer_id=owner.id,
        base_version=1,
        proposed_body="It shall answer within 2 s.",
        reason="Measurable",
    )
    db_session.add(change_request)
    suggestion = Suggestion(
        finding_id=finding.id,
        project_id=project.id,
        category="Ambiguous",
        status="ready",
        options=[{"text": "It shall answer within 2 s.", "target": None,
                  "target_requirement_id": str(vague.id), "trade_off": "t",
                  "confidence": 0.6, "tbd_slots": []}],
    )  # fmt: skip
    db_session.add(suggestion)
    decision_rule = DecisionRule(project_id=project.id, name="Matrix", match_label="m",
                                 owner_kind="requirement_owner")  # fmt: skip
    baselines = tuple(
        Baseline(project_id=project.id, label=label, baseline_revision=0, requirement_count=0)
        for label in ("a", "b")
    )
    db_session.add_all([decision_rule, *baselines])
    db_session.commit()
    graph_snapshot = GraphState(project_id=project.id, graph_revision=0, baseline_revision=0,
                                baseline_id=baselines[0].id, nodes=[], edges=[])  # fmt: skip
    db_session.add(graph_snapshot)
    db_session.commit()
    other = Requirement(document_id=document.id, project_id=project.id, body="It shall log.")
    db_session.add(other)
    db_session.flush()
    link = RequirementLink(project_id=project.id, source_id=vague.id, target_id=other.id,
                           kind="depends_on")  # fmt: skip
    db_session.add(link)
    db_session.commit()
    srs = tuple(
        SrsDocument(project_id=project.id, baseline_revision=0, status="draft",
                    requirements=[{"requirement_id": str(vague.id), "label": None,
                                   "version": 1, "state": "Approved",
                                   "body": "It shall be fast."}])
        for _ in range(2)
    )  # fmt: skip
    db_session.add_all(srs)
    db_session.flush()
    db_session.add(SrsSection(srs_id=srs[0].id, key="1.1_purpose", order=1, title="1.1 Purpose",
                              kind="narrative", body="Why.", source="llm", status="pending"))  # fmt: skip
    db_session.commit()
    return World(
        workspace=workspace,
        project=project,
        document=document,
        join_code_id=code.join_code.id,
        join_request=request,
        viewer_role_id=viewer,
        channel=channel,
        target=target,
        custom_role=custom_role,
        message=message,
        finding=finding,
        ownership_request=ownership_request,
        run=run,
        clarification=clarification,
        issue=issue,
        change_request=change_request,
        suggestion=suggestion,
        decision_rule=decision_rule,
        baselines=(baselines[0], baselines[1]),
        graph_snapshot=graph_snapshot,
        other_requirement=other,
        link=link,
        srs=(srs[0], srs[1]),
        db=db_session,
    )


@pytest.fixture
def api(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    from app.main import app

    monkeypatch.setattr(document_service, "dispatch_processing", lambda _id: "task-1")
    app.dependency_overrides[get_storage] = lambda: LocalFileStorage(tmp_path / "uploads")
    app.dependency_overrides[get_embedder] = HashingEmbedder
    app.dependency_overrides[get_llm_client] = lambda: None  # no model: AI routes answer 503
    app.dependency_overrides[get_budget_guard] = UnlimitedBudget
    yield client
    for dependency in (get_storage, get_embedder, get_llm_client, get_budget_guard):
        app.dependency_overrides.pop(dependency, None)


def _call(api: TestClient, case: Case, world: World, user: User) -> int:
    message_id = world.message.id
    if case.own_message:
        own = Message(channel_id=world.channel.id, author_id=user.id, body="mine")
        world.db.add(own)
        world.db.commit()
        message_id = own.id
    change_request_id = world.change_request.id
    if case.own_change_request:
        mine = ChangeRequest(
            project_id=world.project.id,
            requirement_id=world.change_request.requirement_id,
            number=world.change_request.number + 1 + world.db.query(ChangeRequest).count(),
            proposer_id=user.id,
            base_version=1,
            proposed_body="It shall answer within 3 s.",
            reason="Mine",
        )
        world.db.add(mine)
        world.db.commit()
        change_request_id = mine.id
    path = case.path.format(
        message_id=message_id,
        finding_id=world.finding.id,
        workspace_id=world.workspace.id,
        project_id=world.project.id,
        document_id=world.document.id,
        join_code_id=world.join_code_id,
        join_request_id=world.join_request.id,
        channel_id=world.channel.id,
        user_id=world.target.id,
        role_id=world.custom_role.id,
        requirement_id=world.finding.requirement_id,
        ownership_request_id=world.ownership_request.id,
        analysis_run_id=world.run.id,
        clarification_id=world.clarification.id,
        issue_id=world.issue.id,
        change_request_id=change_request_id,
        suggestion_id=world.suggestion.id,
        decision_rule_id=world.decision_rule.id,
        baseline_id=world.baselines[0].id,
        other_baseline_id=world.baselines[1].id,
        graph_snapshot_id=world.graph_snapshot.id,
        link_id=world.link.id,
        srs_id=world.srs[0].id,
        other_srs_id=world.srs[1].id,
        key="1.1_purpose",
    )
    headers = {"Authorization": f"Bearer {security.create_access_token(user.id)[0]}"}
    body = case.body(world)
    if case.upload:
        files = {"file": ("srs.docx", io.BytesIO(make_docx("REQ-001: It shall work.")), "x")}
        return api.request(case.method, path, files=files, headers=headers).status_code
    return api.request(case.method, path, json=body, headers=headers).status_code


@pytest.mark.parametrize("role", list(DefaultRole), ids=lambda role: role.value)
@pytest.mark.parametrize("case", CASES, ids=lambda case: f"{case.method} {case.path}")
def test_route_is_allowed_exactly_for_holders_of_its_permission(
    api: TestClient,
    db_session: Session,
    world: World,
    make_user: Callable[..., User],
    case: Case,
    role: DefaultRole,
) -> None:
    declared = _declared_permission(case.method, case.path)
    needed = case.needs or declared[0]
    member = make_user(role=role)

    status = _call(api, case, world, member)

    # A protected-only grant (the Compliance Reviewer's finding.review) does not count here: the
    # world's requirement is not protected.
    held = {p for p in DEFAULT_ROLE_PERMISSIONS[role] if (role, p) not in PROTECTED_ONLY_GRANTS}
    if needed in held:
        assert status not in (401, 403, 404), f"{role.value} should pass, got {status}"
        if case.ok is not None:
            assert status == case.ok, f"{role.value} should get {case.ok}, got {status}"
    else:
        assert status == 403, f"{role.value} should be refused, got {status}"


def test_every_permission_route_is_in_the_matrix() -> None:
    covered = {(case.method, case.path) for case in CASES}
    declared = {
        (method, route.path)
        for method, route in _api_routes()
        if _declarations(route.dependant)[0].kind in ("permission", "any_permission")
        and not route.path.startswith("/api/v1/reports")
    }
    assert declared <= covered, f"add these routes to CASES: {sorted(declared - covered)}"


# ── 3. Custom roles × routes (US-49) ────────────────────────────────────────────────────────
CUSTOM_ROLES = {
    # The Sprint 2 exit criterion: reviews change requests but never proposes.
    "External reviewer": frozenset({"view", "message.post", "req.comment", "rcr.review"}),
    "Channel steward": frozenset({"view", "message.post", "channel.manage"}),
    "Read only": frozenset({"view"}),
}


@pytest.mark.parametrize("name", list(CUSTOM_ROLES))
@pytest.mark.parametrize("case", CASES, ids=lambda case: f"{case.method} {case.path}")
def test_a_custom_role_gets_exactly_its_permissions(
    api: TestClient,
    db_session: Session,
    world: World,
    make_user: Callable[..., User],
    case: Case,
    name: str,
) -> None:
    held = CUSTOM_ROLES[name]
    role = Role(
        workspace_id=world.workspace.id,
        name=name,
        permissions=[RolePermission(permission=p) for p in sorted(held)],
    )
    db_session.add(role)
    db_session.commit()
    member = make_user(role=None)
    add_member(db_session, workspace_id=world.workspace.id, user_id=member.id, role_id=role.id)
    needed = case.needs or _declared_permission(case.method, case.path)[0]

    status = _call(api, case, world, member)

    if needed in held:
        assert status not in (401, 403, 404), f"{name} should pass, got {status}"
        if case.ok is not None:
            assert status == case.ok, f"{name} should get {case.ok}, got {status}"
    else:
        assert status == 403, f"{name} should be refused, got {status}"


def test_a_client_reviewer_cannot_propose_but_can_comment() -> None:
    """The exit criterion in one line, read from the routes' own declarations."""
    reviewer = CUSTOM_ROLES["External reviewer"]
    propose = _declared_permission("POST", "/api/v1/channels/{channel_id}/requirement-posts")
    post_message = _declared_permission("POST", "/api/v1/channels/{channel_id}/messages")
    assert propose[0] not in reviewer
    assert post_message[0] in reviewer
