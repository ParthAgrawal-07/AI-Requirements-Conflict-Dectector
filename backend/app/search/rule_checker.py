"""Rule-based cross-checks (Heet — US-58, FR-101, NFR-37, DR-21; ADR-27; design update §11.5).

The embedding filter only sends *similar-sounding* pairs to the AI, so two requirements that
contradict each other in different words ("Statements are kept for 7 years" / "Statements are
deleted after 5 years") may never be compared. These checks close that gap deterministically:

1. **Attribute index.** Every requirement version is read into ``requirement_attributes``
   (Keval's ``AttributeExtractor``: patterns first; the LLM only for text the patterns cannot
   parse, when a model is configured, recorded as ``extractor = llm``).
2. **Checks.** A requirement is compared with every live requirement of its project that shares
   its entity, metric or action — **whatever their embedding similarity**:

   =====================  ==============================================================
   ``numeric_limit``      the same subject ("API" and "API responses" are one) and metric
                          under the same condition, with two different limits (5 vs 30
                          minutes; a minimum above a maximum) — a valid range is not one
   ``negation``           the same action, "shall" in one and "shall not" in the other,
                          where the conditions overlap
   ``actor``              the same action given to different actors, where one says it is
                          *only* theirs
   ``condition_overlap``  the same condition and the same object, with different responses
   ``unbounded``          a finite limit in one ("expire after 5 minutes", "at most 3 concurrent
                          sessions", "deleted after 3 years") and *no* limit for the same
                          measure in the other ("until the user logs out", "any number of
                          devices at the same time", "kept indefinitely") — Sprint 6
   =====================  ==============================================================

   Sprint 6 recall tuning (CP2 misses, dev split only): frequency words ("hourly", "nightly",
   "every day") are read as a period before extraction, and the unbounded side of a pair is
   indexed under the measure it leaves open, so the two are compared at all.

3. **Findings.** Each hit is a Conflicting finding with ``source = rule``, the ``rule_id`` and a
   rationale built from the attributes (IDs and values, never invented text). It enters the same
   review workflow as AI findings (ADR-25) and opens an auto issue between two owners like any
   other. The AI may later classify the pair too; its answer never removes a rule finding.

Runs after every analysis run (``analysis.after_run``), so it also runs when no LLM is
configured, on a merged change (a new version) and on a posted requirement.
"""

import logging
import math
import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, replace
from typing import Any

from sqlalchemy import Select, func, or_, select, true
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from app.classification.attributes import (
    GENERIC_ACTORS,
    AttributeExtractor,
    Attributes,
    extract_with_llm,
)
from app.classification.budget import BudgetExceededError
from app.classification.llm_client import LLMClient
from app.models import (
    AnalysisRun,
    AnalysisScope,
    CandidatePair,
    Embedding,
    Finding,
    FindingCategory,
    Requirement,
    RequirementAttribute,
    RequirementState,
    Severity,
)

logger = logging.getLogger(__name__)

