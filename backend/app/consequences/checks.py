"""Consequence checks of a change request (Madhav — US-34, FR-64, FR-98, FR-99; §3.2, §7.2).

**The probe.** The proposed text is classified — never stored — against the requirements it
touches: every *directly* affected requirement (``app.consequences.impact``) plus the nearest
neighbours of the proposed text by embedding, at most ``MAX_PROBES`` in all, and once on its own
for ambiguous or missing wording. It uses Keval's pure ``Classifier`` with the project's context
pack, so each comparison is one LLM call counted against the project's budget. Without a model,
over budget, or when a reply stays invalid, the comparison is recorded as not done and the delta
lists it under *must re-run*: a check never pretends to have run.

**The checks**, each ``pending`` (waiting for budget), ``pass``, ``warning``, ``fail`` or
``info`` (did not apply or could not run):

==================  ====================================================================
``stale``           the request was written against the requirement's current version
``protected``       a protected requirement is changed or affected: a compliance reviewer
``dependency``      requirements that depend on this one (fail for a deprecation)
``new_conflicts``   the new text conflicts with a requirement no open finding links it to
``duplicates``      the new text duplicates one
``wording``         the new text is ambiguous or incomplete
==================  ====================================================================

Messages name requirements by ID, never quote them.
"""

import logging
import uuid
from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy.orm import Session

from app.classification.budget import BudgetExceededError
from app.classification.classifier import Classifier
from app.classification.context_pack import ContextPackBuilder
from app.classification.llm_client import (
    LLMClient,
    LLMOutputError,
    LLMRefusedError,
    LLMUnavailableError,
)
from app.classification.schemas import RequirementInput
from app.consequences.impact import Impact, label
from app.embeddings.incremental import similar_to_text
from app.embeddings.model import Embedder
from app.models import ChangeRequest, Project, Requirement
from app.search.relations import RelationKind

logger = logging.getLogger(__name__)

MAX_PROBES = 8
SIMILAR_PROBES = 5
CheckStatus = Literal["pending", "pass", "warning", "fail", "info"]
ProbeState = Literal["done", "unavailable", "budget", "failed"]


@dataclass
class Outcome:
    """One comparison of the proposed text (with ``requirement_id``, or alone when None)."""

    requirement_id: uuid.UUID | None
    label: str | None
    state: ProbeState
    category: str | None = None  # "Conflicting"…, or None for no issue (or not done)
    confidence: float | None = None


@dataclass
class Probe:
    pairs: list[Outcome] = field(default_factory=list)
    single: Outcome | None = None
    llm_calls: int = 0

    def outcome_for(self, requirement_id: uuid.UUID) -> Outcome | None:
        return next((o for o in self.pairs if o.requirement_id == requirement_id), None)

    @property
    def incomplete(self) -> list[Outcome]:
        every = [*self.pairs, *([self.single] if self.single else [])]
        return [o for o in every if o.state != "done"]


@dataclass
class Check:
    key: str
    title: str
    status: CheckStatus
    message: str
    details: dict[str, object] = field(default_factory=dict)

    def as_json(self) -> dict[str, object]:
        return {
            "key": self.key,
            "title": self.title,
            "status": self.status,
            "message": self.message,
            "details": self.details,
        }


def _targets(
    db: Session, requirement: Requirement, text: str, impact: Impact, embedder: Embedder | None
) -> list[Requirement]:
    # Every directly affected requirement is probed (FR-99): the cap only limits how many
    # similarity hints are added on top, so a ninth direct target is never silently skipped.
    direct = [a.requirement_id for a in impact.direct]
    hints: list[uuid.UUID] = []
    if embedder is not None:
        for hint in similar_to_text(
            db, requirement.project_id, text, embedder, k=SIMILAR_PROBES, exclude={requirement.id}
        ):
            if hint.requirement_id not in direct and hint.requirement_id not in hints:
                hints.append(hint.requirement_id)
    ids = direct + hints[: max(0, MAX_PROBES - len(direct))]
    rows = {r.id: r for r in (db.get(Requirement, i) for i in ids) if r is not None}
    return [rows[i] for i in ids if i in rows and i != requirement.id]


def probe(
    db: Session,
    change_request: ChangeRequest,
    requirement: Requirement,
    impact: Impact,
    llm: LLMClient | None,
    embedder: Embedder | None,
) -> Probe:
    """Classify the proposed text against what it touches (see module doc). Stores nothing."""
    result = Probe()
    text = change_request.proposed_body
    if text is None:  # a deprecation writes nothing new
        return result
    targets = _targets(db, requirement, text, impact, embedder)
    if llm is None:
        result.pairs = [Outcome(t.id, label(t), "unavailable") for t in targets]
        result.single = Outcome(None, None, "unavailable")
        return result
    project = db.get(Project, requirement.project_id)
    if project is None:  # pragma: no cover
        return result
    pack = ContextPackBuilder(db).build(project, query_text=text)
    classifier = Classifier(llm)
    proposed = RequirementInput(id=label(requirement), text=text)
    out_of_budget = False
    for target in targets:
        if out_of_budget:
            result.pairs.append(Outcome(target.id, label(target), "budget"))
            continue
        try:
            output = classifier.classify_pair(
                proposed,
                RequirementInput(id=label(target), text=target.body),
                pack=pack,
                project_id=project.id,
            )
        except BudgetExceededError:
            out_of_budget = True
            result.pairs.append(Outcome(target.id, label(target), "budget"))
            continue
        except (LLMOutputError, LLMRefusedError, LLMUnavailableError) as error:
            # Unavailable too: the report is still saved, saying to re-run, instead of the task
            # dying with no report and the Checks tab waiting forever.
            logger.warning(
                "Probe of %s against %s failed: %s",
                change_request.id,
                target.id,
                type(error).__name__,
            )
            result.llm_calls += 1
            result.pairs.append(Outcome(target.id, label(target), "failed"))
            continue
        result.llm_calls += 1
        category = output.category if output.is_issue else None
        result.pairs.append(Outcome(target.id, label(target), "done", category, output.confidence))
    if out_of_budget:
        result.single = Outcome(None, None, "budget")
        return result
    try:
        single = classifier.classify_single(proposed, pack=pack, project_id=project.id)
        result.llm_calls += 1
        result.single = Outcome(
            None, None, "done", single.category if single.is_issue else None, single.confidence
        )
    except BudgetExceededError:
        result.single = Outcome(None, None, "budget")
    except (LLMOutputError, LLMRefusedError, LLMUnavailableError):
        result.llm_calls += 1
        result.single = Outcome(None, None, "failed")
    return result


