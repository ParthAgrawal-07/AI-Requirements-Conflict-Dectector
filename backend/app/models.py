from sqlalchemy import Column, Integer, String, ForeignKey, Enum, Text, DateTime
from sqlalchemy.orm import relationship
import enum
import datetime
from .database import Base


# ── Enums ──────────────────────────────────────────────────


class RelationshipType(enum.Enum):
    conflict = "conflict"
    duplicate = "duplicate"
    ambiguous = "ambiguous"
    dependent = "dependent"


class RelationshipStatus(enum.Enum):
    pending = "pending"
    reviewed = "reviewed"


# ── Mixin ──────────────────────────────────────────────────


class TimestampMixin:
    """Provides created_at and updated_at columns to any model."""

    created_at = Column(
        DateTime, default=lambda: datetime.datetime.now(datetime.UTC)
    )
    updated_at = Column(
        DateTime,
        default=lambda: datetime.datetime.now(datetime.UTC),
        onupdate=lambda: datetime.datetime.now(datetime.UTC),
    )


# ── Models ─────────────────────────────────────────────────


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(150), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)


class Document(TimestampMixin, Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    file_size = Column(Integer, nullable=True)  # bytes
    status = Column(String(50), default="uploaded")

    requirements = relationship("Requirement", back_populates="document")


class Requirement(TimestampMixin, Base):
    __tablename__ = "requirements"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    text = Column(Text, nullable=False)
    version = Column(Integer, default=1)

    document = relationship("Document", back_populates="requirements")


class Relationship(TimestampMixin, Base):
    __tablename__ = "relationships"

    id = Column(Integer, primary_key=True, index=True)
    requirement_a_id = Column(
        Integer, ForeignKey("requirements.id"), nullable=False
    )
    requirement_b_id = Column(
        Integer, ForeignKey("requirements.id"), nullable=False
    )
    type = Column(Enum(RelationshipType), nullable=False)
    status = Column(
        Enum(RelationshipStatus), default=RelationshipStatus.pending
    )
    rationale = Column(Text, nullable=True)
    clarification_question = Column(Text, nullable=True)
