"""Domain enumerations shared by models, schemas and services (Role 5)."""

from enum import StrEnum


class Role(StrEnum):
    """Application roles — see docs/engineering/roles-and-access.md."""

    ANALYST = "analyst"
    ADMIN = "admin"
    COMPLIANCE_REVIEWER = "compliance_reviewer"
    READ_ONLY = "read_only"
    SERVICE = "service"


class DocumentFormat(StrEnum):
    PDF = "pdf"
    DOCX = "docx"
    TXT = "txt"
    REQIF = "reqif"


class DocumentStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class FindingCategory(StrEnum):
    """The 5-category issue taxonomy (ADR-02)."""

    CONFLICTING = "Conflicting"
    DUPLICATE = "Duplicate"
    AMBIGUOUS = "Ambiguous"
    INCOMPLETE = "Incomplete"
    DEPENDENT = "Dependent"


class FindingStatus(StrEnum):
    FLAGGED = "flagged"
    CONFIRMED = "confirmed"
    DISMISSED = "dismissed"
    MERGED = "merged"
    RECLASSIFIED = "reclassified"


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AuditAction(StrEnum):
    """Well-known audit actions. The column is free-form so later sprints can add more."""

    VIEWED_PROTECTED = "viewed_protected"
    CONFIRMED = "confirmed"
    DISMISSED = "dismissed"
    MERGED = "merged"
    RECLASSIFIED = "reclassified"
    PROTECTION_CHANGED = "protection_changed"
    SIGNED_OFF = "signed_off"
    JOIN_CODE_CREATED = "join_code_created"
    JOIN_CODE_REVOKED = "join_code_revoked"
    JOIN_CODE_REDEEMED = "join_code_redeemed"
    JOIN_REQUEST_CREATED = "join_request_created"
    JOIN_REQUEST_APPROVED = "join_request_approved"
    JOIN_REQUEST_REJECTED = "join_request_rejected"


class JoinCodeStatus(StrEnum):
    """Lifecycle status of a workspace join code (US-25)."""

    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"
    EXHAUSTED = "exhausted"


class JoinRequestStatus(StrEnum):
    """Review status of a pending join request created via approval-gated code."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
