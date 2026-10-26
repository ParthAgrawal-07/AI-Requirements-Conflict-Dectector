"""Tests for the classification output schemas (Role 3)."""

import json
from pathlib import Path
from typing import get_args

import pytest
from pydantic import ValidationError

from app.classification.schemas import (
    PairCategory,
    PairClassificationOutput,
    RequirementInput,
    SingleCategory,
    SingleClassificationOutput,
)
from app.models.enums import FindingCategory


def _pair(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "category": "Conflicting",
        "confidence": 0.92,
        "rationale": "REQ-021 sets a 2 second timeout but REQ-023 allows 10 seconds.",
        "evidence": ["time out after 2 seconds", "up to 10 seconds"],
    }
    data.update(overrides)
    return data


def _single(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "category": "Ambiguous",
        "confidence": 0.85,
        "rationale": "REQ-007 says 'promptly' without a measurable response time.",
        "vague_terms": ["promptly"],
    }
    data.update(overrides)
    return data


# ── Pairwise output ──────────────────────────────────────────────────────────
def test_pair_output_parses_from_llm_json() -> None:
    out = PairClassificationOutput.model_validate_json(json.dumps(_pair()))

    assert out.category == "Conflicting"
    assert out.is_issue
    assert out.finding_category is FindingCategory.CONFLICTING


def test_pair_none_is_not_an_issue() -> None:
    out = PairClassificationOutput.model_validate(_pair(category="None", evidence=[]))

    assert not out.is_issue
    assert out.finding_category is None


def test_dependent_requires_direction() -> None:
    with pytest.raises(ValidationError, match="dependency_direction is required"):
        PairClassificationOutput.model_validate(_pair(category="Dependent"))

    out = PairClassificationOutput.model_validate(
        _pair(category="Dependent", dependency_direction="A_depends_on_B")
    )
    assert out.finding_category is FindingCategory.DEPENDENT


def test_direction_rejected_for_non_dependent() -> None:
    with pytest.raises(ValidationError, match="must be null"):
        PairClassificationOutput.model_validate(_pair(dependency_direction="B_depends_on_A"))


@pytest.mark.parametrize("category", ["Ambiguous", "Incomplete", "conflicting", "Conflict"])
def test_pair_rejects_categories_outside_pair_taxonomy(category: str) -> None:
    with pytest.raises(ValidationError):
        PairClassificationOutput.model_validate(_pair(category=category))


@pytest.mark.parametrize("confidence", [-0.1, 1.01, "high"])
def test_confidence_must_be_between_0_and_1(confidence: object) -> None:
    with pytest.raises(ValidationError):
        PairClassificationOutput.model_validate(_pair(confidence=confidence))


@pytest.mark.parametrize("rationale", ["", "   "])
def test_rationale_cannot_be_blank(rationale: str) -> None:
    with pytest.raises(ValidationError):
        PairClassificationOutput.model_validate(_pair(rationale=rationale))


def test_unexpected_fields_are_rejected() -> None:
    with pytest.raises(ValidationError, match="Extra inputs"):
        PairClassificationOutput.model_validate(_pair(severity="high"))


def test_missing_required_field_is_rejected() -> None:
    data = _pair()
    del data["confidence"]
    with pytest.raises(ValidationError):
        PairClassificationOutput.model_validate(data)


def test_evidence_is_capped_at_four_quotes() -> None:
    with pytest.raises(ValidationError):
        PairClassificationOutput.model_validate(_pair(evidence=["q"] * 5))


# ── Single-requirement output ────────────────────────────────────────────────
def test_single_output_parses_from_llm_json() -> None:
    out = SingleClassificationOutput.model_validate_json(json.dumps(_single()))

    assert out.finding_category is FindingCategory.AMBIGUOUS
    assert out.vague_terms == ["promptly"]


def test_ambiguous_requires_vague_terms() -> None:
    with pytest.raises(ValidationError, match="vague_terms"):
        SingleClassificationOutput.model_validate(_single(vague_terms=[]))


def test_incomplete_requires_missing_information() -> None:
    with pytest.raises(ValidationError, match="missing_information"):
        SingleClassificationOutput.model_validate(_single(category="Incomplete", vague_terms=[]))

    out = SingleClassificationOutput.model_validate(
        _single(category="Incomplete", vague_terms=[], missing_information=["measurement window"])
    )
    assert out.finding_category is FindingCategory.INCOMPLETE


def test_single_none_needs_no_details() -> None:
    out = SingleClassificationOutput.model_validate(_single(category="None", vague_terms=[]))

    assert out.finding_category is None


@pytest.mark.parametrize("category", ["Conflicting", "Duplicate", "Dependent"])
def test_single_rejects_pairwise_categories(category: str) -> None:
    with pytest.raises(ValidationError):
        SingleClassificationOutput.model_validate(_single(category=category))


# ── Input ────────────────────────────────────────────────────────────────────
def test_requirement_input_strips_and_requires_text() -> None:
    req = RequirementInput(id=" REQ-001 ", text=" The system shall log in users. ")
    assert (req.id, req.text) == ("REQ-001", "The system shall log in users.")

    with pytest.raises(ValidationError):
        RequirementInput(id="REQ-001", text="  ")


# ── Consistency with the rest of the project ─────────────────────────────────
def test_schema_categories_cover_the_finding_taxonomy_exactly() -> None:
    """Every FindingCategory is produced by exactly one of the two calls (ADR-02)."""
    pair_issues = set(get_args(PairCategory)) - {"None"}
    single_issues = set(get_args(SingleCategory)) - {"None"}

    assert pair_issues.isdisjoint(single_issues)
    assert pair_issues | single_issues == {c.value for c in FindingCategory}


def test_benchmark_labels_fit_the_schemas(sample_srs_path: Path) -> None:
    """The planted-conflict labels must be representable by the output we ask the LLM for."""
    labels_path = sample_srs_path.with_name("srs_v1_labels.json")
    labels = json.loads(labels_path.read_text(encoding="utf-8"))["labels"]

    for label in labels:
        allowed = get_args(PairCategory) if "r2" in label else get_args(SingleCategory)
        assert label["category"] in allowed, label
