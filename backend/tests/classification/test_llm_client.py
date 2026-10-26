"""LLMClient (Keval): validation with one re-ask, budget first, provider-independent."""

import json
import uuid

import pytest

from app.classification.budget import BudgetExceededError, CountingBudget
from app.classification.llm_client import FakeTransport, LLMClient, LLMOutputError
from app.classification.schemas import PairClassificationOutput

VALID = json.dumps(
    {
        "category": "Conflicting",
        "confidence": 0.86,
        "rationale": "REQ-031 and REQ-014 set different inactivity limits.",
        "dependency_direction": None,
        "evidence": ["5 minutes", "30 minutes"],
    }
)


def test_a_valid_reply_is_parsed_into_the_schema() -> None:
    client = LLMClient(FakeTransport([VALID]))

    output = client.complete_json("sys", "user", PairClassificationOutput)

    assert output.category == "Conflicting"
    assert output.confidence == 0.86


def test_a_reply_in_a_code_fence_is_accepted() -> None:
    client = LLMClient(FakeTransport([f"```json\n{VALID}\n```"]))
    assert client.complete_json("sys", "user", PairClassificationOutput).is_issue


def test_an_invalid_reply_is_asked_again_with_the_error() -> None:
    transport = FakeTransport(['{"category": "Conflicting"}', VALID])
    client = LLMClient(transport)

    output = client.complete_json("sys", "user", PairClassificationOutput)

    assert output.category == "Conflicting"
    assert len(transport.calls) == 2
    assert "not valid" in transport.calls[1][1]


def test_two_invalid_replies_raise_and_nothing_is_returned() -> None:
    client = LLMClient(FakeTransport(["not json", '{"category": "Bogus"}']))
    with pytest.raises(LLMOutputError):
        client.complete_json("sys", "user", PairClassificationOutput)


def test_every_call_goes_through_the_budget() -> None:
    project = uuid.uuid4()
    client = LLMClient(FakeTransport([VALID, VALID]), CountingBudget(allowance=1))

    client.complete_json("sys", "user", PairClassificationOutput, project_id=project)

    with pytest.raises(BudgetExceededError):
        client.complete_json("sys", "user", PairClassificationOutput, project_id=project)


def test_the_drafter_callable_returns_text() -> None:
    llm = LLMClient(FakeTransport(['{"purpose": "x"}'])).as_draft_llm()
    assert llm("system", "user") == '{"purpose": "x"}'


def test_without_an_api_key_there_is_no_client(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.classification import llm_client
    from app.core.config import get_settings

    monkeypatch.setenv("LLM_API_KEY", "")
    get_settings.cache_clear()
    llm_client.get_llm_client.cache_clear()
    try:
        assert llm_client.get_llm_client() is None
    finally:
        get_settings.cache_clear()
        llm_client.get_llm_client.cache_clear()