RULES: dict[str, str] = {
    "numeric_limit": "Different limits for the same measure",
    "negation": '"Shall" and "shall not" for the same action',
    "actor": "The same action given to different actors",
    "condition_overlap": "The same condition with different responses",
    "unbounded": "A limit in one requirement, no limit in the other",
}
CONFIDENCE = {
    "numeric_limit": 0.8,
    "negation": 0.75,
    "actor": 0.65,
    "condition_overlap": 0.55,
    "unbounded": 0.7,
}
SEVERITY = {
    "numeric_limit": Severity.MEDIUM,
    "negation": Severity.MEDIUM,
    "actor": Severity.MEDIUM,
    "condition_overlap": Severity.LOW,
    "unbounded": Severity.MEDIUM,
}
NOT_CHECKED = (RequirementState.REJECTED, RequirementState.DEPRECATED)
_EXCLUSIVE = re.compile(r"\b(only|solely|exclusively)\b", re.IGNORECASE)
# "No limit" for a measure, as people write it (Sprint 6, from the CP2 misses).
_UNBOUNDED: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "timeout",
        re.compile(
            r"\buntil (?:the |a )?(?:user|they|he|she|someone)?\s*(?:explicitly |manually )?"
            r"(?:logs?|signs?) (?:out|off)\b|\bnever (?:expires?|times? out)\b|"
            r"\bno (?:session )?time ?out\b",
            re.IGNORECASE,
        ),
    ),
    (
        "retention",
        re.compile(
            r"\b(?:kept|retained|stored|keep|retain|store) (?:indefinitely|forever|permanently)\b|"
            r"\bnever (?:be )?(?:deleted|purged|removed)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "concurrency",
        re.compile(
            r"\b(?:any number of|an unlimited number of|unlimited)\b[^.]*?"
            r"\b(?:at the same time|at once|simultaneous(?:ly)?|concurrent(?:ly)?)\b|"
            r"\b(?:any number of|unlimited) (?:concurrent|simultaneous)\b",
            re.IGNORECASE,
        ),
    ),
)
# Nouns that make two differently worded subjects one ("each user" / "sessions per user").
_SUBJECT_NOUNS = frozenset(
    {"session", "user", "account", "record", "report", "file", "upload", "password", "log",
     "backup", "message", "order", "payment", "token", "device"}
)  # fmt: skip
_FREQUENCY: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(pattern, re.IGNORECASE), replacement)
    for pattern, replacement in (
        (r"\bhourly\b", "every 1 hour"),
        (r"\b(?:nightly|daily|every night|once a day)\b", "every 1 day"),
        (r"\bweekly\b", "every 1 week"),
        (r"\bmonthly\b", "every 1 month"),
        (r"\b(?:yearly|annually)\b", "every 1 year"),
        (r"\bevery (minute|hour|day|week|month|year)\b", r"every 1 \1"),
    )
)
_TIME_UNITS = (
    (31_536_000, "year"),
    (2_592_000, "month"),
    (604_800, "week"),
    (86_400, "day"),
    (3600, "hour"),
    (60, "minute"),
    (1, "second"),
)


@dataclass(frozen=True)
class Hit:
    rule_id: str
    rationale: str


def label(requirement: Requirement) -> str:
    return requirement.source_req_id or f"requirement {str(requirement.id)[:8]}"


def human(value: float, unit: str | None, comparison: str | None = "=") -> str:
    """``1800, "s"`` → "30 minutes"; with ``<=`` → "at most 30 minutes"."""
    prefix = {"<=": "at most ", ">=": "at least "}.get(comparison or "=", "")
    if unit == "s":
        if value < 1:
            return f"{prefix}{value * 1000:g} ms"
        for size, name in _TIME_UNITS:
            if value >= size and math.isclose(value / size, round(value / size), abs_tol=0.01):
                count = round(value / size)
                return f"{prefix}{count} {name}{'s' * (count != 1)}"
        return f"{prefix}{value:g} seconds"
    if unit == "B":
        for scale, name in ((1e12, "TB"), (1e9, "GB"), (1e6, "MB"), (1e3, "KB")):
            if value >= scale:
                return f"{prefix}{value / scale:g} {name}"
        return f"{prefix}{value:g} bytes"
    if unit == "%":
        return f"{prefix}{value:g}%"
    if unit == "chars":
        return f"{prefix}{value:g} characters"
    return f"{prefix}{value:g}"


def incompatible(a: RequirementAttribute, b: RequirementAttribute) -> bool:
    """Can both limits hold at once? Only a minimum and a maximum can (a range, when the minimum
    is not above the maximum); two different values of any other kind are two limits."""
    if a.value is None or b.value is None:
        return False
    pair = (a.comparison or "=", b.comparison or "=")
    if pair == (">=", "<="):
        return a.value > b.value
    if pair == ("<=", ">="):
        return b.value > a.value
    return not math.isclose(a.value, b.value)


def unbounded(text: str) -> tuple[str, str] | None:
    """The measure a requirement leaves without a limit, and the words that say so."""
    for metric, pattern in _UNBOUNDED:
        found = pattern.search(text)
        if found:
            return metric, found.group(0)
    return None


def with_frequencies(text: str) -> str:
    """ "refreshed hourly" → "refreshed every 1 hour", so the period can be compared."""
    for pattern, replacement in _FREQUENCY:
        text = pattern.sub(replacement, text)
    return text


def _nouns(text: str) -> set[str]:
    words = {w.rstrip("s") for w in re.findall(r"[a-z]+", text.lower())}
    return words & _SUBJECT_NOUNS


def base_metric(metric: str | None) -> str | None:
    return metric.split(":")[0] if metric else None


def same_subject(a: RequirementAttribute, b: RequirementAttribute) -> bool:
    """ "API" and "API responses" are one subject; "admin sessions" and "guest sessions" are two."""
    if a.entity is None or b.entity is None:
        return False
    first, second = set(a.entity.split()), set(b.entity.split())
    return first <= second or second <= first


