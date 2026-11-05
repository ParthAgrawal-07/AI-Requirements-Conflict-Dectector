"""Real-time event envelope (Dhavni — US-03, US-29, design update §3.4).

Every message pushed to browsers has the same shape::

    {"type": "analysis.progress", "workspace_id": "...", "project_id": "...",
     "channel_id": null, "entity_id": "<document id>", "at": "2026-10-24T10:42:00Z",
     "data": {...}}

* ``type`` is ``<area>.<what happened>``; the constants below are the ones that exist today.
* ``workspace_id`` decides who may receive it (the gateway checks membership on subscribe);
  ``project_id`` / ``channel_id`` narrow it further.
* ``data`` carries ids, states and numbers only — never requirement or message text (CR-04).
  A client that needs the text re-reads it over REST, which also re-checks permissions.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

ANALYSIS_PROGRESS = "analysis.progress"  # a document moved to a new stage or percentage (US-03)
MEMBERSHIP_REVOKED = "membership.revoked"  # the gateway closes the member's sockets (US-26, S2)
GRAPH_DELTA = "graph.delta"  # nodes/edges changed on the live map (US-14, S3)

EVENT_TYPES = frozenset({ANALYSIS_PROGRESS, MEMBERSHIP_REVOKED, GRAPH_DELTA})


class Event(BaseModel):
    type: str
    workspace_id: uuid.UUID
    project_id: uuid.UUID | None = None
    channel_id: uuid.UUID | None = None
    entity_id: uuid.UUID | None = None
    at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    data: dict[str, Any] = Field(default_factory=dict)


def analysis_progress(
    *,
    workspace_id: uuid.UUID,
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    status: str,
    progress_percent: int,
    stage: str | None = None,
    error_message: str | None = None,
) -> Event:
    """A document's processing state, as ``GET /documents/{id}`` would report it."""
    return Event(
        type=ANALYSIS_PROGRESS,
        workspace_id=workspace_id,
        project_id=project_id,
        entity_id=document_id,
        data={
            "document_id": str(document_id),
            "status": status,
            "progress_percent": progress_percent,
            "stage": stage,
            "error_message": error_message,
        },
    )


def membership_revoked(*, workspace_id: uuid.UUID, user_id: uuid.UUID) -> Event:
    """The user left or was removed: the gateway closes their sockets (US-26, NFR-27)."""
    return Event(
        type=MEMBERSHIP_REVOKED,
        workspace_id=workspace_id,
        entity_id=user_id,
        data={"user_id": str(user_id)},
    )
