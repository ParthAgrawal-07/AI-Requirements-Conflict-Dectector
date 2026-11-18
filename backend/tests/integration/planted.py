"""The planted SRS as a database fixture (Abhyudit — Sprint 4 integration tests).

Loads ``eval/benchmark_v2``: every requirement of ``srs_planted.md`` (Approved, with its printed
ID), one finding per issue label of ``labels.csv`` (pairs as candidate pairs, Dependent read as
"r1 depends on r2"; Conflicting and Duplicate at Medium severity), and the owners and protected
requirements of ``change_requests.json``. No embeddings: the relations are the labelled ones.
"""

import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.models import (
    CandidatePair,
    Finding,
    FindingCategory,
    Project,
    Requirement,
    RequirementOrigin,
    RequirementState,
    RequirementVersion,
    Severity,
    User,
)

BENCHMARK = Path(__file__).resolve().parents[3] / "eval" / "benchmark_v2"
_LINE = re.compile(r"^(?:\| )?(REQ-\d{3})(?::| \|) (.+?)(?: \|)?$")


def statements() -> dict[str, str]:
    found: dict[str, str] = {}
    for line in (BENCHMARK / "srs_planted.md").read_text(encoding="utf-8").splitlines():
        match = _LINE.match(line.strip())
        if match:
            found[match.group(1)] = match.group(2).strip()
    return found


def labels() -> list[dict[str, str]]:
    with (BENCHMARK / "labels.csv").open(encoding="utf-8", newline="") as handle:
        return [row for row in csv.DictReader(handle) if row["category"] != "None"]


def scripted() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(
        (BENCHMARK / "change_requests.json").read_text(encoding="utf-8")
    )
    return data


@dataclass
class Planted:
    project: Project
    by_label: dict[str, Requirement]
    owners: dict[str, User]  # by name
    findings: dict[frozenset[str], Finding] = field(default_factory=dict)  # by label pair / single

    def label_of(self, requirement_id: object) -> str:
        return next(label for label, r in self.by_label.items() if r.id == requirement_id)

    def category_between(self, a: str, b: str) -> str | None:
        finding = self.findings.get(frozenset((a, b)))
        return finding.category.value if finding else None


def load(db: Session, project: Project, owners: dict[str, User]) -> Planted:
    data = scripted()
    owner_of = {label: owners[name] for name, items in data["owners"].items() for label in items}
    protected = set(data["protected"])
    by_label: dict[str, Requirement] = {}
    for order, (label, body) in enumerate(sorted(statements().items())):
        owner = owner_of.get(label)
        requirement = Requirement(
            project_id=project.id,
            origin=RequirementOrigin.POST,
            body=body,
            source_req_id=label,
            order_index=order,
            state=RequirementState.APPROVED,
            owner_id=owner.id if owner else None,
            is_protected=label in protected,
        )
        db.add(requirement)
        by_label[label] = requirement
    db.flush()
    db.add_all(
        RequirementVersion(requirement_id=r.id, version_no=1, body_snapshot=r.body)
        for r in by_label.values()
    )
    planted = Planted(project, by_label, owners)
    for row in labels():
        category = FindingCategory(row["category"])
        severity = (
            Severity.MEDIUM
            if category in (FindingCategory.CONFLICTING, FindingCategory.DUPLICATE)
            else None
        )
        r1 = by_label[row["r1"]]
        if not row["r2"]:
            finding = Finding(
                project_id=project.id, requirement_id=r1.id, category=category, severity=severity,
                confidence=0.8, rationale=row["note"], original_ai_output={},
            )  # fmt: skip
            planted.findings[frozenset((row["r1"],))] = finding
            db.add(finding)
            continue
        r2 = by_label[row["r2"]]
        first, second = CandidatePair.ordered(r1.id, r2.id)
        pair = CandidatePair(requirement_a_id=first, requirement_b_id=second, similarity_score=0.8)
        db.add(pair)
        db.flush()
        direction = None
        if category is FindingCategory.DEPENDENT:
            direction = "A_depends_on_B" if first == r1.id else "B_depends_on_A"
        finding = Finding(
            project_id=project.id, candidate_pair_id=pair.id, category=category, severity=severity,
            confidence=0.8, rationale=row["note"], original_ai_output={"dependency_direction": direction},
        )  # fmt: skip
        planted.findings[frozenset((row["r1"], row["r2"]))] = finding
        db.add(finding)
    db.commit()
    return planted
