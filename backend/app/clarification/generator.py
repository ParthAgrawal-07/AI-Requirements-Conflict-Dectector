"""Clarification questions (Madhav — US-09, FR-22, FR-23; ADR-06 human in the loop).

For every live **Conflicting, Ambiguous or Incomplete** finding the generator asks the model for
one question a stakeholder can answer and a QA engineer can resolve the finding from (FR-22).
Duplicate and Dependent findings are settled by a merge or link decision and get none.

A question is only stored when it is **specific**: it ends with a question mark, names at least
one of the requirements by ID, quotes the vague term of an Ambiguous finding, and is not one of
the generic stock questions ("Can you clarify this?", "Please provide more details."). A generic
or empty question counts as a failure: the model is asked again with the reason, up to
:data:`MAX_GENERIC_RETRIES` times, and nothing is stored if it still fails (US-09 AC).

Requirement text reaches the model only escaped inside ``<requirement>`` tags, with the project's
context pack (FR-105). The stored row keeps the prompt version and the model that answered
(ADR-31). Nothing here posts or notifies; ``app.clarification.tasks`` does.
"""

import html
import json
import logging
import re
import uuid
from collections.abc import Sequence
from functools import cache
from pathlib import Path
from string import Template

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.clarification.schemas import ClarificationOutput
from app.classification.classifier import as_input
from app.classification.context_pack import ContextPackBuilder
from app.classification.llm_client import LLMClient
from app.core.config import get_settings
from app.models import Clarification, Finding, FindingCategory, FindingStatus, Project
from app.services.review_state import involved_requirements

logger = logging.getLogger(__name__)

PROMPT_VERSION = "clarify-v1"
PROMPTS = Path(__file__).parent / "prompts"
QUESTION_CATEGORIES = frozenset(
    {FindingCategory.CONFLICTING, FindingCategory.AMBIGUOUS, FindingCategory.INCOMPLETE}
)
MAX_GENERIC_RETRIES = 2
_GENERIC = re.compile(
    r"\b(can|could|would) you (please )?(clarify|explain|elaborate)\b"
    r"|\bplease (clarify|elaborate|explain)\b"
    r"|\b(provide|give|share) (some |any )?(more|further|additional) "
    r"(detail|details|information|info|context)\b"
    r"|\bwhat (exactly )?(do|does) (you|this|it) mean\b"
    r"|\bis (this|the) requirement (correct|clear|right|complete)\b"
    r"|\bany (other )?(thoughts|comments|questions)\b",
    re.IGNORECASE,
)


class GenericQuestionError(ValueError):
    """The model's question is not specific enough to be useful (US-09)."""


def needs_question(finding: Finding) -> bool:
    return (
        finding.category in QUESTION_CATEGORIES
        and not finding.is_stale
        and finding.status not in (FindingStatus.DISMISSED, FindingStatus.MERGED)
    )


def check_specific(output: ClarificationOutput, labels: list[str], vague_terms: list[str]) -> None:
    """Raise :class:`GenericQuestionError` with the reason the question fails."""
    question = output.question.strip()
    if not question.endswith("?"):
        raise GenericQuestionError("it is not a question")
    if _GENERIC.search(question):
        raise GenericQuestionError("it is a generic question that fits any requirement")
    if not any(label in question for label in labels):
        raise GenericQuestionError(f"it does not name the requirements by ID ({', '.join(labels)})")
    if vague_terms and not any(term.lower() in question.lower() for term in vague_terms):
        raise GenericQuestionError(
            "it does not quote the vague wording (" + ", ".join(f'"{t}"' for t in vague_terms) + ")"
        )


