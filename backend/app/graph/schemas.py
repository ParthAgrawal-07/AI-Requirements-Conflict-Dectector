"""Live-map graph schemas (Dhavni — US-14; agreed in Sprint 0 with Abhijeet and Pranshu).

``GET /projects/{p}/graph`` (Sprint 2) returns a :class:`GraphSnapshot`; after every analysis run
the server publishes a ``graph.delta`` event whose ``data`` is a :class:`GraphDelta` (Sprint 3).
A client applies a delta only if ``from_revision`` equals the revision it holds; otherwise it
re-fetches the snapshot (missed events are never replayed).

Nodes are requirements, edges are findings (and, later, human links). Text stays out of deltas:
``label`` is the printed ID (``REQ-014``) and the client fetches the statement over REST.
"""

import uuid
from typing import Literal

from pydantic import BaseModel, Field

NodeState = Literal["Proposed", "Under_Review", "Approved", "Rejected", "Implemented", "Deprecated"]
EdgeKind = Literal["conflict", "duplicate", "depends_on", "ambiguous", "incomplete", "link"]


class GraphNode(BaseModel):
    id: uuid.UUID  # requirement id
    label: str | None  # printed ID, e.g. "REQ-014"; None when the document had none
    state: NodeState
    group: str | None = None  # stakeholder group, for "group by" on the map
    owner_id: uuid.UUID | None = None
    open_issues: int = 0


class GraphEdge(BaseModel):
    id: uuid.UUID  # finding id (or link id)
    source: uuid.UUID
    target: uuid.UUID
    kind: EdgeKind
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
    added: GraphChanges = Field(default_factory=GraphChanges)
    changed: GraphChanges = Field(default_factory=GraphChanges)
    removed: GraphRemovals = Field(default_factory=GraphRemovals)
    # One-line written feed under the map (US-14), e.g. "REQ-041 added by Heet; conflicts with
    # REQ-012". Template sentences built by the narrator (S3), not by an LLM.
    sentences: list[str] = Field(default_factory=list)
