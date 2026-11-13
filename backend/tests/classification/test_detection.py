"""Detection engine (Keval — US-05 tasks 5a–5c, US-07): per-category prompts, up to three re-asks,
per-pair status (G1), explanations with located evidence, and every labelled category stored."""

import csv
import json
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.classification.budget import BudgetExceededError, CountingBudget
from app.classification.explain import Subject, explain_pair, locate
from app.classification.llm_client import FakeTransport, LLMClient
from app.classification.prompting import (
    PROMPT_VERSION,
    build_pair_messages,
    build_single_messages,
    pattern_matches,
)
from app.classification.schemas import PairClassificationOutput, RequirementInput
from app.classification.tasks import classify_candidate_pair, classify_requirement
from app.models import (
    CandidatePair,
    ClassificationStatus,
    Finding,
    FindingCategory,
    Project,
    Requirement,
)

LABELS = Path(__file__).parents[3] / "eval" / "benchmark_v2" / "labels.csv"
A_TEXT = "API requests shall time out after 2 seconds."
B_TEXT = "API requests may take up to 10 seconds before they time out."


def pair_reply(category: str = "Conflicting", **extra: Any) -> str:
    body: dict[str, Any] = {
        "category": category,
        "confidence": 0.86,
        "rationale": "REQ-021 and REQ-023 give different timeouts for the same requests.",
        "dependency_direction": "A_depends_on_B" if category == "Dependent" else None,
        "evidence": ["time out after 2 seconds", "up to 10 seconds"],
    }
    body.update(extra)
    return json.dumps(body)


def single_reply(category: str, **extra: Any) -> str:
    body: dict[str, Any] = {
        "category": category,
        "confidence": 0.8,
        "rationale": "REQ-040 has a problem.",
        "vague_terms": ["fast"] if category == "Ambiguous" else [],
        "missing_information": ["the measurement period"] if category == "Incomplete" else [],
    }
    body.update(extra)
    return json.dumps(body)


@pytest.fixture
def pair(db_session: Session, make_requirement: Callable[..., Requirement]) -> CandidatePair:
    a = make_requirement(A_TEXT, source_req_id="REQ-021", section_heading="3.4 API")
    b = make_requirement(B_TEXT, source_req_id="REQ-023", section_heading="3.4 API")
    low, high = CandidatePair.ordered(a.id, b.id)
    candidate = CandidatePair(requirement_a_id=low, requirement_b_id=high, similarity_score=0.9)
    db_session.add(candidate)
    db_session.commit()
    return candidate


class TestPrompts:
    def test_the_pair_prompt_holds_the_three_pair_categories(self) -> None:
        system, _ = build_pair_messages(
            RequirementInput(id="A", text="x"), RequirementInput(id="B", text="y")
        )
        for heading in ("## Conflicting", "## Duplicate", "## Dependent"):
            assert heading in system
        assert "## Ambiguous" not in system
        assert PROMPT_VERSION == "v2"

    def test_the_single_prompt_holds_ambiguous_and_incomplete_with_pattern_hints(self) -> None:
        system, user = build_single_messages(
            RequirementInput(id="REQ-040", text="The app shall be fast and user-friendly.")
        )
        assert "## Ambiguous" in system and "## Incomplete" in system
        assert "## Conflicting" not in system
        assert "<pattern_matches>" in user and '"fast"' in user and '"user-friendly"' in user

    def test_no_pattern_block_without_a_match(self) -> None:
        _, user = build_single_messages(RequirementInput(id="R", text="Logs are kept for 7 years."))
        assert "<pattern_matches>" not in user

    def test_pattern_hints_are_escaped_like_requirement_text(self) -> None:
        assert pattern_matches("It shall be FAST.") == [("FAST", "Speed word without a number.")]


