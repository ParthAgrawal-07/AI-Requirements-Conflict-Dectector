"""SQLAlchemy models (Role 5).

Importing this package registers every table on ``Base.metadata`` — Alembic's ``env.py``
relies on that, so a new model file must be imported here.
"""

from app.models.analysis import AnalysisRun, CandidatePair, Clarification, Finding
from app.models.attributes import RequirementAttribute
from app.models.audit import AuditLog
from app.models.base import Base
from app.models.baseline import Baseline, BaselineItem
from app.models.change_request import ChangeRequest, ChangeRequestIssue, ChangeRequestRevision
from app.models.change_review import Review, ReviewComment, ReviewRequest
from app.models.channel import Channel, ChannelMember, ChannelRead, Message
from app.models.consequence import ConsequenceReport
from app.models.context import DocumentSection, ProjectContext
from app.models.decision_rule import DecisionRule
from app.models.document import Document
from app.models.draft import RequirementDraft
from app.models.embedding import EMBEDDING_DIM, Embedding
from app.models.enums import (
    AnalysisRunStatus,
    AnalysisScope,
    AuditAction,
    ClassificationStatus,
    DocumentFormat,
    DocumentStatus,
    FindingCategory,
    FindingStatus,
    ImportMode,
    JoinCodeStatus,
    JoinRequestStatus,
    MessageKind,
    PlatformRole,
    ProjectStatus,
    RequirementOrigin,
    RequirementState,
    Severity,
)
from app.models.graph import ChangeLogVisit, GraphEvent, GraphState, NodePosition
from app.models.issue import Comment, Issue, IssueAssignee, IssueRequirement
from app.models.join_code import JoinCode, JoinRequest
from app.models.membership import Membership, ProjectMember
from app.models.notification import Notification
from app.models.ownership import OwnershipRequest
from app.models.project import Project
from app.models.requirement import Requirement, RequirementVersion
from app.models.review import FindingReview, RequirementTransition
from app.models.role import Role, RolePermission
from app.models.suggestion import Suggestion, SuggestionFeedback
from app.models.user import User
from app.models.workspace import Workspace

__all__ = [
    "ChangeLogVisit",
    "GraphEvent",
    "GraphState",
    "EMBEDDING_DIM",
    "AnalysisRun",
    "AnalysisRunStatus",
    "AnalysisScope",
    "AuditAction",
    "AuditLog",
    "Base",
    "Baseline",
    "BaselineItem",
    "CandidatePair",
    "ChangeRequest",
    "ChangeRequestIssue",
    "ChangeRequestRevision",
    "ClassificationStatus",
    "Channel",
    "ChannelMember",
    "ChannelRead",
    "Clarification",
    "Comment",
    "ConsequenceReport",
    "DecisionRule",
    "Document",
    "DocumentSection",
    "DocumentFormat",
    "DocumentStatus",
    "Embedding",
    "Finding",
    "FindingReview",
    "FindingCategory",
    "FindingStatus",
    "ImportMode",
    "Issue",
    "IssueAssignee",
    "IssueRequirement",
    "JoinCode",
    "JoinCodeStatus",
    "JoinRequest",
    "JoinRequestStatus",
    "Membership",
    "Message",
    "MessageKind",
    "NodePosition",
    "Notification",
    "OwnershipRequest",
    "PlatformRole",
    "Project",
    "ProjectContext",
    "ProjectMember",
    "ProjectStatus",
    "Requirement",
    "RequirementAttribute",
    "RequirementDraft",
    "RequirementOrigin",
    "RequirementState",
    "RequirementTransition",
    "RequirementVersion",
    "Review",
    "ReviewComment",
    "ReviewRequest",
    "Role",
    "RolePermission",
    "Severity",
    "Suggestion",
    "SuggestionFeedback",
    "User",
    "Workspace",
]
