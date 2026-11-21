"""Requirement attributes (Keval — US-58, FR-101): patterns first, the LLM only as a fallback."""

import json

import pytest

from app.classification.attributes import AttributeExtractor, extract_with_llm, stem
from app.classification.llm_client import FakeTransport, LLMClient

extract = AttributeExtractor().extract


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "The session shall expire after 30 minutes of inactivity.",
            {"entity": "session", "metric": "timeout", "value": 1800.0, "unit": "s",
             "comparison": "=", "modality": "shall"},
        ),
        (
            "The system shall lock the account after 5 failed login attempts.",
            {"actor": "system", "entity": "account", "action": "lock account",
             "metric": "lockout", "value": 5.0, "unit": "count"},
        ),
        (
            "The API shall respond within 2 seconds for 95% of requests.",
            {"metric": "response_time", "value": 2.0, "comparison": "<="},
        ),
        (
            "Passwords shall be at least 12 characters long.",
            {"entity": "password", "metric": "password_length", "value": 12.0, "unit": "chars",
             "comparison": ">="},
        ),
        (
            "Statements are kept for 7 years.",
            {"entity": "statement", "metric": "retention", "value": 7 * 31_536_000.0},
        ),
        (
            "The system shall not store card numbers.",
            {"negated": True, "modality": "shall_not", "entity": "card number"},
        ),
        (
            "When a payment fails, the system shall notify the customer within 2 minutes.",
            {"condition": "payment fail", "action": "notify customer", "value": 120.0},
        ),
        (
            "Only administrators shall approve refunds.",
            {"actor": "administrator", "action": "approv refund"},
        ),
    ],
)  # fmt: skip
def test_patterns(text: str, expected: dict[str, object]) -> None:
    attributes = extract(text).as_json()
    assert {key: attributes[key] for key in expected} == expected
    assert attributes["extractor"] == "rules"


def test_units_are_normalised_so_differently_written_limits_compare() -> None:
    assert (
        extract("Sessions shall end after 1 hour.").value
        == extract("Sessions shall end after 60 minutes.").value
    )


def test_a_trailing_scope_is_a_condition() -> None:
    assert extract("Sessions shall time out after 5 minutes on payment screens.").condition == (
        "payment screen"
    )


def test_unparsable_text_is_marked_for_the_fallback() -> None:
    assert not extract("Fast and pleasant.").parsed
    assert extract("The system shall log every login attempt.").parsed


def test_stems_match_inflections() -> None:
    assert stem("deleted") == stem("delete") and stem("logs") == stem("logged") == "log"


def test_the_llm_fallback_is_labelled() -> None:
    reply = json.dumps({"entity": "statement", "metric": "retention", "value": 5.0,
                        "unit": "count", "comparison": "=", "actor": None, "action": "purge",
                        "condition": None, "modality": "shall", "confidence": 0.6})  # fmt: skip
    attributes = extract_with_llm(
        "Purge statements after five years.", llm=LLMClient(FakeTransport([reply])), project_id=None
    )
    assert attributes is not None
    assert (attributes.extractor, attributes.confidence, attributes.metric) == (
        "llm",
        0.6,
        "retention",
    )


def test_the_llm_fallback_gives_up_quietly() -> None:
    llm = LLMClient(FakeTransport(["not json", "still not"]))
    assert extract_with_llm("Purge statements.", llm=llm, project_id=None) is None
