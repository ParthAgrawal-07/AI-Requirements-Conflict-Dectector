"""Domain enumerations shared by models, schemas and services (Role 5)."""

from enum import StrEnum


class PlatformRole(StrEnum):
    """Account-level roles that live outside any workspace (``users.platform_role``).

    Workspace roles are *data* (``roles`` / ``role_permissions``, ADR-20) and never an enum:
    authorisation checks permissions, not role names. Only two things are platform-wide:

    * ``platform_admin`` — created by the CLI (FR-37); may create workspaces (FR-43).
    * ``service`` — reserved for API keys / background clients (post-MVP, FR-40).
    """

    PLATFORM_ADMIN = "platform_admin"
    SERVICE = "service"


class ProjectStatus(StrEnum):
    """Project lifecycle (FR-47, FR-103). No analysis may run while a project is in ``setup``."""

    SETUP = "setup"
    ACTIVE = "active"
    ARCHIVED = "archived"


class ImportMode(StrEnum):
    """How an uploaded SRS enters a project (FR-01, SX-08)."""

    BASELINE = "baseline"  # requirements become Approved (needs ``baseline.manage``)
    PROPOSALS = "proposals"  # requirements become Proposed (needs ``doc.upload``)


class RequirementState(StrEnum):
    """Requirement lifecycle (design update §7.1). Only Approved/Implemented form the baseline."""

    PROPOSED = "Proposed"
    UNDER_REVIEW = "Under_Review"
    APPROVED = "Approved"
    REJECTED = "Rejected"
    IMPLEMENTED = "Implemented"
    DEPRECATED = "Deprecated"


class RequirementOrigin(StrEnum):
    """Where a requirement came from (DR-06)."""

    DOCUMENT = "document"
    POST = "post"
    CHANGE_REQUEST = "change_request"


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
    """How bad a finding is (FR-42) — distinct from confidence ("how sure").

    Revision 5 uses three levels; ``critical`` was retired in migration 0003 (A1).
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AuditAction(StrEnum):
    """Well-known audit actions. The column is free-form so later sprints can add more."""

    VIEWED_PROTECTED = "viewed_protected"
    CONFIRMED = "confirmed"
    DISMISSED = "dismissed"
    MERGED = "merged"
    RECLASSIFIED = "reclassified"
    PROTECTION_CHANGED = "protection_changed"
    SIGNED_OFF = "signed_off"
    ESCALATED = "escalated"  # A2 — escalations are audited (FR-36)
    # Tenancy (Sprint 0–1). Identifiers only — never requirement or message text (CR-04).
    WORKSPACE_CREATED = "workspace_created"
    WORKSPACE_UPDATED = "workspace_updated"
    PROJECT_CREATED = "project_created"
    PROJECT_UPDATED = "project_updated"
    MEMBER_ADDED = "member_added"
    DOCUMENT_UPLOADED = "document_uploaded"
    PROJECT_MEMBER_SET = "project_member_set"  # added to a project team / its role changed
    # Project context (US-60). Version numbers and field names only — never brief text.
    CONTEXT_DRAFTED = "context_drafted"
    CONTEXT_UPDATED = "context_updated"
    PROJECT_ACTIVATED = "project_activated"
