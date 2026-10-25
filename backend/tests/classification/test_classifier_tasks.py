"""Classifier skeleton (Keval): a candidate pair becomes a finding with the context version,
"None" stores nothing, and a project in Setup is never sent to the LLM."""

import json
from collections.abc import Callable

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.classification.classifier import Classifier, as_input
from app.classification.llm_client import FakeTransport, LLMClient
from app.classification.schemas import RequirementInput
from app.classification.tasks import classify_candidate_pair
from app.core.errors import AppError
from app.models import (
    CandidatePair,
    Finding,
    FindingCategory,
    Project,
    ProjectContext,
    ProjectStatus,
    Requirement,
)


def _reply(category: str) -> str:
    return json.dumps(
        {
            "category": category,
            "confidence": 0.9,
            "rationale": "REQ-1 and REQ-2 disagree on the timeout.",
            "dependency_direction": None,
            "evidence": [],
        }
    )


@pytest.fixture
def pair(
    db_session: Session, make_requirement: Callable[..., Requirement], project: Project
) -> CandidatePair:
    db_session.add(
        ProjectContext(
            project_id=project.id,
            version=3,
            purpose="Banking",
            field_status={"purpose": "confirmed"},
            summary="Banking",
        )
    )
    project.context_version = 3
    first = make_requirement("Sessions end after 30 minutes.", source_req_id="REQ-1")
    second = make_requirement("Sessions end after 5 minutes.", source_req_id="REQ-2")
    a_id, b_id = CandidatePair.ordered(first.id, second.id)
    candidate = CandidatePair(requirement_a_id=a_id, requirement_b_id=b_id, similarity_score=0.9)
    db_session.add(candidate)
    db_session.commit()
    return candidate


def test_a_conflict_is_stored_with_the_context_version_and_raw_output(
    db_session: Session, pair: CandidatePair
) -> None:
    transport = FakeTransport([_reply("Conflicting")])

    finding = classify_candidate_pair(db_session, pair.id, LLMClient(transport))

    assert finding is not None
    assert finding.category is FindingCategory.CONFLICTING
    assert finding.context_version == 3
    assert finding.original_ai_output["category"] == "Conflicting"
    assert transport.calls[0][1].startswith('<project_context version="3">')


def test_no_issue_stores_nothing_and_a_second_run_does_not_duplicate(
    db_session: Session, pair: CandidatePair
) -> None:
    no_issue = LLMClient(FakeTransport([_reply("None")]))
    assert classify_candidate_pair(db_session, pair.id, no_issue) is None
    classify_candidate_pair(db_session, pair.id, LLMClient(FakeTransport([_reply("Duplicate")])))
    again = FakeTransport([_reply("Duplicate")])

    assert classify_candidate_pair(db_session, pair.id, LLMClient(again)) is None
    assert again.calls == []  # already classified: the model is not asked again
    assert len(db_session.scalars(select(Finding)).all()) == 1


def test_a_project_in_setup_is_refused_before_any_llm_call(
    db_session: Session, pair: CandidatePair, project: Project
) -> None:
    project.status = ProjectStatus.SETUP
    db_session.commit()
    transport = FakeTransport([_reply("Conflicting")])

    with pytest.raises(AppError) as refused:
        classify_candidate_pair(db_session, pair.id, LLMClient(transport))

    assert refused.value.status_code == 409
    assert transport.calls == []


def test_the_printed_id_is_what_the_model_sees(
    make_requirement: Callable[..., Requirement],
) -> None:
    with_id = make_requirement("x", source_req_id="FR-2.1b")
    without = make_requirement("y")
    assert as_input(with_id).id == "FR-2.1b"
    assert as_input(without).id.startswith("item-")


def test_single_requirement_classification_validates_the_details() -> None:
    reply = json.dumps(
        {
            "category": "Ambiguous",
            "confidence": 0.8,
            "rationale": "REQ-22 says quickly without a number.",
            "vague_terms": ["quickly"],
            "missing_information": [],
        }
    )
    classifier = Classifier(LLMClient(FakeTransport([reply])))

    output = classifier.classify_single(
        RequirementInput(id="REQ-22", text="The app shall load the summary quickly.")
    )

    assert output.vague_terms == ["quickly"]
