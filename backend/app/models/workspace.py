"""Workspace model (Role 5) — the tenancy boundary (FR-38)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Float, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.user import User


class Workspace(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Access boundary: users only see documents and results inside their workspace."""

    __tablename__ = "workspaces"
    __table_args__ = (
        CheckConstraint("similarity_threshold BETWEEN 0 AND 1", name="similarity_threshold_range"),
    )

    name: Mapped[str] = mapped_column(String(120), unique=True)
    # Per-workspace override of the embedding pre-filter threshold (FR-10, US-06).
    similarity_threshold: Mapped[float] = mapped_column(
        Float, server_default=text("0.75"), default=0.75
    )

    users: Mapped[list[User]] = relationship(back_populates="workspace")
    documents: Mapped[list[Document]] = relationship(back_populates="workspace")
