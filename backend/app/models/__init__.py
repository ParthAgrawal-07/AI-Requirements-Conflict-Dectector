"""SQLAlchemy models (Role 5).

Importing this package registers every table on ``Base.metadata`` — Alembic's ``env.py``
relies on that, so a new model file must be imported here.
"""

from app.models.analysis import CandidatePair, Clarification, Finding
from app.models.audit import AuditLog
from app.models.base import Base
from app.models.document import Document
from app.models.embedding import EMBEDDING_DIM, Embedding
from app.models.enums import (
    AuditAction,
    DocumentFormat,
    DocumentStatus,
    FindingCategory,
    FindingStatus,
    Role,
    Severity,
)
from app.models.requirement import Requirement, RequirementVersion
from app.models.user import User
from app.models.workspace import Workspace

__all__ = [
    "EMBEDDING_DIM",
    "AuditAction",
    "AuditLog",
    "Base",
    "CandidatePair",
    "Clarification",
    "Document",
    "DocumentFormat",
    "DocumentStatus",
    "Embedding",
    "Finding",
    "FindingCategory",
    "FindingStatus",
    "Requirement",
    "RequirementVersion",
    "Role",
    "Severity",
    "User",
    "Workspace",
]
