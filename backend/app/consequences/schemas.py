"""Pydantic schemas for Change-Impact Analysis & Consequence Evaluation (Role 4).

These schemas define the Sprint 0 data contracts for consequence assessment (US-11,
FR-24, FR-25, DR-05). Whenever a user proposes modifying a requirement, the impact
engine evaluates direct and transitive ripples through the dependency and conflict
graph before the modification is committed.

Contract Notes:
- Sprint 0 Scope: Data contracts and check-result structures only.
- Sprint 4+ Scope: Full graph traversal engine (`ImpactAnalyzer.analyse`), vector
  neighbour lookups, and Celery task orchestration.
- Grounded in current project documents (`docs/clarification-impact-design.md`,
  `docs/engineering/object-design.md`, and `docs/engineering/requirements-spec.md`).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import Severity


class ImpactType(StrEnum):
    """Categorization of the relationship linking the edited requirement to an affected requirement."""

    DIRECT_DEPENDENCY = "direct_dependency"
    CONFLICT_PARTNER = "conflict_partner"
    SEMANTIC_SIMILARITY = "semantic_similarity"
    DUPLICATE_OVERLAP = "duplicate_overlap"
    SHARED_CONSTRAINT = "shared_constraint"


class ImpactStatus(StrEnum):
    """Verification state distinguishing heuristic AI inferences from confirmed facts (NFR-17)."""

    POTENTIAL = "potential"  # AI-inferred from vector similarity or unreviewed candidate pairs
    CONFIRMED = (
        "confirmed"  # Verified by human analyst, explicit dependency link, or compliance tag
    )


class CheckType(StrEnum):
    """Specific integrity and consequence checks executed during impact analysis."""

    CIRCULAR_DEPENDENCY = "circular_dependency"
    PROTECTED_REQUIREMENT = "protected_requirement"
    CONFLICT_PARTNER = "conflict_partner"
    SEMANTIC_DRIFT = "semantic_drift"


class CheckStatus(StrEnum):
    """Status outcome for an individual impact/consequence check."""

    PASSED = "passed"
    WARNING = "warning"
    FAILED = "failed"
    INFO = "info"


class ImpactItem(BaseModel):
    """One requirement affected by a proposed requirement edit (direct or transitive)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    requirement_id: uuid.UUID = Field(
        ..., description="UUID of the impacted requirement in the database"
    )
    source_req_id: str | None = Field(
        default=None,
        description="Source identifier printed in the SRS (e.g. 'REQ-041'), if present",
    )
    body_preview: str = Field(
        ...,
        min_length=1,
        description="Verbatim text snippet of the affected requirement for reviewer context",
    )
    location: str | None = Field(
        default=None,
        description="Source location in original document (e.g. 'Page 14, Section 3.2')",
    )
    relationship_type: ImpactType = Field(
        ..., description="Taxonomy of the link connecting source to target"
    )
    status: ImpactStatus = Field(
        default=ImpactStatus.POTENTIAL,
        description="Whether this impact is inferred (potential) or verified (confirmed)",
    )
    severity: Severity = Field(
        default=Severity.MEDIUM,
        description="Severity of the impact if the proposed edit is applied",
    )
    reason: str = Field(
        ...,
        min_length=1,
        description="Plain-language explanation of why this requirement is affected (NFR-15)",
    )
    depth: int = Field(
        default=1,
        ge=1,
        description="Graph traversal distance: 1 = direct relationship, 2+ = transitive ripple",
    )
    is_protected: bool = Field(
        default=False,
        description="True if target requirement is compliance-critical or regulatory (DR-05)",
    )