def _conditions_overlap(a: RequirementAttribute, b: RequirementAttribute) -> bool:
    """No condition means "always", which overlaps every condition."""
    return a.condition is None or b.condition is None or a.condition == b.condition


def compare(
    a: RequirementAttribute, b: RequirementAttribute, *, a_req: Requirement, b_req: Requirement
) -> list[Hit]:
    hits: list[Hit] = []
    first, second = label(a_req), label(b_req)
    about = f" for {a.entity}" if a.entity else ""
    if (
        a.metric is not None
        and a.metric == b.metric
        and a.value is not None
        and b.value is not None
        and a.unit == b.unit
        and a.condition == b.condition
        and same_subject(a, b)
        and incompatible(a, b)
    ):
        measure = a.metric.split(":")[0].replace("_", " ")
        where = f" when {a.condition}" if a.condition else ""
        hits.append(
            Hit(
                "numeric_limit",
                f"{first} sets the {measure}{about} to {human(a.value, a.unit, a.comparison)}; "
                f"{second} sets it to {human(b.value, b.unit, b.comparison)}{where}. "
                "Both cannot hold.",
            )
        )
    if (
        a.action is not None
        and a.action == b.action
        and a.negated != b.negated
        and a.entity == b.entity
        and _conditions_overlap(a, b)
    ):
        yes, no = (second, first) if a.negated else (first, second)
        hits.append(
            Hit(
                "negation",
                f"{yes} requires an action{about} that {no} forbids (one says shall, the other "
                "shall not), and their conditions overlap.",
            )
        )
    if (
        a.action is not None
        and a.action == b.action
        and not (a.negated or b.negated)
        and a.actor
        and b.actor
        and a.actor != b.actor
        and a.actor.split()[-1] not in GENERIC_ACTORS
        and b.actor.split()[-1] not in GENERIC_ACTORS
        and (_EXCLUSIVE.search(a_req.body) or _EXCLUSIVE.search(b_req.body))
        and _conditions_overlap(a, b)
    ):
        hits.append(
            Hit(
                "actor",
                f"{first} gives the same action{about} to {a.actor}; {second} gives it to "
                f"{b.actor}, and one of them says it is theirs only.",
            )
        )
    if (
        a.condition is not None
        and a.condition == b.condition
        and a.entity is not None
        and a.entity == b.entity
        and a.action
        and b.action
        and a.action.split()[0] != b.action.split()[0]
        and not (a.negated or b.negated)
    ):
        hits.append(
            Hit(
                "condition_overlap",
                f"When {a.condition}, {first} and {second} respond differently{about}: check "
                "that both responses are meant.",
            )
        )
    hits.extend(_unbounded_hits(a, b, a_req=a_req, b_req=b_req))
    return hits


def _unbounded_hits(
    a: RequirementAttribute, b: RequirementAttribute, *, a_req: Requirement, b_req: Requirement
) -> list[Hit]:
    """A finite limit on one side, "no limit" for the same measure on the other."""
    for finite, open_, finite_req, open_req in ((a, b, a_req, b_req), (b, a, b_req, a_req)):
        if finite.value is None or (finite.comparison or "=") not in ("<=", "="):
            continue
        if open_.value is not None:
            continue
        found = unbounded(open_req.body)
        if found is None or found[0] != base_metric(finite.metric):
            continue
        if not (same_subject(finite, open_) or _nouns(finite_req.body) & _nouns(open_req.body)):
            continue
        measure = found[0].replace("_", " ")
        about = f" for {finite.entity}" if finite.entity else ""
        return [
            Hit(
                "unbounded",
                f"{label(finite_req)} sets the {measure}{about} to "
                f"{human(finite.value, finite.unit, finite.comparison)}; {label(open_req)} sets "
                f'no limit ("{found[1]}"). Both cannot hold.',
            )
        ]
    return []


def read_attributes(text: str) -> Attributes:
    """The patterns' reading of a requirement, as the checker indexes it: frequency words as
    periods, and a requirement that leaves a measure open indexed under that measure (Sprint 6).
    Pure — the evaluation (``eval/recall_by_layer.py``) uses it too, so the two never drift."""
    attributes = AttributeExtractor().extract(with_frequencies(text))
    if attributes.metric is None:  # "until the user logs out": index it under what it leaves open
        found = unbounded(text)
        if found is not None:
            attributes = replace(attributes, metric=found[0])
    return attributes


