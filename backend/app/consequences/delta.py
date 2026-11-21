"""The findings delta of a change request (Madhav — US-34, FR-99; design update §11.4).

What would merging do to the findings? Built from the open findings and the probe
(``app.consequences.checks.probe``):

* **resolved** — an open finding on the changed requirement whose condition no longer holds with
  the proposed text (the probe found a different category, or no issue); every open finding on a
  requirement being **deprecated**;
* **new** — an issue the probe found that no open finding records yet;
* **still open** — open findings on the changed requirement that the probe found again, open
  findings of directly affected requirements that the change does not touch, and every finding a
  **person** raised (only its decision owner closes it, US-57);
* **must re-run** — open findings the probe could not re-check (no model, budget, a failed
  reply), and requirements two steps away, whose relation to the new text nobody re-analysed.

Each entry: ``finding_id`` (None for *new* and two-step entries), ``category``, ``labels``,
``requirement_ids``, ``source`` and a ``reason`` naming requirements by ID only.
"""

import uuid
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.consequences.checks import Probe
from app.consequences.impact import Impact, label
from app.models import CandidatePair, Finding, Requirement
from app.search.relations import LIVE_STATUSES

Entry = dict[str, Any]


def open_findings(
    db: Session, requirement_ids: list[uuid.UUID]
) -> list[tuple[Finding, list[uuid.UUID]]]:
    """Live findings about any of ``requirement_ids``, each with the requirements it is about."""
    if not requirement_ids:
        return []
    rows = db.execute(
        select(Finding, CandidatePair)
        .outerjoin(CandidatePair, CandidatePair.id == Finding.candidate_pair_id)
        .where(
            ~Finding.is_stale,
            Finding.status.in_(LIVE_STATUSES),
            or_(
                Finding.requirement_id.in_(requirement_ids),
                CandidatePair.requirement_a_id.in_(requirement_ids),
                CandidatePair.requirement_b_id.in_(requirement_ids),
            ),
        )
        .order_by(Finding.created_at, Finding.id)
    )
    result = []
    for finding, pair in rows:
        ids = (
            [pair.requirement_a_id, pair.requirement_b_id]
            if pair is not None
            else [finding.requirement_id]
            if finding.requirement_id
            else []
        )
        result.append((finding, ids))
    return result


def open_partners(db: Session, requirement: Requirement) -> dict[str, set[uuid.UUID]]:
    """Category → requirements with an open finding of that category with ``requirement``."""
    partners: dict[str, set[uuid.UUID]] = {}
    for finding, ids in open_findings(db, [requirement.id]):
        for other in ids:
            if other != requirement.id:
                partners.setdefault(finding.category.value, set()).add(other)
    return partners


def _entry(
    finding: Finding | None,
    category: str,
    ids: list[uuid.UUID],
    labels: dict[uuid.UUID, str],
    reason: str,
    source: str = "ai",
) -> Entry:
    return {
        "finding_id": str(finding.id) if finding else None,
        "category": category,
        "requirement_ids": [str(i) for i in ids],
        "labels": [labels.get(i, "?") for i in ids],
        "source": finding.source if finding else source,
        "reason": reason,
    }


def _labels(db: Session, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    return {r.id: label(r) for r in db.scalars(select(Requirement).where(Requirement.id.in_(ids)))}


def build_delta(
    db: Session, requirement: Requirement, kind: str, impact: Impact, probe: Probe
) -> dict[str, list[Entry]]:
    delta: dict[str, list[Entry]] = {"resolved": [], "new": [], "still_open": [], "must_rerun": []}
    source = label(requirement)
    direct = [a.requirement_id for a in impact.direct]
    findings = open_findings(db, [requirement.id, *direct])
    labels = _labels(
        db,
        {
            requirement.id,
            *direct,
            *(i for _, ids in findings for i in ids),
            *(a.requirement_id for a in impact.affected),
        },
    )
    labels[requirement.id] = source

    seen: dict[str, set[uuid.UUID]] = {}
    for finding, ids in findings:
        category = finding.category.value
        if requirement.id not in ids:
            delta["still_open"].append(
                _entry(
                    finding,
                    category,
                    ids,
                    labels,
                    f"On {', '.join(labels.get(i, '?') for i in ids)}; this change does not touch it",
                )
            )
            continue
        partner = next((i for i in ids if i != requirement.id), None)
        seen.setdefault(category, set()).add(partner or requirement.id)
        if kind == "deprecate":
            delta["resolved"].append(
                _entry(finding, category, ids, labels, f"{source} leaves the baseline")
            )
            continue
        if finding.source == "person":
            delta["still_open"].append(
                _entry(
                    finding,
                    category,
                    ids,
                    labels,
                    "Raised by a person: only its decision owner closes it",
                )
            )
            continue
        outcome = probe.outcome_for(partner) if partner else probe.single
        if outcome is None or outcome.state != "done":
            delta["must_rerun"].append(
                _entry(finding, category, ids, labels, "Not re-checked against the new text")
            )
        elif outcome.category == category:
            delta["still_open"].append(
                _entry(finding, category, ids, labels, "Still holds with the new text")
            )
        else:
            delta["resolved"].append(
                _entry(finding, category, ids, labels, "No longer holds with the new text")
            )

    for outcome in probe.pairs:
        if (
            outcome.state == "done"
            and outcome.category
            and outcome.requirement_id not in seen.get(outcome.category, set())
        ):
            ids = (
                [requirement.id, outcome.requirement_id]
                if outcome.requirement_id
                else [requirement.id]
            )
            delta["new"].append(
                _entry(
                    None,
                    outcome.category,
                    ids,
                    labels,
                    f"Found by checking the new text against {outcome.label}",
                )
            )
    single = probe.single
    if (
        single is not None
        and single.state == "done"
        and single.category
        and requirement.id not in seen.get(single.category, set())
    ):
        delta["new"].append(
            _entry(
                None,
                single.category,
                [requirement.id],
                labels,
                "Found by checking the new text on its own",
            )
        )

    for affected in impact.affected:
        if affected.depth == 2:
            delta["must_rerun"].append(
                _entry(
                    None,
                    affected.relation.value,
                    [requirement.id, affected.requirement_id],
                    labels,
                    f"Two steps away through {affected.path[1]}: re-run before approving",
                    source="ai",
                )
            )
    return delta
