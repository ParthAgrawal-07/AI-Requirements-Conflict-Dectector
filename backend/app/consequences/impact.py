"""Impact analysis (Madhav — US-11, FR-24, FR-25, NFR-15; design update §3.2).

``ImpactAnalyzer.analyse(requirement, kind)`` answers *who and what does this change touch?*
for a change request, before anyone decides:

* **affected requirements** — Heet's relationship queries (``app.search.relations``): one hop
  over findings and shared embeddings, a second hop over findings, each with a plain-language
  **reason** that names requirements by ID only, and whether the link is **confirmed** (a finding
  a person confirmed) or **potential** (unreviewed, or similarity only — NFR-17);
* **owners and stakeholder groups** of the changed requirement and of everything affected:
  who the review requests and notifications reach (US-35, US-38);
* **work items** — linked work items arrive with US-48, which is deferred (revision 5): the
  list is always empty for now, and the report says so.

Pure reads: nothing is stored here; ``app.consequences.tasks`` stores the report.
"""

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Finding, FindingStatus, Requirement
from app.search.relations import Related, RelationKind, related

_REASONS: dict[RelationKind, str] = {
    RelationKind.CONFLICT: "{other} conflicts with {source} today; the new text may resolve or change that",
    RelationKind.DUPLICATE: "{other} may duplicate {source}; both should still say the same",
    RelationKind.DEPENDS_ON: "{source} depends on {other}",
    RelationKind.REQUIRED_BY: "{other} depends on {source}: it relies on what changes",
    RelationKind.DEPENDENCY: "{other} and {source} depend on each other",
    RelationKind.REFINES: "{source} refines {other} (a link a person made)",
    RelationKind.REFINED_BY: "{other} refines {source} (a link a person made)",
    RelationKind.RELATED: "{other} is related to {source} (a link a person made)",
    RelationKind.SIMILAR: "{other} is worded much like {source} ({similarity:.0%} similar) and may say the same thing",
}


# A second hop, read from the requirement in between.
_VERBS: dict[RelationKind, str] = {
    RelationKind.CONFLICT: "conflicts with",
    RelationKind.DUPLICATE: "may duplicate",
    RelationKind.DEPENDS_ON: "depends on",
    RelationKind.REQUIRED_BY: "is needed by",
    RelationKind.DEPENDENCY: "has a dependency with",
    RelationKind.REFINES: "refines",
    RelationKind.REFINED_BY: "is refined by",
    RelationKind.RELATED: "is related to",
    RelationKind.SIMILAR: "is similar to",
}


@dataclass
class Affected:
    requirement_id: uuid.UUID
    label: str
    depth: int
    relation: RelationKind
    reason: str
    status: str  # "confirmed" or "potential"
    owner_id: uuid.UUID | None
    stakeholder_group: str | None
    is_protected: bool
    finding_id: uuid.UUID | None
    path: list[str]  # labels from the changed requirement to this one

    def as_json(self) -> dict[str, object]:
        return {
            "requirement_id": str(self.requirement_id),
            "label": self.label,
            "depth": self.depth,
            "relation": self.relation.value,
            "reason": self.reason,
            "status": self.status,
            "owner_id": str(self.owner_id) if self.owner_id else None,
            "stakeholder_group": self.stakeholder_group,
            "is_protected": self.is_protected,
            "finding_id": str(self.finding_id) if self.finding_id else None,
            "path": self.path,
        }


@dataclass
class Impact:
    requirement: Requirement
    affected: list[Affected]
    owners: list[uuid.UUID]  # the changed requirement's owner first, then the affected ones
    stakeholder_groups: list[str]
    work_items: list[dict[str, object]] = field(default_factory=list)  # US-48, deferred

    @property
    def direct(self) -> list[Affected]:
        return [a for a in self.affected if a.depth == 1]


def label(requirement: Requirement) -> str:
    return requirement.source_req_id or f"item-{str(requirement.id)[:8]}"


class ImpactAnalyzer:
    def __init__(self, db: Session) -> None:
        self.db = db

    def analyse(self, requirement: Requirement, *, kind: str = "modify") -> Impact:
        db = self.db
        relations = related(db, requirement.id)
        rows = {
            r.id: r
            for r in db.scalars(
                select(Requirement).where(
                    Requirement.id.in_({x for rel in relations for x in rel.path})
                )
            )
        }
        confirmed = self._confirmed({r.finding_id for r in relations if r.finding_id})
        source = label(requirement)
        affected = [
            self._affected(rel, rows, source, confirmed, kind)
            for rel in relations
            if rel.requirement_id in rows
        ]
        owners: list[uuid.UUID] = []
        for owner in [requirement.owner_id, *(a.owner_id for a in affected)]:
            if owner is not None and owner not in owners:
                owners.append(owner)
        groups = sorted(
            {
                g
                for g in [requirement.stakeholder_group, *(a.stakeholder_group for a in affected)]
                if g
            }
        )
        return Impact(requirement, affected, owners, groups)

    def _confirmed(self, finding_ids: set[uuid.UUID]) -> set[uuid.UUID]:
        if not finding_ids:
            return set()
        return set(
            self.db.scalars(
                select(Finding.id).where(
                    Finding.id.in_(finding_ids), Finding.status == FindingStatus.CONFIRMED
                )
            )
        )

    def _affected(
        self,
        rel: Related,
        rows: dict[uuid.UUID, Requirement],
        source: str,
        confirmed: set[uuid.UUID],
        kind: str,
    ) -> Affected:
        target = rows[rel.requirement_id]
        other = label(target)
        path = [label(rows[i]) if i in rows else "?" for i in rel.path]
        if rel.depth == 1:
            reason = _REASONS[rel.kind].format(
                other=other, source=source, similarity=rel.similarity or 0.0
            )
            if kind == "deprecate" and rel.kind is RelationKind.REQUIRED_BY:
                reason = f"{other} depends on {source}, which this request deprecates"
        else:
            reason = f"Two steps away: {path[1]} {_VERBS[rel.kind]} {other}"
        return Affected(
            requirement_id=target.id,
            label=other,
            depth=rel.depth,
            relation=rel.kind,
            reason=reason,
            # A person's link is a fact someone asserted (US-53); a finding only once confirmed.
            status="confirmed" if rel.link_id or rel.finding_id in confirmed else "potential",
            owner_id=target.owner_id,
            stakeholder_group=target.stakeholder_group,
            is_protected=target.is_protected,
            finding_id=rel.finding_id,
            path=path,
        )
