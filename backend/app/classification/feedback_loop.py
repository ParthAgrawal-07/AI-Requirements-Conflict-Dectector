"""The AI feedback report: what people told the tool it got wrong (Keval — US-15, FR-18,
NFR-22; US-45 suggestion outcomes).

One report per project, read from the review and feedback records people already leave:

* **Findings by category and pattern** — how many were confirmed and how many dismissed as false
  positives, per category and per *pattern*: the rule that fired for a rule check (``R-NUM-01``…),
  "AI" for the model, "Person" for a raised concern. Dismissals carry their reasons, grouped.
* **Surfaced for tuning** — a pattern dismissed at least ``projects.feedback_alert_threshold``
  times (default 5). It is a signal for the people who own prompts and rules (Keval, Heet);
  **nothing retrains itself** (US-45 "no self-learning claim").
* **Suggestion feedback** — the six structured outcomes of AI suggestions (accepted, accepted
  after editing, rejected for meaning / feasibility / missing context, deferred), per category,
  next to the dismissals so both kinds of AI feedback are read together.

Counts only and short reasons people wrote; never requirement text.
"""

import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import BadRequestError
from app.models import (
    AuditAction,
    AuditLog,
    Finding,
    FindingReview,
    FindingStatus,
    Project,
    Suggestion,
    SuggestionFeedback,
    User,
)
from app.models.suggestion import OUTCOMES

MAX_REASONS = 5
MAX_REASON_CHARS = 140
PATTERN_NAMES = {"ai": "AI", "person": "Person"}


@dataclass
class Pattern:
    pattern: str  # rule id, "AI" or "Person"
    source: str  # ai, rule, person
    confirmed: int = 0
    dismissed: int = 0
    reasons: list[tuple[str, int]] = field(default_factory=list)  # (reason, how often)
    surfaced: bool = False

    @property
    def false_positive_rate(self) -> float | None:
        decided = self.confirmed + self.dismissed
        return round(self.dismissed / decided, 3) if decided else None


@dataclass
class CategoryFeedback:
    category: str
    open: int = 0
    confirmed: int = 0
    dismissed: int = 0
    patterns: list[Pattern] = field(default_factory=list)
    suggestions: dict[str, int] = field(default_factory=dict)  # outcome → count


@dataclass
class Report:
    project_id: uuid.UUID
    threshold: int
    categories: list[CategoryFeedback]
    surfaced: list[tuple[str, Pattern]]  # (category, pattern) at or over the threshold
    suggestion_totals: dict[str, int]
    self_training: bool = False  # stated, so nobody reads the report as a learning loop


def _reason(text: str | None) -> str:
    clean = " ".join((text or "").split())
    if not clean:
        return "(no reason given)"
    return clean[:MAX_REASON_CHARS] + ("…" if len(clean) > MAX_REASON_CHARS else "")


def report(db: Session, project: Project) -> Report:
    threshold = project.feedback_alert_threshold
    findings = db.execute(
        select(Finding.id, Finding.category, Finding.source, Finding.rule_id, Finding.status).where(
            Finding.project_id == project.id, ~Finding.is_stale
        )
    ).all()
    by_category: dict[str, CategoryFeedback] = {}
    patterns: dict[tuple[str, str], Pattern] = {}
    finding_key: dict[uuid.UUID, tuple[str, str]] = {}
    dismissed_ids: list[uuid.UUID] = []
    for finding_id, category, source, rule_id, status in findings:
        cat = by_category.setdefault(category.value, CategoryFeedback(category.value))
        name = rule_id if source == "rule" and rule_id else PATTERN_NAMES.get(source, source)
        key = (category.value, name)
        pattern = patterns.setdefault(key, Pattern(name, source))
        finding_key[finding_id] = key
        if status is FindingStatus.DISMISSED:
            cat.dismissed += 1
            pattern.dismissed += 1
            dismissed_ids.append(finding_id)
        elif status is FindingStatus.CONFIRMED:
            cat.confirmed += 1
            pattern.confirmed += 1
        elif status in (FindingStatus.FLAGGED, FindingStatus.RECLASSIFIED):
            cat.open += 1

    # The latest dismissal reason of each dismissed finding, grouped per pattern.
    reasons: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    if dismissed_ids:
        latest = (
            select(FindingReview.finding_id, FindingReview.reason)
            .where(FindingReview.finding_id.in_(dismissed_ids), FindingReview.action == "dismiss")
            .order_by(FindingReview.finding_id, FindingReview.created_at.desc())
            .distinct(FindingReview.finding_id)
        )
        for finding_id, text in db.execute(latest):
            reasons[finding_key[finding_id]][_reason(text)] += 1
    for key, pattern in patterns.items():
        pattern.reasons = reasons[key].most_common(MAX_REASONS)
        pattern.surfaced = pattern.dismissed >= threshold

    suggestion_totals = dict.fromkeys(OUTCOMES, 0)
    rows = db.execute(
        select(Suggestion.category, SuggestionFeedback.action, func.count())
        .join(SuggestionFeedback, SuggestionFeedback.suggestion_id == Suggestion.id)
        .where(Suggestion.project_id == project.id, SuggestionFeedback.action.in_(OUTCOMES))
        .group_by(Suggestion.category, SuggestionFeedback.action)
    )
    for suggestion_category, action, count in rows:
        cat = by_category.setdefault(suggestion_category, CategoryFeedback(suggestion_category))
        cat.suggestions[action] = int(count)
        suggestion_totals[action] += int(count)

    for (category_name, _), pattern in sorted(patterns.items()):
        by_category[category_name].patterns.append(pattern)
    for cat in by_category.values():
        cat.patterns.sort(key=lambda p: (-p.dismissed, p.pattern))
    surfaced = sorted(
        ((category, p) for (category, _), p in patterns.items() if p.surfaced),
        key=lambda item: (-item[1].dismissed, item[0], item[1].pattern),
    )
    return Report(
        project_id=project.id,
        threshold=threshold,
        categories=sorted(by_category.values(), key=lambda c: c.category),
        surfaced=surfaced,
        suggestion_totals=suggestion_totals,
    )


def set_threshold(db: Session, project: Project, actor: User, threshold: int) -> Project:
    if not 1 <= threshold <= 100:
        raise BadRequestError("The threshold is between 1 and 100", code="invalid_threshold")
    before = project.feedback_alert_threshold
    project.feedback_alert_threshold = threshold
    db.add(
        AuditLog(
            workspace_id=project.workspace_id,
            actor_id=actor.id,
            action=AuditAction.FEEDBACK_THRESHOLD_CHANGED,
            details={"project_id": str(project.id), "from": before, "to": threshold},
        )
    )
    db.commit()
    return project
