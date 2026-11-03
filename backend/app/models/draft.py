"""RequirementDraft (Bansil — FR-81, interface design §5.2; migration 0006b).

The composer autosaves what a member has typed so far, every 5 s, privately: a draft is visible
to its author only and never analysed. ``fields`` holds :class:`app.intake.schemas.DraftFields`
as JSON (every field optional). Posting the requirement deletes the draft.
"""

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class RequirementDraft(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "requirement_drafts"
    __table_args__ = (
        Index("ix_requirement_drafts_author_id_project_id", "author_id", "project_id"),
    )

    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    fields: Mapped[dict[str, Any]] = mapped_column(JSONB)
