"""Live-map layout (Dhavni — US-14; design update §3.4, migration 0006d).

One row per requirement that has been placed on the map. Positions are shared by every viewer
of the project, so the layout stays stable: a new node is placed next to its nearest neighbour
(``app.graph.positions``) and nothing else moves when it appears.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class NodePosition(Base):
    __tablename__ = "node_positions"
    __table_args__ = (Index("ix_node_positions_project_id", "project_id"),)

    requirement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("requirements.id", ondelete="CASCADE"), primary_key=True
    )
    # Denormalised from the requirement so one indexed query loads a project's layout.
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    x: Mapped[float] = mapped_column(Float)
    y: Mapped[float] = mapped_column(Float)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