def _not_run(outcomes: list[Outcome]) -> tuple[CheckStatus, str]:
    if any(o.state == "budget" for o in outcomes):
        return "pending", "Waiting for analysis budget; re-run the checks once it is back"
    if any(o.state == "unavailable" for o in outcomes):
        return "info", "No analysis model is configured, so this was not checked"
    return "info", "The analysis could not answer for some requirements; re-run the checks"


def _found(
    key: str,
    title: str,
    category: str,
    probe_result: Probe,
    already: set[uuid.UUID],
    found_status: CheckStatus,
    word: str,
    kind: str,
) -> Check:
    if kind == "deprecate":
        return Check(key, title, "info", "A deprecation writes no new text")
    hits = [
        o
        for o in probe_result.pairs
        if o.state == "done" and o.category == category and o.requirement_id not in already
    ]
    if hits:
        labels = [o.label or "?" for o in hits]
        return Check(
            key,
            title,
            found_status,
            f"The new text {word} {', '.join(labels)}",
            {"requirement_ids": [str(o.requirement_id) for o in hits], "labels": labels},
        )
    missing = [o for o in probe_result.pairs if o.state != "done"]
    if missing:
        status, message = _not_run(missing)
        return Check(key, title, status, message, {"labels": [o.label for o in missing]})
    checked = len(probe_result.pairs)
    return Check(
        key, title, "pass", f"None found among {checked} related requirement{'s' * (checked != 1)}"
    )


def run_checks(
    change_request: ChangeRequest,
    requirement: Requirement,
    impact: Impact,
    probe_result: Probe,
    *,
    open_partners: dict[str, set[uuid.UUID]],
) -> list[Check]:
    """``open_partners``: category → requirements that already have an open finding of that
    category with ``requirement`` (so they are not *new*)."""
    source = label(requirement)
    kind = change_request.kind
    checks: list[Check] = []

    if change_request.base_version == requirement.current_version:
        checks.append(
            Check(
                "stale",
                "Up to date",
                "pass",
                f"Written against {source} v{requirement.current_version}, its current version",
            )
        )
    else:
        checks.append(
            Check(
                "stale",
                "Up to date",
                "fail",
                f"{source} is at v{requirement.current_version} now; this request was written against v{change_request.base_version}: update it",
                {
                    "base_version": change_request.base_version,
                    "current_version": requirement.current_version,
                },
            )
        )

    protected = [a.label for a in impact.affected if a.is_protected]
    if requirement.is_protected:
        checks.append(
            Check(
                "protected",
                "Protected requirements",
                "warning",
                f"{source} is protected: a compliance reviewer must approve",
                {"labels": [source, *protected]},
            )
        )
    elif protected:
        checks.append(
            Check(
                "protected",
                "Protected requirements",
                "warning",
                f"Affects protected {', '.join(protected)}: a compliance reviewer should review",
                {"labels": protected},
            )
        )
    else:
        checks.append(
            Check(
                "protected",
                "Protected requirements",
                "pass",
                "No protected requirement is involved",
            )
        )

    dependants = [a.label for a in impact.direct if a.relation is RelationKind.REQUIRED_BY]
    if not dependants:
        checks.append(Check("dependency", "Dependencies", "pass", f"Nothing depends on {source}"))
    elif kind == "deprecate":
        checks.append(
            Check(
                "dependency",
                "Dependencies",
                "fail",
                f"{', '.join(dependants)} depend{'s' * (len(dependants) == 1)} on {source}: deprecating it breaks them",
                {"labels": dependants},
            )
        )
    else:
        checks.append(
            Check(
                "dependency",
                "Dependencies",
                "warning",
                f"{', '.join(dependants)} depend{'s' * (len(dependants) == 1)} on {source}: check they still hold",
                {"labels": dependants},
            )
        )

    checks.append(
        _found(
            "new_conflicts",
            "New conflicts",
            "Conflicting",
            probe_result,
            open_partners.get("Conflicting", set()),
            "fail",
            "conflicts with",
            kind,
        )
    )
    checks.append(
        _found(
            "duplicates",
            "Duplicates",
            "Duplicate",
            probe_result,
            open_partners.get("Duplicate", set()),
            "warning",
            "may duplicate",
            kind,
        )
    )

    single = probe_result.single
    if kind == "deprecate":
        checks.append(Check("wording", "Wording", "info", "A deprecation writes no new text"))
    elif single is None or single.state != "done":
        status, message = _not_run([single] if single else [])
        checks.append(Check("wording", "Wording", status, message))
    elif single.category is None:
        checks.append(Check("wording", "Wording", "pass", "The new text is specific and complete"))
    else:
        word = "ambiguous" if single.category == "Ambiguous" else "incomplete"
        checks.append(
            Check(
                "wording",
                "Wording",
                "warning",
                f"The new text looks {word}",
                {"category": single.category},
            )
        )
    return checks
