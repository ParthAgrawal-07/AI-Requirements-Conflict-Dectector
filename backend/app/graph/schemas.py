"""Live-map graph schemas (Dhavni — US-14; agreed in Sprint 0 with Abhijeet and Pranshu).

``GET /projects/{p}/graph`` returns a :class:`GraphSnapshot`; after every change that affects the
map the server publishes a ``graph.delta`` event whose ``data`` is a :class:`GraphDelta`.
A client applies a delta only if ``from_revision`` equals the revision it holds; otherwise it
re-fetches the snapshot (missed events are never replayed).

Nodes are requirements, edges are findings (and, from Sprint 5, human links). Requirement text
stays out of the map payloads: ``label`` is the printed ID (``REQ-014``) and the drawer fetches
the statement over REST. Delta ``sentences`` name requirements by ID and people by name only.
"""

import uuid
from typing import Literal

from pydantic import BaseModel, Field

NodeState = Literal["Proposed", "Under_Review", "Approved", "Rejected", "Implemented", "Deprecated"]
EdgeKind = Literal["conflict", "duplicate", "depends_on", "ambiguous", "incomplete", "link"]
EdgeStatus = Literal["flagged", "confirmed", "dismissed", "merged", "reclassified"]


class GraphNode(BaseModel):
    id: uuid.UUID  # requirement id
    label: str | None  # printed ID, e.g. "REQ-014"; None when the document had none
    state: NodeState
    group: str | None = None  # stakeholder group, for "group by" on the map
    owner_id: uuid.UUID | None = None
    req_type: str | None = None  # functional / non_functional / constraint: the node's shape
    origin: Literal["document", "post", "change_request"] = "document"
    is_protected: bool = False
    open_issues: int = 0  # issues arrive with US-52 (Sprint 4)
    # The shared, persisted layout (``node_positions``); None until someone places the node.
    x: float | None = None
    y: float | None = None


class GraphEdge(BaseModel):
    id: uuid.UUID  # finding id (or link id)
    source: uuid.UUID
    target: uuid.UUID  # == source for a single-requirement finding: the map draws a badge
    kind: EdgeKind
    status: EdgeStatus = "flagged"  # the human review state (US-10)
    severity: Literal["low", "medium", "high"] | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class GraphSnapshot(BaseModel):
    project_id: uuid.UUID
    revision: int
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class GraphChanges(BaseModel):
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)


class GraphRemovals(BaseModel):
    node_ids: list[uuid.UUID] = Field(default_factory=list)
    edge_ids: list[uuid.UUID] = Field(default_factory=list)


class GraphDelta(BaseModel):
    project_id: uuid.UUID
    from_revision: int
    to_revision: int
    # Who caused it (the poster, the reviewer…); None for the system (e.g. a budget resume).
    actor_id: uuid.UUID | None = None
    actor_name: str | None = None
    added: GraphChanges = Field(default_factory=GraphChanges)
    changed: GraphChanges = Field(default_factory=GraphChanges)
    removed: GraphRemovals = Field(default_factory=GraphRemovals)
    # The written feed under the map (US-14), e.g. "Arjun added REQ-031." Template sentences
    # built by ``app.graph.narrator``, never by an LLM. Empty for layout-only changes.
    sentences: list[str] = Field(default_factory=list)


class NodePlacement(BaseModel):
    requirement_id: uuid.UUID
    x: float = Field(ge=-1_000_000, le=1_000_000)
    y: float = Field(ge=-1_000_000, le=1_000_000)


class PositionsUpdate(BaseModel):
    positions: list[NodePlacement] = Field(min_length=1, max_length=500)