class CheckResult(BaseModel):
    """Result of an automated consequence or integrity check run before an edit is saved."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    check_name: str = Field(
        ..., min_length=1, description="Human-readable identifier for the check"
    )
    check_type: CheckType = Field(
        ..., description="Taxonomy category of the rule or verification executed"
    )
    status: CheckStatus = Field(..., description="Outcome status: passed, warning, failed, or info")
    severity: Severity = Field(
        default=Severity.MEDIUM,
        description="Severity level associated with this check outcome",
    )
    passed: bool = Field(
        ..., description="True if the check did not detect any violations or blocking conditions"
    )
    message: str = Field(
        ..., min_length=1, description="Summary explanation of the check evaluation"
    )
    details: dict[str, Any] | None = Field(
        default=None,
        description="Structured context specific to the check (e.g. cycle path list, score)",
    )


class ImpactReport(BaseModel):
    """Complete consequence evaluation report presented before saving a requirement edit (US-11).

    This contract satisfies the interface of `ImpactAnalyzer.analyse(requirement_id, proposed_body)`
    as defined in `docs/engineering/object-design.md`. It allows the project manager or architect
    to inspect all potential ripple effects and rule violations before confirming changes.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_requirement_id: uuid.UUID = Field(
        ..., description="UUID of the requirement currently being edited"
    )
    source_req_id: str | None = Field(
        default=None,
        description="Document-level requirement identifier (e.g. 'REQ-014'), if known",
    )
    source_version: int = Field(
        ..., ge=1, description="Current version number prior to applying this edit"
    )
    proposed_body: str = Field(
        ...,
        min_length=1,
        description="The candidate requirement body text being analyzed prior to saving",
    )
    analyzed_at: datetime = Field(
        ..., description="UTC timestamp when the impact analysis was performed"
    )
    total_impacted_count: int = Field(
        default=0,
        ge=0,
        description="Total count of unique downstream requirements affected",
    )
    critical_impacts_count: int = Field(
        default=0,
        ge=0,
        description="Count of impacted requirements with CRITICAL severity or compliance lock",
    )
    has_circular_dependency: bool = Field(
        default=False,
        description="True if directed dependency traversal encountered a circular back-edge",
    )
    circular_dependency_path: list[str] | None = Field(
        default=None,
        description="Ordered sequence of requirement IDs forming the dependency cycle, if detected",
    )
    has_protected_impact: bool = Field(
        default=False,
        description="True if any impacted requirement is marked is_protected per DR-05",
    )
    requires_manual_approval: bool = Field(
        default=False,
        description="True if regulatory constraints (DR-05) mandate human sign-off before save",
    )
    safe_to_apply: bool = Field(
        default=True,
        description="True if no blocking conditions (such as circular dependencies) exist",
    )
    impacted_requirements: list[ImpactItem] = Field(
        default_factory=list,
        description="List of all directly and transitively impacted requirements",
    )
    checks: list[CheckResult] = Field(
        default_factory=list,
        description="Detailed results of each individual automated safety check",
    )

    @model_validator(mode="after")
    def _validate_consistency(self) -> Self:
        """Enforce internal consistency between items, counts, and safety flags."""
        # Reconcile total impacted count
        if self.impacted_requirements and self.total_impacted_count == 0:
            self.total_impacted_count = len(self.impacted_requirements)

        # Reconcile critical impacts count
        critical_items = [
            item for item in self.impacted_requirements if item.severity == Severity.CRITICAL
        ]
        if critical_items and self.critical_impacts_count == 0:
            self.critical_impacts_count = len(critical_items)

        # DR-05: If any affected requirement is protected, flag manual approval
        any_protected = any(item.is_protected for item in self.impacted_requirements)
        if any_protected:
            self.has_protected_impact = True
            self.requires_manual_approval = True

        # Circular dependency validation
        if self.has_circular_dependency:
            if not self.circular_dependency_path:
                raise ValueError(
                    "circular_dependency_path must be provided when has_circular_dependency is True"
                )
            # A cycle is inherently unsafe to apply blindly
            self.safe_to_apply = False
        elif self.circular_dependency_path is not None:
            raise ValueError(
                "circular_dependency_path must be null when has_circular_dependency is False"
            )

        return self

    @property
    def is_blocking(self) -> bool:
        """Whether this report contains fatal violations preventing immediate save."""
        return not self.safe_to_apply or self.has_circular_dependency

    @property
    def direct_impacts(self) -> list[ImpactItem]:
        """Convenience accessor for direct (depth=1) impacts."""
        return [item for item in self.impacted_requirements if item.depth == 1]

    @property
    def transitive_impacts(self) -> list[ImpactItem]:
        """Convenience accessor for indirect (depth > 1) impacts."""
        return [item for item in self.impacted_requirements if item.depth > 1]
