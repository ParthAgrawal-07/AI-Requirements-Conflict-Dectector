"""Redis Pub/Sub publisher for project-scoped graph events.

Redis Pub/Sub is ephemeral. Call publish_graph_delta only after the database transaction
has committed. Clients must fetch a REST snapshot if their revision sequence has a gap.
"""

from __future__ import annotations

import json
from uuid import UUID

from redis.asyncio import Redis

from app.core.config import get_settings
from app.graph.schemas import GraphDeltaEvent


def project_channel(project_id: UUID) -> str:
    return f"rcd:project:{project_id}:events"


async def publish_graph_delta(event: GraphDeltaEvent) -> int:
    """Publish a validated event and return the number of subscribers."""
    redis = Redis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        return await redis.publish(
            project_channel(event.project_id),
            json.dumps(event.model_dump(mode="json"), separators=(",", ":")),
        )
    finally:
        await redis.aclose()
