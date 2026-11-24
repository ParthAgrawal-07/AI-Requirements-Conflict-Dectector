"""The map's Preview layer for a change request (Dhavni — US-50, FR-85, SX-17).

What would merging this change request do to the map? Read from its latest consequence report
(US-34), never by running an analysis (SX-16):

* the changed requirement is the **proposed** node (dashed); a deprecation fades it out;
* edges of findings the report lists as **resolved** fade;
* findings the report lists as **new** — issues that appear only with the proposed text — glow
  as ghost edges between the requirements they would join;
* requirements the report lists as affected are outlined.

When the checks have not run yet, or ran on an older proposal, the preview says so
(``checks_pending`` / ``stale``) instead of showing an outdated picture as current. A pre-flight
draft (US-51) is previewed in the client from the pre-flight answer itself, which already names
the requirements a draft would conflict with.
"""

import uuid
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.consequences.tasks import latest_report, stale_reasons
from app.graph.schemas import EdgeKind
from app.graph.service import KIND
from app.models import ChangeRequest, FindingCategory, Project, Requirement

_NOUN = {
    "conflict": ("conflict", "conflicts"),
    "duplicate": ("possible duplicate", "possible duplicates"),
    "depends_on": ("dependency", "dependencies"),
    "ambiguous": ("ambiguity", "ambiguities"),
    "incomplete": ("missing-information finding", "missing-information findings"),
    "link": ("link", "links"),
}


@dataclass(frozen=True)
class GhostEdge:
    source: uuid.UUID
    target: uuid.UUID  # == source for a single-requirement finding
    kind: EdgeKind
    labels: list[str]
    reason: str


@dataclass
class Preview:
    change_request_id: uuid.UUID
    number: int
    kind: str  # "modify" or "deprecate"
    requirement_id: uuid.UUID
    report_id: uuid.UUID | None = None
    checks_pending: bool = True
    stale: list[str] = field(default_factory=list)
    fading_edge_ids: list[uuid.UUID] = field(default_factory=list)
    glowing_edges: list[GhostEdge] = field(default_factory=list)
    affected_node_ids: list[uuid.UUID] = field(default_factory=list)
    removed_node_ids: list[uuid.UUID] = field(default_factory=list)
    sentences: list[str] = field(default_factory=list)


def _kind(category: str) -> EdgeKind | None:
    try:
        return KIND[FindingCategory(category)]
    except ValueError:
        return None


def _count(n: int, kind: EdgeKind) -> str:
    one, many = _NOUN[kind]
    return f"{n} {one if n == 1 else many}"


def for_change_request(db: Session, change_request: ChangeRequest) -> Preview:
    preview = Preview(
        change_request_id=change_request.id,
        number=change_request.number,
        kind=change_request.kind,
        requirement_id=change_request.requirement_id,
    )
    if change_request.kind == "deprecate":
        preview.removed_node_ids.append(change_request.requirement_id)
    report = latest_report(db, change_request.id)
    requirement = db.get(Requirement, change_request.requirement_id)
    project = db.get(Project, change_request.project_id)
    key = f"RCR-{change_request.number}"
    if report is None or report.status != "done" or requirement is None or project is None:
        preview.sentences.append(f"The checks of {key} have not finished: no preview yet.")
        return preview
    preview.report_id = report.id
    preview.checks_pending = False
    preview.stale = stale_reasons(report, change_request, requirement, project)
    delta = report.findings_delta or {}
    resolved: dict[EdgeKind, int] = {}
    for entry in delta.get("resolved", []):
        if entry.get("finding_id"):
            preview.fading_edge_ids.append(uuid.UUID(entry["finding_id"]))
        kind = _kind(entry.get("category", ""))
        if kind is not None:
            resolved[kind] = resolved.get(kind, 0) + 1
    added: dict[EdgeKind, int] = {}
    for entry in delta.get("new", []):
        kind = _kind(entry.get("category", ""))
        ids = [uuid.UUID(i) for i in entry.get("requirement_ids", [])]
        if kind is None or not ids:
            continue
        preview.glowing_edges.append(
            GhostEdge(
                source=ids[0],
                target=ids[-1],
                kind=kind,
                labels=list(entry.get("labels", [])),
                reason=str(entry.get("reason", "")),
            )
        )
        added[kind] = added.get(kind, 0) + 1
    preview.affected_node_ids = [
        uuid.UUID(a["requirement_id"]) for a in report.affected or [] if a.get("requirement_id")
    ]
    parts = [f"resolve {_count(n, k)}" for k, n in resolved.items()]
    parts += [f"add {_count(n, k)}" for k, n in added.items()]
    if parts:
        joined = ", ".join(parts[:-1]) + (" and " if len(parts) > 1 else "") + parts[-1]
        preview.sentences.append(f"Merging {key} would {joined}.")
    else:
        preview.sentences.append(f"Merging {key} would not change any finding on the map.")
    if preview.stale:
        preview.sentences.append(f"The checks are out of date: {'; '.join(preview.stale)}.")
    return preview
