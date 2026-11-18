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

from app.models import Requirement
from app.search.relations import RelationKind

_REASONS: dict[RelationKind, str] = {
    RelationKind.CONFLICT: "{other} conflicts with {source} today; the new text may resolve or change that",
    RelationKind.DUPLICATE: "{other} may duplicate {source}; both should still say the same",
    RelationKind.DEPENDS_ON: "{source} depends on {other}",
    RelationKind.REQUIRED_BY: "{other} depends on {source}: it relies on what changes",
    RelationKind.DEPENDENCY: "{other} and {source} depend on each other",
    RelationKind.SIMILAR: "{other} is worded much like {source} ({similarity:.0%} similar) and may say the same thing",
}


# A second hop, read from the requirement in between.
_VERBS: dict[RelationKind, str] = {
    RelationKind.CONFLICT: "conflicts with",
    RelationKind.DUPLICATE: "may duplicate",
    RelationKind.DEPENDS_ON: "depends on",
    RelationKind.REQUIRED_BY: "is needed by",
    RelationKind.DEPENDENCY: "has a dependency with",
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
