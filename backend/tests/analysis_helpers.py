"""Helpers for tests that drive an analysis run without Celery or a real LLM (Sprint 3).

* :func:`pair_reply` / :func:`single_reply` — valid classifier replies for ``FakeTransport``.
* :class:`Recorder` — stands in for ``dispatch``: records the tasks the orchestrator fans out.
* :func:`run_everything` — does what the workers would do with those tasks.
* :func:`make_post` — a posted requirement (origin ``post``, version 1 by its author), the way
  ``app.intake.posts`` stores one, without the channel message.
"""

import json
import uuid

from sqlalchemy.orm import Session

from app.classification.budget import BudgetExceededError
from app.classification.llm_client import LLMClient
from app.classification.tasks import classify_candidate_pair, classify_requirement
from app.models import (
    Project,
    Requirement,
    RequirementOrigin,
    RequirementState,
    RequirementVersion,
    User,
)
from app.services import analysis_orchestrator as orchestrator


def pair_reply(category: str = "Conflicting", confidence: float = 0.9) -> str:
    return json.dumps(
        {
            "category": category,
            "confidence": confidence,
            "rationale": "The two requirements set different timeouts.",
            "dependency_direction": None,
            "evidence": [],
        }
    )


def single_reply(category: str = "None", confidence: float = 0.9) -> str:
    vague = ["fast"] if category == "Ambiguous" else []
    missing = ["the time limit"] if category == "Incomplete" else []
    return json.dumps(
        {
            "category": category,
            "confidence": confidence,
            "rationale": "Clear." if category == "None" else "The wording leaves room to guess.",
            "vague_terms": vague,
            "missing_information": missing,
        }
    )


class Recorder:
    def __init__(self) -> None:
        self.sent: list[tuple[str, list[str]]] = []

    def __call__(self, name: str, args: list[str]) -> None:
        self.sent.append((name, args))

    def of(self, name: str) -> list[list[str]]:
        return [args for task, args in self.sent if task == name]


def run_everything(db: Session, recorder: Recorder, llm: LLMClient) -> None:
    """What the workers do with the fanned-out tasks (budget errors park the run, as in prod)."""
    for run_id, pair_id in recorder.of(orchestrator.CLASSIFY_PAIR):
        try:
            classify_candidate_pair(db, uuid.UUID(pair_id), llm, run_id=uuid.UUID(run_id))
        except BudgetExceededError:
            db.rollback()
        orchestrator.record(
            db, uuid.UUID(run_id), "pair", orchestrator.pair_outcome(db, uuid.UUID(pair_id))
        )
    for run_id, requirement_id in recorder.of(orchestrator.CHECK_REQUIREMENT):
        budget = False
        try:
            classify_requirement(db, uuid.UUID(requirement_id), llm, run_id=uuid.UUID(run_id))
        except BudgetExceededError:
            db.rollback()
            budget = True
        outcome = "budget" if budget else orchestrator.check_outcome(db, uuid.UUID(requirement_id))
        orchestrator.record(db, uuid.UUID(run_id), "check", outcome)


def make_post(
    db: Session,
    project: Project,
    author: User,
    body: str,
    *,
    label: str | None = None,
    state: RequirementState = RequirementState.PROPOSED,
) -> Requirement:
    requirement = Requirement(
        project_id=project.id,
        document_id=None,
        origin=RequirementOrigin.POST,
        owner_id=author.id,
        body=body,
        source_req_id=label,
        state=state,
    )
    db.add(requirement)
    db.flush()
    db.add(
        RequirementVersion(
            requirement_id=requirement.id, version_no=1, body_snapshot=body, changed_by=author.id
        )
    )
    db.commit()
    return requirement
