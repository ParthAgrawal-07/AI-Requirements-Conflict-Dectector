"""The result card of a posted requirement's live analysis (Keval — US-31, FR-57, NFR-25, DR-21).

When a run for a posted requirement closes — or parks for budget — ``analysis.after_run`` calls
:func:`publish_card`, which posts an ``analysis_card`` **reply in the requirement's thread**:

* one line per finding: category, the other requirement's ID, severity, confidence and the
  rationale, plus its clarification question once one exists (US-09);
* the owners of every requirement involved, @mentioned so they are notified (US-36);
* "waiting for budget" when the project's monthly LLM budget is used up — the same card is
  rewritten with the results when the run resumes and finishes;
* a readable reason when the analysis could not finish (no model configured, failed comparisons);
* a clean result says **"No issues detected by analysis — analysis can miss conflicts"**, never
  "verified" or "conflict-free" (DR-21), and points to raising a concern.

There is one card per run: publishing again (a resumed run, a new clarification) rewrites it and
announces ``message.updated``. The card is a system message (no author); ``payload`` carries the
run and requirement ids, and the UI reads the details from ``GET /analysis-runs/{id}``.
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AnalysisRun,
    AnalysisRunStatus,
    AnalysisScope,
    CandidatePair,
    Channel,
    Clarification,
    Finding,
    Message,
    MessageKind,
    Requirement,
    Severity,
)

try:
    from app.graph.deltas import label_of
except ImportError:

    def label_of(requirement: Requirement | None) -> str:
        """How sentences name a requirement: its printed ID, or a short stable stand-in."""
        if requirement is None:
            return ""
        return requirement.source_req_id or f"requirement {str(requirement.id)[:8]}"
from app.models.channel import MAX_MESSAGE_CHARS
from app.services import messages as message_service

CLEAN = "No issues detected by analysis — analysis can miss conflicts."
CONCERN_HINT = "If you see a problem the analysis missed, raise a concern."
WAITING = (
    "Waiting for budget: this project's monthly analysis budget is used up. The analysis "
    "resumes automatically when budget is available."
)
RATIONALE_CHARS = 280
QUESTION_CHARS = 300
_SEVERITY_ORDER = {Severity.HIGH: 0, Severity.MEDIUM: 1, Severity.LOW: 2, None: 3}
_RELATION = {
    "Conflicting": "Conflicting with",
    "Duplicate": "Possible duplicate of",
    "Dependent": "Depends on / is depended on by",
}


def publish_card(db: Session, run: AnalysisRun) -> Message | None:
    """Post or rewrite the card of a requirement run. ``None`` when there is nowhere to post it
    (a document run, or a requirement that did not come from a post)."""
    if run.scope is not AnalysisScope.REQUIREMENT:
        return None
    requirement = db.get(Requirement, run.subject_id)
    if requirement is None or requirement.origin_message_id is None:
        return None
    root = db.get(Message, requirement.origin_message_id)
    channel = db.get(Channel, root.channel_id) if root is not None else None
    if root is None or channel is None:
        return None

    findings = _findings(db, run)
    body = render(db, run, requirement, findings)
    payload: dict[str, Any] = {
        "run_id": str(run.id),
        "requirement_id": str(requirement.id),
        "label": requirement.source_req_id,
        "status": run.status.value,
        "finding_ids": [str(f.id) for f in findings],
    }
    existing = db.scalar(
        select(Message).where(
            Message.parent_id == root.id,
            Message.kind == MessageKind.ANALYSIS_CARD,
            Message.payload["run_id"].astext == str(run.id),
        )
    )
    if existing is not None:
        if existing.body == body and existing.payload == payload:
            return existing
        return message_service.update_system_message(
            db, message=existing, body=body, payload=payload
        )
    return message_service.post_system_message(
        db,
        channel=channel,
        body=body,
        kind=MessageKind.ANALYSIS_CARD,
        parent_id=root.id,
        payload=payload,
    )


def render(db: Session, run: AnalysisRun, requirement: Requirement, findings: list[Finding]) -> str:
    """The card as plain text: what every client shows, and what a notification quotes."""
    label = label_of(requirement)
    seconds = (
        round((run.finished_at - run.created_at).total_seconds())
        if run.finished_at and run.created_at
        else None
    )
    header = f"Analysis of {label}" + (f" ({seconds} s)" if seconds is not None else "")
    if run.status is AnalysisRunStatus.WAITING_BUDGET:
        return f"{header}: {WAITING}"

    head = [header + ":"]
    if run.error_message:
        head.append(f"Analysis could not finish: {run.error_message}")
    tail: list[str] = []
    failed = run.pairs_failed + run.checks_failed
    if failed:
        noun = "comparison" if failed == 1 else "comparisons"
        tail.append(
            f"{failed} {noun} could not be completed; they are retried when the analysis runs again."
        )
    if not findings and not run.error_message:
        tail.append(f"{CLEAN} {CONCERN_HINT}")
    owners = _owners(db, requirement, findings)
    if findings and owners:
        tail.append("Owners: " + " ".join(f"<@{owner}>" for owner in owners))

    others = _other_requirements(db, requirement, findings)
    questions = _questions(db, findings)
    # Whole findings only, most severe first, so the owners' mentions at the end always fit.
    budget = MAX_MESSAGE_CHARS - len("\n".join(head + tail)) - 60
    body: list[str] = []
    for shown, finding in enumerate(findings):
        block = [_line(finding, others.get(finding.id))]
        if finding.id in questions:
            block.append(f"  Clarification: {_short(questions[finding.id], QUESTION_CHARS)}")
        size = sum(len(line) + 1 for line in block)
        if size > budget:
            body.append(f"…and {len(findings) - shown} more — open the analysis to see them all.")
            break
        body.extend(block)
        budget -= size
    return "\n".join(head + body + tail)


def _findings(db: Session, run: AnalysisRun) -> list[Finding]:
    findings = list(
        db.scalars(
            select(Finding).where(Finding.analysis_run_id == run.id, Finding.is_stale.is_(False))
        )
    )
    return sorted(
        findings, key=lambda f: (_SEVERITY_ORDER.get(f.severity, 3), -f.confidence, f.created_at)
    )


def _line(finding: Finding, other: Requirement | None) -> str:
    category = finding.category.value
    subject = f"{_RELATION.get(category, category)} {label_of(other)}" if other else category
    severity = f" · {finding.severity.value}" if finding.severity else ""
    rationale = _short(finding.explanation or finding.rationale, RATIONALE_CHARS)
    return f"• {subject}{severity} · {round(finding.confidence * 100)}% confidence — {rationale}"


def _other_requirements(
    db: Session, requirement: Requirement, findings: list[Finding]
) -> dict[uuid.UUID, Requirement]:
    pair_ids = [f.candidate_pair_id for f in findings if f.candidate_pair_id]
    if not pair_ids:
        return {}
    pairs = {
        p.id: p for p in db.scalars(select(CandidatePair).where(CandidatePair.id.in_(pair_ids)))
    }
    result: dict[uuid.UUID, Requirement] = {}
    for finding in findings:
        pair = pairs.get(finding.candidate_pair_id) if finding.candidate_pair_id else None
        if pair is None:
            continue
        other_id = (
            pair.requirement_b_id
            if pair.requirement_a_id == requirement.id
            else pair.requirement_a_id
        )
        other = db.get(Requirement, other_id)
        if other is not None:
            result[finding.id] = other
    return result


def _questions(db: Session, findings: list[Finding]) -> dict[uuid.UUID, str]:
    if not findings:
        return {}
    return {
        c.finding_id: c.question
        for c in db.scalars(
            select(Clarification).where(Clarification.finding_id.in_([f.id for f in findings]))
        )
    }


def _owners(db: Session, requirement: Requirement, findings: list[Finding]) -> list[uuid.UUID]:
    """The posted requirement's owner first, then the owners of the others, each once."""
    owners: list[uuid.UUID] = []
    candidates = [requirement, *_other_requirements(db, requirement, findings).values()]
    for item in candidates:
        if item.owner_id is not None and item.owner_id not in owners:
            owners.append(item.owner_id)
    return owners


def _short(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"