def index_requirement(
    db: Session, requirement: Requirement, *, llm: LLMClient | None = None
) -> RequirementAttribute:
    """The attributes of the requirement's current version, read once and stored. Two runs over
    the same version (a re-analysis while an upload is analysed) share one row: the second waits
    for the first's and reuses it."""
    query = select(RequirementAttribute).where(
        RequirementAttribute.requirement_id == requirement.id,
        RequirementAttribute.version_no == requirement.current_version,
    )
    row = db.scalar(query)
    if row is not None:
        return row
    attributes = read_attributes(requirement.body)
    if not attributes.parsed and llm is not None:
        try:
            attributes = (
                extract_with_llm(requirement.body, llm=llm, project_id=requirement.project_id)
                or attributes
            )
        except BudgetExceededError:
            logger.info("No LLM attributes for %s: budget exhausted", requirement.id)
    db.execute(
        insert(RequirementAttribute)
        .values(
            id=uuid.uuid4(),
            requirement_id=requirement.id,
            project_id=requirement.project_id,
            version_no=requirement.current_version,
            entity=(attributes.entity or None) and attributes.entity[:120],
            metric=attributes.metric,
            value=attributes.value,
            unit=attributes.unit,
            comparison=attributes.comparison,
            actor=(attributes.actor or None) and attributes.actor[:120],
            action=(attributes.action or None) and attributes.action[:120],
            condition=(attributes.condition or None) and attributes.condition[:200],
            negated=attributes.negated,
            modality=attributes.modality,
            extractor=attributes.extractor,
            confidence=min(1.0, max(0.0, attributes.confidence)),
        )
        .on_conflict_do_nothing(index_elements=["requirement_id", "version_no"])
    )
    return db.scalars(query).one()


def _similarity(db: Session, a: uuid.UUID, b: uuid.UUID) -> float:
    first, second = aliased(Embedding), aliased(Embedding)
    value = db.scalar(
        select(1 - first.vector.cosine_distance(second.vector))
        .select_from(first)
        .join(second, true())
        .where(first.requirement_id == a, second.requirement_id == b)
    )
    return 0.0 if value is None else max(-1.0, min(1.0, float(value)))


def _pair(db: Session, a: Requirement, b: Requirement) -> CandidatePair:
    """The pair, created when the embedding filter never proposed it (left ``pending``: the AI
    has not classified it, and may be asked to). Two runs checking the same pair at once both
    find it missing; the second waits for the first's row and reuses it, instead of failing and
    losing every finding of its run (found by the CP2 load test)."""
    first, second = CandidatePair.ordered(a.id, b.id)
    query = select(CandidatePair).where(
        CandidatePair.requirement_a_id == first, CandidatePair.requirement_b_id == second
    )
    pair = db.scalar(query)
    if pair is None:
        db.execute(
            insert(CandidatePair)
            .values(
                id=uuid.uuid4(),
                requirement_a_id=first,
                requirement_b_id=second,
                similarity_score=_similarity(db, a.id, b.id),
            )  # fmt: skip
            .on_conflict_do_nothing(index_elements=["requirement_a_id", "requirement_b_id"])
        )
        pair = db.scalars(query).one()
    return pair


