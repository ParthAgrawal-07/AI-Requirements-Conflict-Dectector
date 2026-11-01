from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EventEnvelope(BaseModel):
    """Common metadata shared by project-scoped events."""

    model_config = ConfigDict(extra="forbid")

    type: str = Field(min_length=1, max_length=100)
    workspace_id: UUID
    project_id: UUID
    channel_id: UUID | None = None
    entity_id: UUID | None = None
    at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class GraphNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=200)
    label: str | None = Field(default=None, max_length=500)
    kind: str | None = Field(default=None, max_length=100)
    data: dict[str, object] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=200)
    source: str = Field(min_length=1, max_length=200)
    target: str = Field(min_length=1, max_length=200)
    label: str | None = Field(default=None, max_length=500)
    kind: str | None = Field(default=None, max_length=100)
    data: dict[str, object] = Field(default_factory=dict)


class GraphDeltaChanges(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nodes: list[GraphNode] = Field(default_factory=list, max_length=5000)
    edges: list[GraphEdge] = Field(default_factory=list, max_length=20000)


class GraphDeltaRemoved(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nodes: list[str] = Field(default_factory=list, max_length=5000)
    edges: list[str] = Field(default_factory=list, max_length=20000)


class GraphDeltaEvent(EventEnvelope):
    """One revision of the graph belonging to a project."""

    type: Literal["graph.delta"] = "graph.delta"

    revision: int = Field(ge=1)
    actor_id: UUID | None = None

    added: GraphDeltaChanges = Field(default_factory=GraphDeltaChanges)
    changed: GraphDeltaChanges = Field(default_factory=GraphDeltaChanges)
    removed: GraphDeltaRemoved = Field(default_factory=GraphDeltaRemoved)
