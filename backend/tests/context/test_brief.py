"""The project brief schema (Sprint 0 contract, FR-103)."""

import pytest
from pydantic import ValidationError

from app.context.brief import (
    REQUIRED_FIELDS,
    BriefField,
    BriefValues,
    FieldStatus,
    is_filled,
    labels,
    missing_required,
)

FULL = BriefValues(
    purpose="Mobile banking for retail customers.",
    scope_in="Accounts, transfers, bill pay.",
    scope_out="Loans and trading.",
    actors=["Customer", "Support agent"],
    environment="Android 10+, iOS 15+; retail banking.",
)
ALL_CONFIRMED = {field.value: FieldStatus.CONFIRMED for field in REQUIRED_FIELDS}


def test_the_four_required_fields_match_the_spec() -> None:
    assert REQUIRED_FIELDS == (
        BriefField.PURPOSE,
        BriefField.SCOPE,
        BriefField.ACTORS,
        BriefField.ENVIRONMENT,
    )


def test_a_full_confirmed_brief_misses_nothing() -> None:
    assert missing_required(FULL, ALL_CONFIRMED) == []


def test_scope_needs_both_in_and_out() -> None:
    half = FULL.model_copy(update={"scope_out": None})
    assert not is_filled(BriefField.SCOPE, half)
    assert missing_required(half, ALL_CONFIRMED) == [BriefField.SCOPE]


def test_ai_drafted_fields_are_still_missing_until_confirmed() -> None:
    status = {**ALL_CONFIRMED, "actors": FieldStatus.AI_DRAFTED}
    assert labels(missing_required(FULL, status)) == ["User classes and actors"]


def test_blank_text_counts_as_empty_and_actors_are_cleaned() -> None:
    values = BriefValues(purpose="   ", actors=["  Customer ", "customer", "", "Fraud  analyst"])
    assert values.purpose is None
    assert values.actors == ["Customer", "Fraud analyst"]


@pytest.mark.parametrize(
    "data",
    [
        {"unknown": "x"},
        {"purpose": "x" * 4001},
        {"glossary": [{"term": "", "meaning": "m"}]},
        {"references": [{"title": "Spec", "url": "ftp://example.com"}]},
        {"actors": ["x" * 121]},
    ],
)
def test_invalid_brief_values_are_rejected(data: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        BriefValues.model_validate(data)
