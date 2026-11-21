"""Pre-flight check (Keval — US-51, FR-93, NFR-34; design update §5, ``PreflightService``).

Before a member posts a requirement (or proposes a change), *Pre-flight check* runs the live
analysis in **dry-run mode**: what would it probably find? Nothing is stored — no finding, no
candidate pair, no run, no map change — so a draft can be checked as often as the member likes,
within two limits:

* every LLM call goes through the project's ``BudgetGuard`` like any other analysis call, and the
  answer carries what is left of the month's budget, which the composer shows;
* a dry run classifies at most ``PREFLIGHT_PAIRS`` neighbours plus the text on its own
  (``1 + PREFLIGHT_PAIRS`` calls), and the API rate-limits pre-flight checks per member.

The neighbours are chosen exactly as for a posted requirement: embedding similarity within the
project above its ``similarity_threshold``, Rejected and Deprecated excluded. The *likely
findings* are the classifier's answers, marked low-confidence below the project's
``confidence_threshold``; the composer draws them as edges of a ghost node on a mini-map.
"""

import logging
import uuid
from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy.orm import Session

from app.classification.budget import BudgetExceededError, BudgetGuard
from app.classification.classifier import Classifier
from app.classification.context_pack import ContextPackBuilder
from app.classification.llm_client import LLMClient, LLMOutputError, LLMRefusedError
from app.classification.schemas import RequirementInput
from app.embeddings.incremental import similar_to_text
from app.embeddings.model import Embedder
from app.lint.engine import LintResult, lint
from app.models import Project, Requirement

logger = logging.getLogger(__name__)

PREFLIGHT_PAIRS = 3
DRAFT_LABEL = "DRAFT"

Status = Literal["done", "partial", "budget", "unavailable"]


@dataclass(frozen=True)
class LikelyFinding:
    category: str
    requirement_id: uuid.UUID | None  # the existing requirement, or None for the draft alone
    label: str | None
    confidence: float
    rationale: str
    low_confidence: bool


@dataclass
class PreflightResult:
    status: Status
    lint: LintResult
    likely: list[LikelyFinding] = field(default_factory=list)
    compared: list[uuid.UUID] = field(default_factory=list)  # neighbours actually classified
    llm_calls: int = 0
    budget_remaining: int | None = None  # None: unlimited
    budget_monthly: int = 0


def _neighbours(
    db: Session,
    project: Project,
    text: str,
    embedder: Embedder,
    exclude: set[uuid.UUID],
) -> list[Requirement]:
    hints = similar_to_text(
        db,
        project.id,
        text,
        embedder,
        k=PREFLIGHT_PAIRS,
        min_similarity=project.similarity_threshold,
        exclude=exclude,
    )
    rows = (db.get(Requirement, hint.requirement_id) for hint in hints)
    return [row for row in rows if row is not None]


def dry_run(
    db: Session,
    project: Project,
    text: str,
    *,
    llm: LLMClient | None,
    embedder: Embedder,
    budget: BudgetGuard,
    exclude_requirement_id: uuid.UUID | None = None,
) -> PreflightResult:
    """Lint plus a dry-run classification of ``text`` (see the module doc). Stores nothing."""
    result = PreflightResult(
        status="done", lint=lint(text), budget_monthly=project.llm_budget_monthly_calls
    )
    exclude = {exclude_requirement_id} if exclude_requirement_id else set()
    neighbours = _neighbours(db, project, text, embedder, exclude)
    if llm is None:
        result.status = "unavailable"
        result.budget_remaining = budget.remaining(project.id)
        return result

    pack = ContextPackBuilder(db).build(project, query_text=text)
    classifier = Classifier(llm)
    draft = RequirementInput(id=DRAFT_LABEL, text=text)
    threshold = project.confidence_threshold
    before = llm.calls
    try:
        for other in neighbours:
            label = other.source_req_id or f"item-{str(other.id)[:8]}"
            try:
                pair = classifier.classify_pair(
                    draft,
                    RequirementInput(id=label, text=other.body),
                    pack=pack,
                    project_id=project.id,
                )
            except (LLMOutputError, LLMRefusedError) as error:
                logger.info("Pre-flight pair skipped: %s", type(error).__name__)
                result.status = "partial"
                continue
            result.compared.append(other.id)
            if pair.is_issue:
                result.likely.append(
                    LikelyFinding(
                        category=pair.category,
                        requirement_id=other.id,
                        label=label,
                        confidence=pair.confidence,
                        rationale=pair.rationale,
                        low_confidence=pair.confidence < threshold,
                    )
                )
        try:
            single = classifier.classify_single(draft, pack=pack, project_id=project.id)
            if single.is_issue:
                result.likely.append(
                    LikelyFinding(
                        category=single.category,
                        requirement_id=None,
                        label=None,
                        confidence=single.confidence,
                        rationale=single.rationale,
                        low_confidence=single.confidence < threshold,
                    )
                )
        except (LLMOutputError, LLMRefusedError):
            result.status = "partial"
    except BudgetExceededError:
        result.status = "budget"
    result.llm_calls = llm.calls - before
    result.likely.sort(key=lambda found: -found.confidence)
    result.budget_remaining = budget.remaining(project.id)
    return result