class RuleChecker:
    def __init__(self, db: Session, *, llm: LLMClient | None = None) -> None:
        self.db = db
        self.llm = llm

    def _others(
        self, requirement: Requirement, mine: RequirementAttribute
    ) -> list[tuple[Requirement, RequirementAttribute]]:
        shared = [
            column == value
            for column, value in (
                (RequirementAttribute.entity, mine.entity),
                (RequirementAttribute.metric, mine.metric),
                (RequirementAttribute.action, mine.action),
            )
            if value is not None
        ]
        if mine.metric is not None:  # "concurrency" meets "concurrency:session"
            shared.append(
                func.split_part(RequirementAttribute.metric, ":", 1) == base_metric(mine.metric)
            )
        if not shared:
            return []
        rows = self.db.execute(
            select(Requirement, RequirementAttribute)
            .join(
                RequirementAttribute,
                (RequirementAttribute.requirement_id == Requirement.id)
                & (RequirementAttribute.version_no == Requirement.current_version),
            )
            .where(
                RequirementAttribute.project_id == requirement.project_id,
                Requirement.id != requirement.id,
                Requirement.state.not_in(NOT_CHECKED),
                or_(*shared),
            )
            .order_by(Requirement.order_index, Requirement.id)
        )
        return [(requirement_row, attributes) for requirement_row, attributes in rows]

    def check(self, requirement: Requirement, *, run_id: uuid.UUID | None = None) -> list[Finding]:
        """Compare one requirement with the rest of its project; returns the new findings."""
        db = self.db
        if requirement.state in NOT_CHECKED:
            return []
        mine = index_requirement(db, requirement, llm=self.llm)
        created: list[Finding] = []
        for other, theirs in self._others(requirement, mine):
            for hit in compare(mine, theirs, a_req=requirement, b_req=other):
                finding = self._store(requirement, other, mine, theirs, hit, run_id)
                if finding is not None:
                    created.append(finding)
        db.commit()
        return created

    def check_all(
        self, requirements: Iterable[Requirement], *, run_id: uuid.UUID | None = None
    ) -> list[Finding]:
        """Index every requirement first, so each pair is seen from both sides."""
        listed = [r for r in requirements if r.state not in NOT_CHECKED]
        for requirement in listed:
            index_requirement(self.db, requirement, llm=self.llm)
        self.db.commit()
        return [f for r in listed for f in self.check(r, run_id=run_id)]

    def _store(
        self,
        a: Requirement,
        b: Requirement,
        a_attributes: RequirementAttribute,
        b_attributes: RequirementAttribute,
        hit: Hit,
        run_id: uuid.UUID | None,
    ) -> Finding | None:
        db = self.db
        pair = _pair(db, a, b)
        exists = db.scalar(live_rule_finding(pair.id, hit.rule_id))
        if exists is not None:
            return None
        finding = Finding(
            project_id=a.project_id,
            document_id=a.document_id or b.document_id,
            analysis_run_id=run_id,
            candidate_pair_id=pair.id,
            category=FindingCategory.CONFLICTING,
            confidence=CONFIDENCE[hit.rule_id],
            severity=SEVERITY[hit.rule_id],
            severity_source="system",  # US-08: the rule's own severity, overridable
            severity_proposed=SEVERITY[hit.rule_id].value,
            severity_reason=f"Rule {hit.rule_id}",
            rationale=hit.rationale,
            explanation=f"Rule check — {RULES[hit.rule_id]}. {hit.rationale}",
            # What the rule compared (the column keeps the producer's raw output, FR-20).
            original_ai_output={
                "rule_id": hit.rule_id,
                "attributes": {
                    str(a.id): _as_json(a_attributes),
                    str(b.id): _as_json(b_attributes),
                },
            },
            source="rule",
            rule_id=hit.rule_id,
        )
        try:
            with db.begin_nested():
                db.add(finding)
                db.flush()
        except IntegrityError:  # another delivery stored it first
            return None
        return finding


def _as_json(row: RequirementAttribute) -> dict[str, object]:
    return {
        "entity": row.entity,
        "metric": row.metric,
        "value": row.value,
        "unit": row.unit,
        "comparison": row.comparison,
        "actor": row.actor,
        "action": row.action,
        "condition": row.condition,
        "negated": row.negated,
        "modality": row.modality,
        "extractor": row.extractor,
    }


def live_rule_finding(pair_id: uuid.UUID, rule_id: str) -> Select[Any]:
    """The live rule finding for a pair, if any. Asked twice per conflicting pair, so it must use
    the partial unique index ``uq_findings_live_rule``: ``NOT is_stale`` matches its predicate,
    ``is_stale IS FALSE`` does not and scans every finding (25 ms each at 60,000 findings)."""
    return select(Finding.id).where(
        Finding.candidate_pair_id == pair_id,
        Finding.source == "rule",
        Finding.rule_id == rule_id,
        ~Finding.is_stale,
    )


def requirements_of(db: Session, run: AnalysisRun) -> list[Requirement]:
    if run.scope is AnalysisScope.REQUIREMENT:
        requirement = db.get(Requirement, run.subject_id)
        return [requirement] if requirement is not None else []
    if run.scope is AnalysisScope.DOCUMENT:
        return list(
            db.scalars(
                select(Requirement)
                .where(Requirement.document_id == run.subject_id)
                .order_by(Requirement.order_index)
            )
        )
    return []  # consequence checks compare a proposal, which is not a requirement version yet


def on_run(db: Session, run: AnalysisRun, *, llm: LLMClient | None = None) -> list[Finding]:
    """The rule checks of an analysis run's requirements (``analysis.after_run``)."""
    return RuleChecker(db, llm=llm).check_all(requirements_of(db, run), run_id=run.id)