def generate(db: Session, llm: LLMClient, finding: Finding) -> Clarification | None:
    """The finding's question: an existing one, a new specific one, or ``None`` when the finding
    needs none or the model kept giving generic questions. LLM errors propagate (the task
    decides: retry later, skip, or stop for budget)."""
    if not needs_question(finding):
        return None
    existing = db.scalar(select(Clarification).where(Clarification.finding_id == finding.id))
    if existing is not None:
        return existing
    requirements = involved_requirements(db, finding)
    project = db.get(Project, finding.project_id)
    if not requirements or project is None:
        return None
    output_data = finding.original_ai_output or {}
    vague = [str(t) for t in output_data.get("vague_terms") or []]
    missing = [str(t) for t in output_data.get("missing_information") or []]
    vector = next((r.embedding.vector for r in requirements if r.embedding is not None), None)
    pack = ContextPackBuilder(db).build(
        project, query_text="\n".join(r.body for r in requirements), query_vector=vector
    )
    subjects = [(as_input(r).id, r.body) for r in requirements]
    system, user = render_messages(
        finding.category,
        finding.explanation or finding.rationale,
        subjects,
        context_pack=pack.text,
        vague_terms=vague,
        missing=missing,
    )
    output = ask(llm, system, user, [label for label, _ in subjects], vague, project_id=project.id)
    if output is None:
        logger.info("No specific clarification for finding %s", finding.id)
        return None

    clarification = Clarification(
        finding_id=finding.id,
        question=output.question.strip(),
        addressed_to=output.addressed_to,
        prompt_version=PROMPT_VERSION,
        llm_model=llm.model,
    )
    try:
        with db.begin_nested():
            db.add(clarification)
            db.flush()
    except IntegrityError:  # another delivery of the task stored one first
        return db.scalar(select(Clarification).where(Clarification.finding_id == finding.id))
    db.commit()
    return clarification


def ask(
    llm: LLMClient,
    system: str,
    user: str,
    labels: list[str],
    vague_terms: list[str],
    *,
    project_id: uuid.UUID | None = None,
) -> ClarificationOutput | None:
    """Ask until the question is specific; ``None`` after :data:`MAX_GENERIC_RETRIES` re-asks.
    No database: the benchmark runner calls it too."""
    prompt = user
    for attempt in range(MAX_GENERIC_RETRIES + 1):
        output = llm.complete_json(
            system,
            prompt,
            ClarificationOutput,
            project_id=project_id,
            retries=get_settings().llm_output_retries,
        )
        try:
            check_specific(output, labels, vague_terms)
            return output
        except GenericQuestionError as reason:
            if attempt == MAX_GENERIC_RETRIES:
                return None
            prompt = (
                f"{user}\n\nYour previous question was rejected because {reason}. Ask one "
                "specific question that names the requirement IDs."
            )
    return None


def render_messages(
    category: FindingCategory,
    explanation: str,
    subjects: list[tuple[str, str]],
    *,
    context_pack: str = "",
    vague_terms: Sequence[str] = (),
    missing: Sequence[str] = (),
) -> tuple[str, str]:
    """``(system, user)`` for one finding. ``subjects`` are ``(ID, text)`` pairs; requirement text
    and the explanation are escaped into data sections."""
    details = ""
    if vague_terms:
        details = "Vague wording: " + ", ".join(f'"{_data(t)}"' for t in vague_terms) + "\n"
    if missing:
        details += "Missing information: " + "; ".join(_data(m) for m in missing) + "\n"
    blocks = "\n".join(
        f'<requirement id="{_data(label)}">{_data(text)}</requirement>' for label, text in subjects
    )
    schema = json.dumps(ClarificationOutput.model_json_schema(), indent=2)
    system = _template("system").substitute(output_schema=schema)
    user = _template("user").substitute(
        # The pack is escaped by ContextPackBuilder; a blank line separates it from the task.
        context_pack=f"{context_pack}\n\n" if context_pack else "",
        category=category.value,
        explanation=_data(explanation),
        details=details,
        requirements=blocks,
    )
    return system, user


def _data(value: str) -> str:
    """Escape text so it cannot close the tag it sits in (prompt injection)."""
    return html.escape(value, quote=True)


@cache
def _template(part: str) -> Template:
    return Template((PROMPTS / f"clarify_v1_{part}.md").read_text(encoding="utf-8"))
