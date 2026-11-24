"""Votes, watches and human links (Madhav — US-53, FR-80, FR-90, FR-91, DR-17, DR-19;
migration 0008a; design update §4.1).

* ``votes`` — one per member and subject (a requirement or a change request): *support* or
  *oppose* with an optional reason. Votes are shown to whoever decides; they never change a state
  and no agreement rule counts them (DR-17).
* ``watches`` — a member follows a requirement, an issue or a change request and hears about its
  activity (US-38, kind ``watching``).
* ``requirement_links`` — a person asserts that one requirement *depends on*, *refines* or is
  *related to* another. The map draws them apart from AI-detected relationships, impact analysis
  (US-11) follows them, and nothing automatic ever deletes one (DR-19).

Comments on a requirement reuse the ``comments`` table of US-52 (``subject_type='requirement'``).
"""

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin

VOTE_SUBJECTS = ("requirement", "change_request")
WATCH_SUBJECTS = ("requirement", "issue", "change_request")
STANCES = ("support", "oppose")
LINK_KINDS = ("depends_on", "refines", "related_to")


def _values(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Vote(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "votes"
    __table_args__ = (
        UniqueConstraint("subject_type", "subject_id", "user_id"),
        CheckConstraint(_values("subject_type", VOTE_SUBJECTS), name="subject_type_values"),
        CheckConstraint(_values("stance", STANCES), name="stance_values"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    subject_type: Mapped[str] = mapped_column(String(16))
    subject_id: Mapped[uuid.UUID]
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    stance: Mapped[str] = mapped_column(String(8))
    reason: Mapped[str | None] = mapped_column(Text)


class Watch(CreatedAtMixin, Base):
    __tablename__ = "watches"
    __table_args__ = (
        CheckConstraint(_values("subject_type", WATCH_SUBJECTS), name="subject_type_values"),
        Index("ix_watches_subject_type_subject_id", "subject_type", "subject_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    subject_type: Mapped[str] = mapped_column(String(16), primary_key=True)
    subject_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))


class RequirementLink(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "requirement_links"
    __table_args__ = (
        UniqueConstraint("source_id", "target_id", "kind"),
        CheckConstraint("source_id <> target_id", name="not_self"),
        CheckConstraint(_values("kind", LINK_KINDS), name="kind_values"),
        Index("ix_requirement_links_target_id", "target_id"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    # "source depends on / refines / is related to target"
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("requirements.id", ondelete="CASCADE"))
    target_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("requirements.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(16))
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
