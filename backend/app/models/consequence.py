"""Consequence reports (Madhav — US-11, US-34, FR-24, FR-25, FR-64, FR-99; migration 0007b).

One row per run of a change request's checks (``app.consequences.tasks``); the newest is the
report the change request page shows. The JSON columns hold ids, labels, states and template
sentences — never requirement text — so a report can be shown to anyone who may see the request.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin

EMPTY_DELTA: dict[str, list[Any]] = {"resolved": [], "new": [], "still_open": [], "must_rerun": []}


class ConsequenceReport(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "consequence_reports"
    __table_args__ = (
        CheckConstraint("status IN ('done', 'failed')", name="status_values"),
        CheckConstraint(
            "risk_level IS NULL OR risk_level IN ('low', 'medium', 'high')",
            name="risk_level_values",
        ),
        Index(
            "ix_consequence_reports_change_request_id_created_at",
            "change_request_id",
            "created_at",
        ),
    )

    change_request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("change_requests.id", ondelete="CASCADE")
    )
    # What the checks ran on (FR-98): the proposal's revision, the requirement version it was
    # written against, and the project's baseline revision at the time.
    proposal_revision: Mapped[int]
    base_version: Mapped[int]
    baseline_revision: Mapped[int]
    status: Mapped[str] = mapped_column(String(16), default="done", server_default="done")
    risk_level: Mapped[str | None] = mapped_column(String(8))
    risk_reasons: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    affected: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    checks: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    findings_delta: Mapped[dict[str, list[Any]]] = mapped_column(
        JSONB,
        default=lambda: {k: [] for k in EMPTY_DELTA},
        server_default=text(
            """'{"resolved": [], "new": [], "still_open": [], "must_rerun": []}'::jsonb"""
        ),
    )
    narrative: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # Keval: AI, labelled
    is_stale: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    llm_calls: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
