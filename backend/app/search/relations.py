"""Relationship queries (Heet — US-11, FR-24, FR-25; design update §3.2, §11.4).

What is a requirement related to? The impact analysis (Madhav, ``app.consequences.impact``)
asks this for the requirement a change request touches; the findings delta asks it for the
requirements it must re-check. Three sources, strongest first:

* **findings** — a live (not stale, not dismissed or merged) Conflicting, Duplicate or Dependent
  finding links the two requirements of its pair. Dependent keeps its direction
  (``depends_on``: this requirement needs the other; ``required_by``: the other needs this one);
* **human links** — ``requirement_links`` arrive with US-53 (Sprint 5, migration 0008); until
  then there are none, and :func:`related` is the only place that will need to read them;
* **shared embeddings** — the nearest neighbours of the requirement's vector above the project's
  similarity threshold that no finding links yet (``similar``): a pointer, never a verdict
  (DR-10), so the impact report marks them *potential*.

:func:`related` walks **one hop** from the source over all three, then a **second hop** over
findings only — a neighbour's neighbours by embedding would be most of a large project and say
nothing about the change. Each requirement appears once, at its smallest depth and with its
strongest relation, with the path it was reached by. Rejected and Deprecated requirements are
never related: they are out of the baseline and are not analysed again.
"""

import uuid
from dataclasses import dataclass, field
from enum import StrEnum

from app.models import FindingCategory, FindingStatus

# A finding still says something about its requirements in these states (US-10).
LIVE_STATUSES = (FindingStatus.FLAGGED, FindingStatus.CONFIRMED, FindingStatus.RECLASSIFIED)
SIMILAR_K = 5


class RelationKind(StrEnum):
    CONFLICT = "conflict"
    DUPLICATE = "duplicate"
    DEPENDS_ON = "depends_on"  # the source needs the related requirement
    REQUIRED_BY = "required_by"  # the related requirement needs the source
    DEPENDENCY = "dependency"  # Dependent without a direction
    SIMILAR = "similar"  # shared embedding only


# Strongest first: when two relations reach the same requirement at the same depth, this wins.
STRENGTH = {
    RelationKind.CONFLICT: 0,
    RelationKind.DUPLICATE: 1,
    RelationKind.DEPENDS_ON: 2,
    RelationKind.REQUIRED_BY: 2,
    RelationKind.DEPENDENCY: 2,
    RelationKind.SIMILAR: 3,
}
_PAIR_KINDS = {
    FindingCategory.CONFLICTING: RelationKind.CONFLICT,
    FindingCategory.DUPLICATE: RelationKind.DUPLICATE,
    FindingCategory.DEPENDENT: RelationKind.DEPENDENCY,
}


@dataclass(frozen=True)
class Edge:
    """One finding between two requirements, seen from ``source``."""

    source: uuid.UUID
    target: uuid.UUID
    kind: RelationKind
    finding_id: uuid.UUID
    severity: str | None


@dataclass
class Related:
    requirement_id: uuid.UUID
    label: str | None  # printed ID, e.g. "REQ-014"
    depth: int  # 1 = direct, 2 = through one other requirement
    kind: RelationKind
    path: list[uuid.UUID]  # from the source to this requirement, both ends included
    finding_id: uuid.UUID | None = None  # the finding of the last hop; None for ``similar``
    similarity: float | None = None  # for ``similar``
    severity: str | None = None
    owner_id: uuid.UUID | None = None
    is_protected: bool = False
    via: list[RelationKind] = field(default_factory=list)  # the kind of every hop on the path


def _directed(kind: RelationKind, source_is_a: bool, direction: object) -> RelationKind:
    if kind is not RelationKind.DEPENDENCY or direction not in ("A_depends_on_B", "B_depends_on_A"):
        return kind
    source_depends = (direction == "A_depends_on_B") == source_is_a
    return RelationKind.DEPENDS_ON if source_depends else RelationKind.REQUIRED_BY
