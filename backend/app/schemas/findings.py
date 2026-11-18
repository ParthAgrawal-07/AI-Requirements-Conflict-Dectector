"""Finding schemas (Keval with Abhijeet — US-07; Parth — US-10 review). AI output is labelled
``source = "AI"``; after a human review the AI's own category stays visible as ``ai_category``
(FR-20)."""

import uuid
from datetime import datetime
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from app.models import (
    Clarification,
    FindingCategory,
    FindingReview,
    FindingStatus,
    RequirementOrigin,
    RequirementState,
    Severity,
)
from app.services.findings import FindingView
from app.services.review_state import ReviewAction


class FindingRequirement(BaseModel):
    """A requirement the finding is about, with where it came from (US-07)."""

    id: uuid.UUID
    label: str | None  # printed ID
    body: str
    state: RequirementState
    is_protected: bool
    origin: RequirementOrigin
    section_heading: str | None  # the source section of an extracted requirement
    location: str | None
    document_id: uuid.UUID | None
    origin_message_id: uuid.UUID | None  # the post a posted requirement came from


class ClarificationRead(BaseModel):
    """A finding's clarification question (US-09) — AI-written, answered by a person (FR-23)."""

    id: uuid.UUID
    finding_id: uuid.UUID
    source: Literal["AI"] = "AI"
    question: str
    addressed_to: str | None  # "owner" or "stakeholders"
    answered: bool
    resolution: str | None
    resolved_by: uuid.UUID | None
    resolved_at: datetime | None
    message_id: uuid.UUID | None  # the thread reply it was posted as
    prompt_version: str | None
    llm_model: str | None
    created_at: datetime

    @classmethod
    def from_model(cls, row: Clarification) -> "ClarificationRead":
        return cls(
            id=row.id,
            finding_id=row.finding_id,
            question=row.question,
            addressed_to=row.addressed_to,
            answered=row.resolved_at is not None,
            resolution=row.resolution,
            resolved_by=row.resolved_by,
            resolved_at=row.resolved_at,
            message_id=row.message_id,
            prompt_version=row.prompt_version,
            llm_model=row.llm_model,
            created_at=row.created_at,
        )


class EvidenceSpan(BaseModel):
    requirement_id: uuid.UUID
    label: str
    quote: str
    start: int  # character offsets into that requirement's ``body``
    end: int


class FindingRead(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    source: Literal["AI"] = "AI"  # human-raised concerns arrive with US-56 (Sprint 4)
    category: FindingCategory
    status: FindingStatus
    severity: Severity | None
    confidence: float
    confidence_percent: int
    # Below the project's confidence threshold: "low confidence — recommend manual review".
    low_confidence: bool
    explanation: str
    evidence_spans: list[EvidenceSpan]
    requirements: list[FindingRequirement]
    dependency_direction: str | None = None
    vague_terms: list[str] = []
    missing_information: list[str] = []
    context_version: int | None
    prompt_version: str | None
    llm_model: str | None = None  # "<provider>/<model>" that produced it (ADR-31)
    analysis_run_id: uuid.UUID | None
    created_at: datetime
    # US-10: the category the model gave (unchanged by a reclassification) and the last review.
    ai_category: FindingCategory | None = None
    merged_into_id: uuid.UUID | None = None
    reviewed_by: uuid.UUID | None = None
    reviewed_at: datetime | None = None
    # US-09: the question, once generated. US-10: "resolved" = accepted and its question answered.
    clarification: ClarificationRead | None = None
    resolved: bool = False

    @classmethod
    def from_view(cls, view: FindingView) -> "FindingRead":
        finding = view.finding
        output: dict[str, Any] = finding.original_ai_output or {}
        return cls(
            id=finding.id,
            project_id=finding.project_id,
            category=finding.category,
            status=finding.status,
            severity=finding.severity,
            confidence=finding.confidence,
            confidence_percent=round(finding.confidence * 100),
            low_confidence=view.low_confidence,
            explanation=finding.explanation or finding.rationale,
            evidence_spans=[EvidenceSpan.model_validate(s) for s in finding.evidence_spans or []],
            requirements=[
                FindingRequirement(
                    id=r.id,
                    label=r.source_req_id,
                    body=r.body,
                    state=r.state,
                    is_protected=r.is_protected,
                    origin=r.origin,
                    section_heading=r.section_heading,
                    location=r.location,
                    document_id=r.document_id,
                    origin_message_id=r.origin_message_id,
                )
                for r in view.requirements
            ],
            dependency_direction=output.get("dependency_direction"),
            vague_terms=list(output.get("vague_terms") or []),
            missing_information=list(output.get("missing_information") or []),
            context_version=finding.context_version,
            prompt_version=finding.prompt_version,
            llm_model=finding.llm_model,
            analysis_run_id=finding.analysis_run_id,
            created_at=finding.created_at,
            ai_category=_category(output.get("category")),
            merged_into_id=finding.merged_into_id,
            reviewed_by=finding.reviewed_by,
            reviewed_at=finding.reviewed_at,
            clarification=(
                ClarificationRead.from_model(finding.clarification)
                if finding.clarification is not None
                else None
            ),
            resolved=finding.status is FindingStatus.CONFIRMED
            and finding.clarification is not None
            and finding.clarification.resolved_at is not None,
        )


def _category(value: object) -> FindingCategory | None:
    try:
        return FindingCategory(str(value))
    except ValueError:  # "None" or a value from an older prompt
        return None


class ReviewRequest(BaseModel):
    """``POST /findings/{id}/review`` (US-10)."""

    model_config = ConfigDict(extra="forbid")

    action: ReviewAction
    reason: str | None = Field(default=None, max_length=2000)  # required to dismiss
    category: FindingCategory | None = None  # reclassify
    merge_into: uuid.UUID | None = None  # merge


class FindingReviewRead(BaseModel):
    id: uuid.UUID
    action: ReviewAction
    actor_id: uuid.UUID
    from_status: FindingStatus
    to_status: FindingStatus
    from_category: FindingCategory
    to_category: FindingCategory
    reason: str | None
    merged_into_id: uuid.UUID | None
    created_at: datetime

    @classmethod
    def from_model(cls, row: FindingReview) -> "FindingReviewRead":
        return cls(
            id=row.id,
            action=cast(ReviewAction, row.action),  # the CHECK constraint keeps it in range
            actor_id=row.actor_id,
            from_status=row.from_status,
            to_status=row.to_status,
            from_category=row.from_category,
            to_category=row.to_category,
            reason=row.reason,
            merged_into_id=row.merged_into_id,
            created_at=row.created_at,
        )