class TestPairs:
    def test_a_conflict_is_explained_with_located_evidence(
        self, db_session: Session, pair: CandidatePair, project: Project
    ) -> None:
        finding = classify_candidate_pair(
            db_session, pair.id, LLMClient(FakeTransport([pair_reply()]))
        )

        assert finding is not None
        assert finding.project_id == project.id and finding.prompt_version == "v2"
        assert "different timeouts" in (finding.explanation or "")
        quotes = {span["quote"] for span in finding.evidence_spans}
        assert quotes == {"time out after 2 seconds", "up to 10 seconds"}
        span = next(s for s in finding.evidence_spans if s["quote"] == "up to 10 seconds")
        requirement = db_session.get(Requirement, span["requirement_id"])
        assert requirement is not None
        assert requirement.body[span["start"] : span["end"]] == "up to 10 seconds"
        db_session.refresh(pair)
        assert pair.classification_status is ClassificationStatus.DONE
        assert (pair.a_version, pair.b_version, pair.attempts) == (1, 1, 1)

    def test_invalid_output_is_asked_again_up_to_three_times(
        self, db_session: Session, pair: CandidatePair
    ) -> None:
        transport = FakeTransport(["not json", "{}", '{"category": "Maybe"}', pair_reply()])

        finding = classify_candidate_pair(db_session, pair.id, LLMClient(transport))

        assert finding is not None and len(transport.calls) == 4
        assert "Your previous reply was not valid" in transport.calls[3][1]

    def test_a_pair_that_never_validates_is_recorded_as_failed_not_dropped(
        self, db_session: Session, pair: CandidatePair
    ) -> None:
        transport = FakeTransport(["nope"] * 4)

        assert classify_candidate_pair(db_session, pair.id, LLMClient(transport)) is None

        db_session.refresh(pair)
        assert pair.classification_status is ClassificationStatus.FAILED
        assert pair.last_error == "invalid_output"
        assert db_session.scalar(select(Finding.id)) is None

    def test_an_unchanged_pair_is_never_sent_twice(
        self, db_session: Session, pair: CandidatePair
    ) -> None:
        classify_candidate_pair(db_session, pair.id, LLMClient(FakeTransport([pair_reply("None")])))
        silent = FakeTransport([])  # any call would raise

        assert classify_candidate_pair(db_session, pair.id, LLMClient(silent)) is None
        assert silent.calls == []

    def test_an_exhausted_budget_leaves_the_pair_pending(
        self, db_session: Session, pair: CandidatePair
    ) -> None:
        with pytest.raises(BudgetExceededError):
            classify_candidate_pair(
                db_session, pair.id, LLMClient(FakeTransport([pair_reply()]), CountingBudget(0))
            )
        db_session.refresh(pair)
        assert pair.classification_status is ClassificationStatus.PENDING
        assert pair.last_error == "budget_exhausted"

    def test_a_dependency_explains_its_direction(self) -> None:
        output = PairClassificationOutput.model_validate_json(pair_reply("Dependent", evidence=[]))
        a = Subject(id=uuid.uuid4(), label="REQ-1", text="x")
        b = Subject(id=uuid.uuid4(), label="REQ-2", text="y")
        assert explain_pair(output, a, b).text.endswith("REQ-1 depends on REQ-2.")


class TestSingles:
    def test_ambiguous_names_and_highlights_the_vague_word(
        self, db_session: Session, make_requirement: Callable[..., Requirement]
    ) -> None:
        vague = make_requirement("The app shall be fast.", source_req_id="REQ-040")

        finding = classify_requirement(
            db_session, vague.id, LLMClient(FakeTransport([single_reply("Ambiguous")]))
        )

        assert finding is not None and finding.category is FindingCategory.AMBIGUOUS
        assert "Vague wording: “fast”." in (finding.explanation or "")
        (span,) = finding.evidence_spans
        assert vague.body[span["start"] : span["end"]] == "fast"

    def test_incomplete_states_what_is_missing(
        self, db_session: Session, make_requirement: Callable[..., Requirement]
    ) -> None:
        uptime = make_requirement(
            "The system shall maintain 99.9% uptime.", source_req_id="REQ-041"
        )
        finding = classify_requirement(
            db_session, uptime.id, LLMClient(FakeTransport([single_reply("Incomplete")]))
        )
        assert finding is not None
        assert "Missing: the measurement period." in (finding.explanation or "")

    def test_a_checked_version_is_not_checked_again_until_it_changes(
        self, db_session: Session, make_requirement: Callable[..., Requirement]
    ) -> None:
        clear = make_requirement("Logs are kept for 7 years.")
        classify_requirement(db_session, clear.id, LLMClient(FakeTransport([single_reply("None")])))
        assert classify_requirement(db_session, clear.id, LLMClient(FakeTransport([]))) is None

        clear.current_version = 2
        db_session.commit()
        transport = FakeTransport([single_reply("None")])
        classify_requirement(db_session, clear.id, LLMClient(transport))
        assert len(transport.calls) == 1


def _labelled_categories() -> list[str]:
    with LABELS.open(encoding="utf-8") as handle:
        return sorted({row["category"] for row in csv.DictReader(handle)})


@pytest.mark.skipif(not LABELS.exists(), reason="eval/ is not mounted")
@pytest.mark.parametrize("category", _labelled_categories() if LABELS.exists() else [])
def test_every_labelled_category_validates_and_is_stored(
    db_session: Session,
    make_requirement: Callable[..., Requirement],
    category: str,
) -> None:
    """Category tests on the labelled pairs (done-when of US-05): whatever the benchmark labels,
    the engine's JSON validates and the right kind of finding is stored."""
    a = make_requirement(A_TEXT, source_req_id="REQ-021")
    if category in ("Ambiguous", "Incomplete"):
        finding = classify_requirement(
            db_session, a.id, LLMClient(FakeTransport([single_reply(category)]))
        )
    else:
        b = make_requirement(B_TEXT, source_req_id="REQ-023")
        low, high = CandidatePair.ordered(a.id, b.id)
        candidate = CandidatePair(requirement_a_id=low, requirement_b_id=high, similarity_score=0.9)
        db_session.add(candidate)
        db_session.commit()
        finding = classify_candidate_pair(
            db_session, candidate.id, LLMClient(FakeTransport([pair_reply(category)]))
        )
    if category == "None":
        assert finding is None
    else:
        assert finding is not None and finding.category.value == category


def test_a_quote_that_is_not_in_the_text_is_never_highlighted() -> None:
    subject = Subject(id=uuid.uuid4(), label="R", text="Sessions end after 30 minutes.")
    assert locate("after  30\nminutes", [subject]) is not None  # spacing differences are fine
    assert locate("after 5 minutes", [subject]) is None
