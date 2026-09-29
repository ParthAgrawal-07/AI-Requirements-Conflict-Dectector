"""Embedding model (Role 5 schema, populated by Role 2) — FR-07, FR-08."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.requirement import Requirement

# all-MiniLM-L6-v2 output size. Changing the model = new migration + re-embedding job.
EMBEDDING_DIM = 384


class Embedding(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "embeddings"
    __table_args__ = (
        # Approximate nearest-neighbour index for cosine similarity (NFR-01/NFR-02).
        # HNSW needs no training data (unlike IVFFlat, whose lists depend on row count),
        # so it works on an empty table and stays accurate as documents are added.
        Index(
            "ix_embeddings_vector_hnsw",
            "vector",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"vector": "vector_cosine_ops"},
        ),
    )

    requirement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("requirements.id", ondelete="CASCADE"), unique=True
    )
    vector: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))
    # Lets a model upgrade find and re-embed stale rows.
    model_version: Mapped[str] = mapped_column(String(64))

    requirement: Mapped[Requirement] = relationship(back_populates="embedding")
