"""Severity of a finding: proposed by rule, overridable by a reviewer (Keval — US-08, FR-42).

Severity says **how bad** a problem would be if it is real; confidence says **how sure** the
finder is. The two are separate fields and the UI shows both. Severity is proposed by fixed
rules from facts the database already holds — never by the LLM — so it can always be explained:

====================  =========================================================================
Base by category      Conflicting, Ambiguous, Incomplete: medium; Duplicate, Dependent: low
One level up          a requirement involved is **protected** (DR-05), is a *Must*, or (for a
                      conflict) is already in the agreed baseline
High                  a conflict with confidence ≥ 0.85 where any of the above holds
One level down        confidence below 0.6 (an uncertain finding is not a top priority)
====================  =========================================================================

A rule check (US-58) keeps the severity its rule defines, a raised concern (US-56) the one its
author chose. A reviewer with ``finding.review`` may override any of them with a reason
(:func:`override`): ``severity_proposed`` keeps the original, the override is audited, and the
conflict-issue labels and consequence-report risk (US-34) read the severity in force.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.errors import BadRequestError
from app.models import (
    AuditAction,
    AuditLog,
    Finding,
    FindingCategory,
    Project,
    Requirement,
    RequirementState,
    Severity,
    User,
)

ORDER = (Severity.LOW, Severity.MEDIUM, Severity.HIGH)
RANK = {s: i for i, s in enumerate(ORDER)}
BASE = {
    FindingCategory.CONFLICTING: Severity.MEDIUM,
    FindingCategory.AMBIGUOUS: Severity.MEDIUM,
    FindingCategory.INCOMPLETE: Severity.MEDIUM,
    FindingCategory.DUPLICATE: Severity.LOW,
    FindingCategory.DEPENDENT: Severity.LOW,
}
HIGH_CONFIDENCE = 0.85
LOW_CONFIDENCE = 0.6
IN_BASELINE = (RequirementState.APPROVED, RequirementState.IMPLEMENTED)
MAX_REASON = 500


@dataclass(frozen=True)
class Proposal:
    severity: Severity
    reason: str  # names facts, never requirement text


def _step(severity: Severity, by: int) -> Severity:
    return ORDER[max(0, min(len(ORDER) - 1, RANK[severity] + by))]


def propose(
    category: FindingCategory, confidence: float, requirements: Sequence[Requirement]
) -> Proposal:
    """The severity the rules give a finding of ``category`` about ``requirements``."""
    severity = BASE[category]
    reasons = [f"{category.value}: {severity.value} by default"]
    raisers = []
    if any(r.is_protected for r in requirements):
        raisers.append("a protected requirement is involved")
    if any((r.priority or "").lower() == "must" for r in requirements):
        raisers.append("a Must requirement is involved")
    if category is FindingCategory.CONFLICTING and any(
        r.state in IN_BASELINE for r in requirements
    ):
        raisers.append("it touches the agreed baseline")
    if raisers:
        if category is FindingCategory.CONFLICTING and confidence >= HIGH_CONFIDENCE:
            severity = Severity.HIGH
        else:
            severity = _step(severity, 1)
        reasons.append("raised because " + " and ".join(raisers))
    if confidence < LOW_CONFIDENCE and severity is not Severity.LOW:
        severity = _step(severity, -1)
        reasons.append(f"lowered because confidence is {confidence:.2f}")
    return Proposal(severity, "; ".join(reasons))


def apply_proposal(finding: Finding, requirements: Sequence[Requirement]) -> None:
    """Give a new AI finding its proposed severity (no commit). Leaves set severities alone."""
    if finding.severity is not None:
        return
    proposal = propose(finding.category, finding.confidence, requirements)
    finding.severity = proposal.severity
    finding.severity_proposed = proposal.severity.value
    finding.severity_source = "system"
    finding.severity_reason = proposal.reason


def override(
    db: Session, finding: Finding, actor: User, severity: Severity, reason: str
) -> Finding:
    """A reviewer sets the severity (commits; audited). The system's proposal is kept."""
    why = reason.strip()
    if not why:
        raise BadRequestError("Say why the severity changes", code="reason_required")
    if len(why) > MAX_REASON:
        raise BadRequestError(f"A reason is at most {MAX_REASON} characters", code="too_long")
    before = finding.severity
    if (
        finding.severity_proposed is None
        and before is not None
        and finding.severity_source != "reviewer"
    ):
        finding.severity_proposed = before.value  # first override: remember what was proposed
    finding.severity = severity
    finding.severity_source = "reviewer"
    finding.severity_reason = why
    finding.severity_set_by = actor.id
    finding.severity_set_at = datetime.now(UTC)
    project = db.get(Project, finding.project_id)
    if project is not None:
        db.add(
            AuditLog(
                workspace_id=project.workspace_id,
                actor_id=actor.id,
                finding_id=finding.id,
                action=AuditAction.SEVERITY_CHANGED,
                details={
                    "from": before.value if before else None,
                    "to": severity.value,
                    "proposed": finding.severity_proposed,
                },
            )
        )
    db.commit()
    return finding
