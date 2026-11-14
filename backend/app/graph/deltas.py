"""Graph deltas: the live map's updates (Dhavni — US-14, FR-84, NFR-32; design update §3.4, ADR-21).

Whoever changes what the map shows — a post, a finished analysis run, a review, a state change —
first **commits** the change and then calls :func:`publish` with a :class:`Change` naming what it
touched. ``publish``:

1. bumps ``projects.graph_revision`` in one atomic ``UPDATE … RETURNING`` (concurrent producers
   get distinct, consecutive revisions);
2. reads the touched nodes and edges back **from the database** and sorts them into
   ``added`` / ``changed`` / ``removed`` — an edge whose finding is now stale, dismissed or merged
   is *removed*, so producers never decide visibility themselves;
3. publishes ``graph.delta`` with the written sentences (``app.graph.narrator``).

A client applies a delta only when ``from_revision`` is the revision it holds, and re-fetches
``GET /projects/{p}/graph`` otherwise — so a lost or reordered event costs one reload, never a
wrong map. Nothing here triggers analysis (SX-16).

Batching: one *logical* change is one delta — a whole analysis run (every finding of a
500-requirement document) goes out as a single delta, and clients coalesce deltas that arrive
within 250 ms into one render (``useGraphDeltas``).

:func:`run_finished` is the delta for a closed analysis run, called from
``analysis_orchestrator.after_run``.
"""

import logging
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.graph import narrator, positions
from app.graph import service as graph_service
from app.graph.schemas import GraphChanges, GraphDelta, GraphRemovals
from app.models import (
    AnalysisRun,
    AnalysisScope,
    CandidatePair,
    Document,
    Embedding,
    Finding,
    Project,
    Requirement,
    RequirementVersion,
    User,
)
from app.realtime import bus
from app.realtime.events import graph_delta

logger = logging.getLogger(__name__)


@dataclass
class Change:
    """What one committed change touched, as its producer knows it."""

    new_requirements: set[uuid.UUID] = field(default_factory=set)
    requirements: set[uuid.UUID] = field(default_factory=set)  # state, owner, group, position
    new_findings: set[uuid.UUID] = field(default_factory=set)
    findings: set[uuid.UUID] = field(default_factory=set)  # reviewed or otherwise changed
    sentences: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(
            self.new_requirements
            or self.requirements
            or self.new_findings
            or self.findings
            or self.sentences
        )


def label_of(requirement: Requirement) -> str:
    """How sentences name a requirement: its printed ID, or a short stable stand-in."""
    return requirement.source_req_id or f"requirement {str(requirement.id)[:8]}"


def publish(
    db: Session, project_id: uuid.UUID, change: Change, *, actor: User | None = None
) -> GraphDelta | None:
    """Bump the revision and publish ``graph.delta``. Call **after** committing the change."""
    if not change:
        return None
    row = db.execute(
        update(Project)
        .where(Project.id == project_id)
        .values(graph_revision=Project.graph_revision + 1)
        .returning(Project.graph_revision, Project.workspace_id)
    ).first()
    db.commit()
    if row is None:
        return None
    revision, workspace_id = row

    node_ids = change.new_requirements | change.requirements
    nodes = graph_service.nodes(db, project_id, node_ids) if node_ids else []
    edge_ids = change.new_findings | change.findings
    visible = {e.id: e for e in graph_service.edges(db, project_id, edge_ids)} if edge_ids else {}
    added, changed, removed = GraphChanges(), GraphChanges(), GraphRemovals()
    for node in nodes:
        (added if node.id in change.new_requirements else changed).nodes.append(node)
    for edge_id in sorted(edge_ids):
        edge = visible.get(edge_id)
        if edge is None:  # stale, dismissed, merged or gone
            removed.edge_ids.append(edge_id)
        else:
            (added if edge_id in change.new_findings else changed).edges.append(edge)

    delta = GraphDelta(
        project_id=project_id,
        from_revision=revision - 1,
        to_revision=revision,
        actor_id=actor.id if actor else None,
        actor_name=actor.full_name if actor else None,
        added=added,
        changed=changed,
        removed=removed,
        sentences=change.sentences,
    )
    bus.publish(graph_delta(workspace_id=workspace_id, delta=delta))
    return delta


