"""Finding schemas (Keval with Abhijeet — US-07). AI output is labelled ``source = "AI"``."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

from app.models import FindingCategory, FindingStatus, RequirementOrigin, RequirementState, Severity
from app.services.findings import FindingView


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
    analysis_run_id: uuid.UUID | None
    created_at: datetime

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
            analysis_run_id=finding.analysis_run_id,
            created_at=finding.created_at,
        )
