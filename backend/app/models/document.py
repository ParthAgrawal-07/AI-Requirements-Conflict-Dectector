"""Document model (Role 5) — an uploaded SRS and its processing state (FR-01, FR-02, US-03)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column
from app.models.enums import DocumentFormat, DocumentStatus

if TYPE_CHECKING:
    from app.models.requirement import Requirement
    from app.models.user import User
    from app.models.workspace import Workspace


class Document(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("progress_percent BETWEEN 0 AND 100", name="progress_range"),
        CheckConstraint("size_bytes >= 0", name="size_non_negative"),
        Index("ix_documents_workspace_id_uploaded_at", "workspace_id", "uploaded_at"),
        Index("ix_documents_status", "status"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT")
    )
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))

    filename: Mapped[str] = mapped_column(String(255))
    format: Mapped[DocumentFormat] = mapped_column(enum_column(DocumentFormat, "document_format"))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    # SHA-256 hex digest of the file — detects re-uploads of the same document.
    sha256: Mapped[str] = mapped_column(String(64))
    # Where the API stored the file for the worker to read (shared volume / object store key).
    storage_path: Mapped[str] = mapped_column(String(1024))

    status: Mapped[DocumentStatus] = mapped_column(
        enum_column(DocumentStatus, "document_status"),
        default=DocumentStatus.QUEUED,
        server_default=DocumentStatus.QUEUED.value,
    )
    progress_percent: Mapped[int] = mapped_column(server_default=text("0"), default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    task_id: Mapped[str | None] = mapped_column(String(64))  # Celery task id for the pipeline run

    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    workspace: Mapped[Workspace] = relationship(back_populates="documents")
    uploader: Mapped[User] = relationship()
    requirements: Mapped[list[Requirement]] = relationship(
        back_populates="document", passive_deletes=True, order_by="Requirement.order_index"
    )
