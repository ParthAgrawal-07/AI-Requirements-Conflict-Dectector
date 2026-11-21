"""AI resolution suggestions and the feedback on them (Madhav — US-45, FR-68, FR-94, NFR-36,
DR-04, DR-20; migration 0008; design update §3.7; ADR-24).

A ``Suggestion`` holds up to three options for one finding, each ``{text, target, trade_off,
confidence, tbd_slots}``; it never changes a requirement (DR-04). ``SuggestionFeedback`` is every
human response to it — append-only (a database trigger refuses UPDATE and DELETE), so the
outcome distribution reported at CP2 is exactly what people did.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

PENDING, WAITING_BUDGET, READY, FAILED, SUPERSEDED = (
    "pending",
    "waiting_budget",
    "ready",
    "failed",
    "superseded",
)
STATUSES = (PENDING, WAITING_BUDGET, READY, FAILED, SUPERSEDED)

# The six structured outcomes (US-45) plus regenerate, prefer, ratings and the expert rating.
ACCEPTED = "accepted"
ACCEPTED_EDITED = "accepted_edited"
REJECTED_MEANING = "rejected_meaning"
REJECTED_INFEASIBLE = "rejected_infeasible"
REJECTED_MISSING_CONTEXT = "rejected_missing_context"
DEFERRED = "deferred"
REGENERATE = "regenerate"
PREFER = "prefer"
RATE_UP, RATE_DOWN = "rate_up", "rate_down"
EXPERT_RATING = "expert_rating"
OUTCOMES = (
    ACCEPTED,
    ACCEPTED_EDITED,
    REJECTED_MEANING,
    REJECTED_INFEASIBLE,
    REJECTED_MISSING_CONTEXT,
    DEFERRED,
)
ACTIONS = (*OUTCOMES, REGENERATE, PREFER, RATE_UP, RATE_DOWN, EXPERT_RATING)
CHOICES = tuple(a for a in ACTIONS if a not in (DEFERRED, REGENERATE))  # name an option
_STATUS_LIST = ", ".join(f"'{s}'" for s in STATUSES)
_ACTION_LIST = ", ".join(f"'{a}'" for a in ACTIONS)
_CHOICE_LIST = ", ".join(f"'{a}'" for a in CHOICES)


class Suggestion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "suggestions"
    __table_args__ = (
        CheckConstraint(f"status IN ({_STATUS_LIST})", name="status_values"),
        CheckConstraint("llm_calls >= 0", name="llm_calls_non_negative"),
        # Idempotent per finding: regenerating supersedes the live one first.
        Index(
            "uq_suggestions_live_finding_id",
            "finding_id",
            unique=True,
            postgresql_where=text("status <> 'superseded'"),
        ),
        Index("ix_suggestions_project_id_status", "project_id", "status"),
    )

    finding_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("findings.id", ondelete="CASCADE"))
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    # Set when the suggestion was asked for next to a failing check of a change request (US-34).
    change_request_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("change_requests.id", ondelete="SET NULL")
    )
    category: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default=PENDING, server_default=PENDING)
    options: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    prompt_version: Mapped[str | None] = mapped_column(String(16))
    model: Mapped[str | None] = mapped_column(String(80))
    instruction: Mapped[str | None] = mapped_column(Text)  # a regeneration's "keep 30 minutes…"
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    error: Mapped[str | None] = mapped_column(String(64))  # machine-readable, never model text
    llm_calls: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    context_version: Mapped[int | None]
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SuggestionFeedback(UUIDPrimaryKeyMixin, Base):
    """One human response. Never updated or deleted (trigger ``suggestion_feedback_append_only``)."""

    __tablename__ = "suggestion_feedback"
    __table_args__ = (
        CheckConstraint(f"action IN ({_ACTION_LIST})", name="action_values"),
        CheckConstraint(
            f"(action IN ({_CHOICE_LIST})) = (option_index IS NOT NULL)", name="option_for_choices"
        ),
        CheckConstraint(
            "option_index IS NULL OR option_index BETWEEN 0 AND 2", name="option_range"
        ),
        CheckConstraint(
            "action <> 'accepted_edited' OR coalesce(length(trim(final_text)), 0) > 0",
            name="edit_has_text",
        ),
        CheckConstraint(
            "action <> 'regenerate' OR coalesce(length(trim(instruction)), 0) > 0",
            name="regenerate_has_instruction",
        ),
        CheckConstraint(
            "(action = 'expert_rating') = (expert_rating IS NOT NULL)", name="rating_for_experts"
        ),
        CheckConstraint(
            "expert_rating IS NULL OR expert_rating BETWEEN 1 AND 5", name="rating_range"
        ),
        Index("ix_suggestion_feedback_suggestion_id_created_at", "suggestion_id", "created_at"),
    )

    suggestion_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("suggestions.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(32))
    option_index: Mapped[int | None]
    final_text: Mapped[str | None] = mapped_column(Text)  # what people adopted, for an edit
    reason: Mapped[str | None] = mapped_column(Text)  # an optional note with a rejection
    instruction: Mapped[str | None] = mapped_column(Text)
    expert_rating: Mapped[int | None]  # 1–5, the analysts' correctness rating (NFR-36)
    change_request_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("change_requests.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
