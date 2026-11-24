"""Live-map layout and history (Dhavni — US-14, US-50, US-55; design update §3.4, §3.8;
migrations 0006d, 0009).

``node_positions``: one row per requirement that has been placed on the map. Positions are
shared by every viewer of the project, so the layout stays stable: a new node is placed next to
its nearest neighbour (``app.graph.positions``) and nothing else moves when it appears.

``graph_events``, ``graph_snapshots`` and ``change_log_visits`` (Sprint 6): the written change
log, the map frozen at baseline revisions for the time slider, and each member's last visit.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


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


# ── Written change log and map history (Dhavni — US-55, US-50; migration 0009) ─────────────
EVENT_KINDS = (
    "added",
    "changed",
    "state",
    "owner",
    "analysed",
    "conflict_found",
    "conflict_resolved",
    "reviewed",
    "issue",
    "change_request",
    "merged",
    "concern",
    "link",
)
SUMMARY_COUNTS = (
    "requirements_added",
    "requirements_changed",
    "requirements_deprecated",
    "conflicts_opened",
    "conflicts_resolved",
    "change_requests_merged",
)


class GraphEvent(UUIDPrimaryKeyMixin, Base):
    """One written sentence of the change log (FR-95): a template sentence from
    ``app.graph.narrator``, never LLM text, stored with the map revision it belongs to so the
    Changes panel and the time slider read the same history.

    ``node_ids`` / ``edge_ids`` are what the sentence is about (the panel highlights them);
    ``counts`` holds the numbers a summary adds up (keys in :data:`SUMMARY_COUNTS`).
    Backfilled rows (from the audit log, for changes made before Sprint 6) have no revision.
    """

    __tablename__ = "graph_events"
    __table_args__ = (
        CheckConstraint(f"kind IN ({', '.join(repr(k) for k in EVENT_KINDS)})", name="kind_values"),
        Index("ix_graph_events_project_id_created_at", "project_id", "created_at"),
        Index("ix_graph_events_node_ids", "node_ids", postgresql_using="gin"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    revision: Mapped[int | None]  # projects.graph_revision of the delta; NULL when backfilled
    baseline_revision: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    kind: Mapped[str] = mapped_column(String(24))
    sentence: Mapped[str] = mapped_column(Text)
    node_ids: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    edge_ids: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    counts: Mapped[dict[str, int]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    backfilled: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GraphState(UUIDPrimaryKeyMixin, Base):
    """The whole map frozen at one point the time slider can show (US-50): when a merge starts a
    new baseline revision, and when a labelled baseline is frozen. Read-only history."""

    __tablename__ = "graph_snapshots"
    __table_args__ = (
        Index("ix_graph_snapshots_project_id_captured_at", "project_id", "captured_at"),
        Index(
            "uq_graph_snapshots_project_id_baseline_revision",
            "project_id",
            "baseline_revision",
            unique=True,
            postgresql_where=text("baseline_id IS NULL"),
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    graph_revision: Mapped[int]
    baseline_revision: Mapped[int]
    # Set for the snapshot taken when a labelled baseline was frozen (US-40).
    baseline_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("baselines.id", ondelete="CASCADE"), unique=True
    )
    nodes: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    edges: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ChangeLogVisit(Base):
    """When a member last read the project's change log: "summarise since my last visit"."""

    __tablename__ = "change_log_visits"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
