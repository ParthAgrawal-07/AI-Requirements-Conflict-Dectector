"""The AI paragraph of a change summary cites only listed events (Keval — US-55, FR-96)."""

import html
import json
import uuid
from datetime import UTC, datetime

from app.classification.budget import CountingBudget
from app.classification.change_summary import SummaryParagraph, problems, write
from app.classification.llm_client import FakeTransport, LLMClient
from app.graph.changelog import Event, Summary

PROJECT = uuid.uuid4()


def summary() -> Summary:
    now = datetime.now(UTC)
    highlights = [
        Event(uuid.uuid4(), now, 7, "merged", "Arjun merged RCR-3: REQ-014 is now v2.", None,
              "Arjun", [], [], False),
        Event(uuid.uuid4(), now, 6, "conflict_found",
              "Analysis of REQ-031: 1 conflict with REQ-014 (high).", None, None, [], [], False),
    ]  # fmt: skip
    counts = {"requirements_added": 2, "conflicts_opened": 1, "change_requests_merged": 1,
              "requirements_changed": 1, "requirements_deprecated": 0, "conflicts_resolved": 0}  # fmt: skip
    return Summary(
        since=None,
        until=now,
        since_label="v1.0",
        counts=counts,
        highlights=highlights,
        total_events=5,
        keys=["RCR-3", "REQ-014", "REQ-031"],
    )


def reply(paragraph: str, cited: list[str] | None = None) -> str:
    return json.dumps({"paragraph": paragraph, "cited_keys": cited or []})


GOOD = (
    "Since v1.0, two requirements were added and RCR-3 was merged, giving REQ-014 a new version. "
    "Analysis of REQ-031 found 1 conflict with REQ-014."
)


def test_a_faithful_paragraph_is_kept_and_labelled_with_its_model() -> None:
    llm = LLMClient(FakeTransport([reply(GOOD, ["RCR-3"])], label="gemini/gemini-2.5-flash"))
    narrative = write(summary(), llm=llm, project_id=PROJECT)
    assert narrative is not None
    assert narrative.text == GOOD
    assert narrative.cited_keys == ["RCR-3", "REQ-014", "REQ-031"]
    assert (narrative.provider, narrative.model) == ("gemini", "gemini-2.5-flash")


def test_the_prompt_carries_only_the_computed_data() -> None:
    transport = FakeTransport([reply(GOOD)])
    write(summary(), llm=LLMClient(transport), project_id=PROJECT)
    ((_, escaped),) = transport.calls
    user = html.unescape(escaped)  # the data block is escaped against prompt injection
    assert "Arjun merged RCR-3" in user and '"requirements_added": 2' in user
    assert '"requirements_deprecated"' not in user  # zero counts are left out


def test_a_paragraph_naming_an_unlisted_key_or_number_is_asked_again() -> None:
    bad = reply("RCR-9 was merged and 4 conflicts were resolved.")
    transport = FakeTransport([bad, reply(GOOD)])
    narrative = write(summary(), llm=LLMClient(transport), project_id=PROJECT)
    assert narrative is not None and narrative.text == GOOD
    assert "RCR-9" in transport.calls[1][1] and "4" in transport.calls[1][1]


def test_no_paragraph_when_the_model_keeps_inventing_or_is_over_budget() -> None:
    bad = reply("ISS-40 was opened.")
    assert write(summary(), llm=LLMClient(FakeTransport([bad, bad])), project_id=PROJECT) is None
    broke = LLMClient(FakeTransport([reply(GOOD)]), CountingBudget(0))
    assert write(summary(), llm=broke, project_id=PROJECT) is None


def test_problems_lists_every_unsupported_claim() -> None:
    output = SummaryParagraph(paragraph="REQ-099 changed 3 times.", cited_keys=["ISS-1"])
    found = problems(output, summary())
    assert any("ISS-1" in p and "REQ-099" in p for p in found)
    assert any("3" in p for p in found)
    assert problems(SummaryParagraph(paragraph=GOOD), summary()) == []
