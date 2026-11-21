"""Decision rules (Parth — US-57, FR-65, FR-100, DR-23; migration 0010c; ADR-26).

Who decides which kind of question in a project: a rule matches on finding category, issue
label, stakeholder group, requirement type and the protected flag (unset fields match anything)
and names a **decision owner** — a role, a person, or the requirement's owner — plus required
and optional reviewers (``[{"kind": "role" | "user", "id": "<uuid>"}]``). The most specific
matching rule wins (``app.services.decision_rules``); each project has one default rule that
matches everything.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

ROLE, USER, REQUIREMENT_OWNER = "role", "user", "requirement_owner"
MATCH_FIELDS = ("match_category", "match_label", "match_group", "match_req_type", "match_protected")


class DecisionRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "decision_rules"
    __table_args__ = (
        CheckConstraint(
            "owner_kind IN ('role', 'user', 'requirement_owner')", name="owner_kind_values"
        ),
        CheckConstraint(
            "(owner_kind = 'role') = (owner_role_id IS NOT NULL)", name="role_owner_has_role"
        ),
        CheckConstraint(
            "(owner_kind = 'user') = (owner_user_id IS NOT NULL)", name="user_owner_has_user"
        ),
        CheckConstraint(
            "NOT is_default OR num_nonnulls(match_category, match_label, match_group, "
            "match_req_type, match_protected) = 0",
            name="default_matches_all",
        ),
        Index("ix_decision_rules_project_id", "project_id"),
        Index(
            "uq_decision_rules_default_project_id",
            "project_id",
            unique=True,
            postgresql_where=text("is_default"),
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120))
    priority: Mapped[int] = mapped_column(
        default=100, server_default=text("100")
    )  # lower wins ties
    match_category: Mapped[str | None] = mapped_column(String(32))
    match_label: Mapped[str | None] = mapped_column(String(64))
    match_group: Mapped[str | None] = mapped_column(String(120))
    match_req_type: Mapped[str | None] = mapped_column(String(32))
    match_protected: Mapped[bool | None]
    owner_kind: Mapped[str] = mapped_column(String(24))
    owner_role_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("roles.id", ondelete="RESTRICT")
    )
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    required_reviewers: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    optional_reviewers: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    is_default: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    @property
    def specificity(self) -> int:
        return sum(getattr(self, name) is not None for name in MATCH_FIELDS)
