from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.graph.schemas import GraphDeltaEvent


def test_graph_delta_defaults_to_empty_change_sets() -> None:
    event = GraphDeltaEvent(project_id=uuid4(), revision=1)
    assert event.type == "graph.delta"
    assert event.added.nodes == []
    assert event.changed.edges == []
    assert event.removed.nodes == []


def test_graph_delta_accepts_added_node_and_edge() -> None:
    event = GraphDeltaEvent(
        project_id=uuid4(),
        revision=2,
        added={
            "nodes": [{"id": "req-1", "label": "Requirement 1"}],
            "edges": [{"id": "link-1", "source": "req-1", "target": "req-2"}],
        },
    )
    assert event.added.nodes[0].id == "req-1"
    assert event.added.edges[0].target == "req-2"


def test_graph_delta_requires_positive_revision() -> None:
    with pytest.raises(ValidationError):
        GraphDeltaEvent(project_id=uuid4(), revision=0)


def test_graph_delta_rejects_unknown_top_level_fields() -> None:
    with pytest.raises(ValidationError):
        GraphDeltaEvent(project_id=uuid4(), revision=1, surprise=True)