def author_of(db: Session, requirement: Requirement) -> User | None:
    """Who wrote the requirement: the person who saved its first version (a post's author)."""
    author_id = db.scalar(
        select(RequirementVersion.changed_by).where(
            RequirementVersion.requirement_id == requirement.id,
            RequirementVersion.version_no == 1,
        )
    )
    return db.get(User, author_id) if author_id else None


def run_finished(db: Session, run: AnalysisRun) -> GraphDelta | None:
    """The delta for a closed analysis run: its findings as new edges, its subject placed on the
    map, and one sentence saying what was found."""
    findings = list(
        db.scalars(
            select(Finding).where(Finding.analysis_run_id == run.id, Finding.is_stale.is_(False))
        )
    )
    if run.scope is AnalysisScope.REQUIREMENT:
        return _requirement_run_finished(db, run, findings)
    if run.scope is AnalysisScope.DOCUMENT:
        return _document_run_finished(db, run, findings)
    return None


def _requirement_run_finished(
    db: Session, run: AnalysisRun, findings: list[Finding]
) -> GraphDelta | None:
    subject = db.get(Requirement, run.subject_id)
    if subject is None:
        return None
    pairs = _pairs(db, findings)
    others: list[uuid.UUID] = []
    related: list[narrator.Related] = []
    labels = _labels(
        db, {r for p in pairs.values() for r in (p.requirement_a_id, p.requirement_b_id)}
    )
    for finding in findings:
        if not graph_service.on_the_map(finding):
            continue
        pair = pairs.get(finding.candidate_pair_id) if finding.candidate_pair_id else None
        edge = graph_service.edge_of(finding, pair)
        if edge is None:
            continue
        other = None
        if pair is not None:
            other_id = (
                pair.requirement_b_id
                if pair.requirement_a_id == subject.id
                else pair.requirement_a_id
            )
            others.append(other_id)
            other = labels.get(other_id)
        related.append(
            narrator.Related(
                kind=edge.kind,
                other=other,
                severity=finding.severity.value if finding.severity else None,
            )
        )
    neighbours = others or _nearest(db, subject)
    placed = positions.place_near_neighbours(db, run.project_id, {subject.id: neighbours})
    db.commit()
    change = Change(
        requirements={subject.id} | placed,
        new_findings={f.id for f in findings},
        sentences=[
            narrator.analysed(label_of(subject), related)
            if run.error_message is None
            else f"Analysis of {label_of(subject)} did not finish: {run.error_message}"
        ],
    )
    return publish(db, run.project_id, change, actor=author_of(db, subject))


def _document_run_finished(
    db: Session, run: AnalysisRun, findings: list[Finding]
) -> GraphDelta | None:
    document = db.get(Document, run.subject_id)
    if document is None:
        return None
    requirement_ids = set(
        db.scalars(select(Requirement.id).where(Requirement.document_id == document.id))
    )
    kinds = [graph_service.KIND[f.category] for f in findings if graph_service.on_the_map(f)]
    sentence = (
        narrator.document_analysed(document.filename, kinds)
        if run.error_message is None
        else f"Analysis of {document.filename} did not finish: {run.error_message}"
    )
    # Extraction published nothing, so the document's requirements arrive as new nodes; a client
    # that already has them (from a snapshot) simply replaces them.
    change = Change(
        new_requirements=requirement_ids,
        new_findings={f.id for f in findings},
        sentences=[sentence],
    )
    actor = db.get(User, document.uploaded_by) if document.uploaded_by else None
    return publish(db, run.project_id, change, actor=actor)


def _pairs(db: Session, findings: list[Finding]) -> dict[uuid.UUID, CandidatePair]:
    ids = [f.candidate_pair_id for f in findings if f.candidate_pair_id]
    if not ids:
        return {}
    return {p.id: p for p in db.scalars(select(CandidatePair).where(CandidatePair.id.in_(ids)))}


def _labels(db: Session, requirement_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not requirement_ids:
        return {}
    return {
        r.id: label_of(r)
        for r in db.scalars(select(Requirement).where(Requirement.id.in_(list(requirement_ids))))
    }


def _nearest(db: Session, requirement: Requirement) -> list[uuid.UUID]:
    """Neighbours to place a node next to when it has no findings: its closest requirements."""
    from app.embeddings.store import nearest_requirements

    vector = db.scalar(select(Embedding.vector).where(Embedding.requirement_id == requirement.id))
    if vector is None:
        return []
    return [
        n.requirement_id
        for n in nearest_requirements(
            db, requirement.project_id, list(vector), k=3, exclude={requirement.id}
        )
    ]
