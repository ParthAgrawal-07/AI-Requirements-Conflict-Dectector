"""Tests for Change-Impact Analysis & Consequence Schemas (Role 4, Sprint 0)."""

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.consequences.schemas import (
    CheckResult,
    CheckStatus,
    CheckType,
    ImpactItem,
    ImpactReport,
    ImpactStatus,
    ImpactType,
)
from app.models.enums import Severity


def _sample_item(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "requirement_id": str(uuid.uuid4()),
        "source_req_id": "REQ-041",
        "body_preview": "The system shall complete batch transaction processing within 10 seconds.",
        "location": "Page 14, Section 3.2",
        "relationship_type": "conflict_partner",
        "status": "confirmed",
        "severity": "high",
        "reason": "Direct timing conflict flagged with source requirement.",
        "depth": 1,
        "is_protected": False,
    }
    data.update(overrides)
    return data


def _sample_check(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "check_name": "Circular Dependency Check",
        "check_type": "circular_dependency",
        "status": "passed",
        "severity": "high",
        "passed": True,
        "message": "No circular dependency paths detected in the dependency graph.",
        "details": None,
    }
    data.update(overrides)
    return data


def _sample_report(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "source_requirement_id": str(uuid.uuid4()),
        "source_req_id": "REQ-014",
        "source_version": 2,
        "proposed_body": "The system shall complete transaction processing within 3 seconds under peak load.",
        "analyzed_at": datetime.now(UTC).isoformat(),
        "total_impacted_count": 0,
        "critical_impacts_count": 0,
        "has_circular_dependency": False,
        "circular_dependency_path": None,
        "has_protected_impact": False,
        "requires_manual_approval": False,
        "safe_to_apply": True,
        "impacted_requirements": [],
        "checks": [],
    }
    data.update(overrides)
    return data


# ── ImpactItem Tests ─────────────────────────────────────────────────────────


def test_impact_item_valid_parsing() -> None:
    data = _sample_item()
    item = ImpactItem.model_validate(data)

    assert str(item.requirement_id) == data["requirement_id"]
    assert item.source_req_id == "REQ-041"
    assert item.relationship_type == ImpactType.CONFLICT_PARTNER
    assert item.status == ImpactStatus.CONFIRMED
    assert item.severity == Severity.HIGH
    assert item.depth == 1
    assert not item.is_protected


def test_impact_item_depth_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        ImpactItem.model_validate(_sample_item(depth=0))


def test_impact_item_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError, match="Extra inputs"):
        ImpactItem.model_validate(_sample_item(extra_unsupported_field="invalid"))


def test_impact_item_strips_whitespace() -> None:
    item = ImpactItem.model_validate(_sample_item(source_req_id="  REQ-041  "))
    assert item.source_req_id == "REQ-041"


# ── CheckResult Tests ────────────────────────────────────────────────────────


def test_check_result_valid_parsing() -> None:
    data = _sample_check()
    res = CheckResult.model_validate(data)

    assert res.check_name == "Circular Dependency Check"
    assert res.check_type == CheckType.CIRCULAR_DEPENDENCY
    assert res.status == CheckStatus.PASSED
    assert res.passed is True


def test_check_result_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError, match="Extra inputs"):
        CheckResult.model_validate(_sample_check(unexpected_data=123))


# ── ImpactReport Tests ───────────────────────────────────────────────────────


def test_impact_report_parses_empty_impacts() -> None:
    report = ImpactReport.model_validate(_sample_report())

    assert report.total_impacted_count == 0
    assert report.critical_impacts_count == 0
    assert report.safe_to_apply is True
    assert not report.is_blocking


def test_impact_report_reconciles_counts_from_items() -> None:
    item1 = _sample_item(severity="high", depth=1)
    item2 = _sample_item(severity="critical", depth=2)
    report = ImpactReport.model_validate(_sample_report(impacted_requirements=[item1, item2]))

    assert report.total_impacted_count == 2
    assert report.critical_impacts_count == 1
    assert len(report.direct_impacts) == 1
    assert len(report.transitive_impacts) == 1


def test_impact_report_enforces_protected_requirement_flag() -> None:
    """DR-05: Protected requirements must trigger manual approval and protected flags."""
    protected_item = _sample_item(is_protected=True, severity="critical")
    report = ImpactReport.model_validate(_sample_report(impacted_requirements=[protected_item]))

    assert report.has_protected_impact is True
    assert report.requires_manual_approval is True


def test_impact_report_circular_dependency_requires_path() -> None:
    with pytest.raises(ValidationError, match="circular_dependency_path must be provided"):
        ImpactReport.model_validate(
            _sample_report(has_circular_dependency=True, circular_dependency_path=None)
        )


def test_impact_report_rejects_path_when_no_circular_dependency() -> None:
    with pytest.raises(ValidationError, match="circular_dependency_path must be null"):
        ImpactReport.model_validate(
            _sample_report(
                has_circular_dependency=False, circular_dependency_path=["REQ-1", "REQ-2"]
            )
        )


def test_impact_report_marks_unsafe_on_circular_dependency() -> None:
    report = ImpactReport.model_validate(
        _sample_report(
            has_circular_dependency=True,
            circular_dependency_path=["REQ-014", "REQ-022", "REQ-014"],
            safe_to_apply=True,  # Validator should override to False
        )
    )

    assert report.safe_to_apply is False
    assert report.is_blocking is True


def test_impact_report_json_roundtrip() -> None:
    item = _sample_item()
    check = _sample_check()
    orig = ImpactReport.model_validate(_sample_report(impacted_requirements=[item], checks=[check]))

    json_str = orig.model_dump_json()
    restored = ImpactReport.model_validate_json(json_str)

    assert restored.source_requirement_id == orig.source_requirement_id
    assert restored.total_impacted_count == 1
    assert len(restored.checks) == 1
    assert restored.checks[0].check_name == "Circular Dependency Check"
