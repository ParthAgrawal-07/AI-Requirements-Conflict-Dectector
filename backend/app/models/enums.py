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
    # Members and roles (US-26, US-49). Ids only.
    MEMBER_ROLE_CHANGED = "member_role_changed"
    MEMBER_REMOVED = "member_removed"
    MEMBER_LEFT = "member_left"
    ROLE_CREATED = "role_created"
    ROLE_UPDATED = "role_updated"
    ROLE_DELETED = "role_deleted"
    # Project context (US-60). Version numbers and field names only — never brief text.
    CONTEXT_DRAFTED = "context_drafted"
    CONTEXT_UPDATED = "context_updated"
    PROJECT_ACTIVATED = "project_activated"
    # Join codes (US-25). Code ids and code hints only — never the code itself.
    JOIN_CODE_CREATED = "join_code_created"
    JOIN_CODE_REVOKED = "join_code_revoked"
    JOIN_CODE_REDEEMED = "join_code_redeemed"
    JOIN_REQUEST_CREATED = "join_request_created"
    JOIN_REQUEST_APPROVED = "join_request_approved"
    JOIN_REQUEST_DENIED = "join_request_denied"
    # Requirement posts (US-30 groundwork). Requirement, message and channel ids only.
    REQUIREMENT_POSTED = "requirement_posted"
    # Lifecycle and review (US-37, US-10). States, versions and ids; reasons live in
    # requirement_transitions / finding_reviews, not here.
    STATE_CHANGED = "state_changed"
    FINDING_REOPENED = "finding_reopened"
    # Clarification questions (US-09). Ids only; the answer text is on the clarification.
    CLARIFICATION_ANSWERED = "clarification_answered"
    # Owners and groups (US-36). User ids and group names only.
    OWNER_CHANGED = "owner_changed"
    GROUP_CHANGED = "group_changed"
    OWNERSHIP_REQUESTED = "ownership_requested"
    OWNERSHIP_DECIDED = "ownership_decided"
    # Channels (US-28). Channel and user ids only — never names, topics or messages (CR-04).
    CHANNEL_CREATED = "channel_created"
    CHANNEL_UPDATED = "channel_updated"
    CHANNEL_ARCHIVED = "channel_archived"
    CHANNEL_MEMBER_ADDED = "channel_member_added"
    CHANNEL_MEMBER_REMOVED = "channel_member_removed"


class MessageKind(StrEnum):
    """What a channel message is (design update §4.1). Cards are distinct kinds, not chat text."""

    CHAT = "chat"
    REQUIREMENT_POST = "requirement_post"  # creates a Proposed requirement (US-30)
    CHANGE_REQUEST = "change_request"  # card for an opened change request (US-33)
    ANALYSIS_CARD = "analysis_card"  # result of live analysis (US-31)
    SYSTEM = "system"  # "Riya joined", "channel renamed"…


class JoinCodeStatus(StrEnum):
    """Join-code lifecycle (design update §7.3). Only ``active`` codes can be redeemed."""

    ACTIVE = "active"
    REVOKED = "revoked"  # by a manager; irreversible
    EXPIRED = "expired"  # past ``expires_at`` (set at redemption time or by the beat task)
    EXHAUSTED = "exhausted"  # ``uses`` reached ``max_uses``


class JoinRequestStatus(StrEnum):
    """A join request made with an approval-gated code (design update §7.3)."""

    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"  # undecided for 14 days


class ClassificationStatus(StrEnum):
    """Where one candidate pair stands in classification (gap G1, US-05).

    A pair whose output still fails validation after the retries is ``failed`` — recorded and
    reported, never silently dropped.
    """

    PENDING = "pending"
    DONE = "done"  # classified (with or without a finding) for ``a_version``/``b_version``
    FAILED = "failed"


class AnalysisRunStatus(StrEnum):
    """Lifecycle of an analysis run (design update §4.1)."""

    QUEUED = "queued"
    WAITING_BUDGET = "waiting_budget"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class AnalysisScope(StrEnum):
    DOCUMENT = "document"  # a whole uploaded document (Sprint 2)
    REQUIREMENT = "requirement"  # one posted requirement against the baseline (US-31, S3)
    CHANGE_REQUEST = "change_request"  # consequence checks (US-34, S4)
