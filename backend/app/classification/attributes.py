"""Requirement attributes for rule-based cross-checks (Keval — US-58, FR-101, ADR-27; §11.5).

``AttributeExtractor.extract(text)`` turns one requirement into structured attributes — what it is
about, the number it sets and how, who acts, under what condition, and whether it is a "shall" or
a "shall not" — so Heet's ``RuleChecker`` can compare requirements **that the embedding filter
never paired** (a conflict worded very differently is still the same metric with two values).

**Deterministic patterns first** (``extractor="rules"``):

=================  =====================================================================
``condition``      an EARS prefix ("When…,", "While…,", "If…, then") or a trailing scope
                   ("… on payment screens", "… for administrators")
``modality``       ``shall`` (shall, must, will, is/are), ``shall_not`` (shall not, must
                   not, cannot, never), ``should``, ``may``
``actor``          the subject before the modal verb ("the system" → ``system``)
``action``         the verb and its object after the modal, stemmed ("lock account")
``value``/``unit`` the first number with a unit, normalised to a base unit (minutes →
                   seconds ``s``, GB → bytes ``B``, % → ``%``, attempts → ``count``)
``comparison``     ``<=`` (within, at most, no more than…), ``>=`` (at least…), ``=``
``metric``         a known measure the sentence talks about (``session_timeout``,
                   ``retention``, ``response_time``…), else the unit's dimension
``entity``         the subject, or the object when the subject is generic ("the system")
=================  =====================================================================

**The LLM only for what the patterns cannot parse** — no modal verb and no number — through
:func:`extract_with_llm`, recorded as ``extractor="llm"`` with the model's confidence. The
patterns never call it; the caller decides (and pays from the project budget).
"""

import re
import uuid
from dataclasses import asdict, dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.classification.llm_client import LLMClient, LLMError
from app.classification.prompting import _as_data, _schema_json, load_prompt

ATTRIBUTES_VERSION = "attributes-v1"

Comparison = Literal["<=", ">=", "="]
Modality = Literal["shall", "shall_not", "should", "may"]

GENERIC_ACTORS = frozenset(
    {
        "system",
        "application",
        "app",
        "platform",
        "service",
        "software",
        "server",
        "solution",
        "product",
        "website",
        "site",
        "portal",
        "tool",
        "module",
    }
)
_STOP = frozenset(
    {"the", "a", "an", "each", "every", "all", "any", "its", "their", "his", "her", "be", "to"}
    | {"only", "solely", "exclusively"}  # exclusivity is read from the text by the rule checker
    | {"able", "allowed", "permitted"}
)
_ID_PREFIX = re.compile(r"^\s*[A-Z]{2,8}-\d+\s*[:|.–—-]?\s*")  # "REQ-021: …"
# A subject ends where its qualifier starts: "Audit log entries older than 12 months".
_QUALIFIER = re.compile(
    r"\b(older|newer|than|that|which|who|whose|with|of|in|on|for|from|after|before|when|if)\b",
    re.IGNORECASE,
)
_PARTICLES = frozenset({"out", "up", "off", "down", "back"})  # "time out", "back up"
_NUMBER_WORDS = {
    word: str(n)
    for n, word in enumerate(
        [
            "zero",
            "one",
            "two",
            "three",
            "four",
            "five",
            "six",
            "seven",
            "eight",
            "nine",
            "ten",
            "eleven",
            "twelve",
        ]
    )
}
_WORD_NUMBER = re.compile(
    r"\b(" + "|".join(_NUMBER_WORDS) + r")\s+(?=(?:ms|milliseconds?|seconds?|minutes?|hours?|"
    r"days?|weeks?|months?|years?|characters?|attempts?)\b)",
    re.IGNORECASE,
)
_CONDITION_PREFIX = re.compile(
    r"^\s*(when|whenever|while|if|where|after|before|once|during|in case)\s+(?P<cond>[^,]+),\s*"
    r"(?:then\s+)?",
    re.IGNORECASE,
)
_TRAILING_SCOPE = re.compile(
    r"\b(?:on|in|for|during|while|when|if|within the)\s+(?P<scope>(?:the\s+)?[a-z][a-z \-]{2,40}?)"
    r"\s*(?:[.;]|$)",
    re.IGNORECASE,
)
_MODAL = re.compile(
    r"\b(shall not|must not|will not|may not|cannot|can not|shall never|must never|never|"
    r"shall|must|will|should|may|can|is|are)\b",
    re.IGNORECASE,
)
_MODALITY: dict[str, Modality] = {
    "shall": "shall",
    "must": "shall",
    "will": "shall",
    "is": "shall",
    "are": "shall",
    "should": "should",
    "may": "may",
    "can": "may",
}
_LESS = (
    r"within|in under|under|in less than|less than|fewer than|no more than|not more than|"
    r"at most|up to|a maximum of|maximum of|max\.?|not exceed|below"
)
_MORE = (
    r"at least|a minimum of|minimum of|no less than|not less than|more than|greater than|"
    r"over|above"
)
_NUMBER = re.compile(
    rf"(?:(?P<cmp>{_LESS}|{_MORE}|after|for|every|of|exactly|to)\s+)?"
    r"(?P<num>\d+(?:[.,]\d+)?)\s*(?P<unit>%|percent|ms|milliseconds?|seconds?|secs?|s\b|"
    r"minutes?|mins?|hours?|hrs?|h\b|days?|weeks?|months?|years?|kb|mb|gb|tb|characters?|"
    r"chars?|attempts?|tries|times|users?|requests?|records?|items?|sessions?|transactions?)?",
    re.IGNORECASE,
)
_UNITS: dict[str, tuple[str, str, float]] = {  # unit -> (dimension, base unit, factor)
    "ms": ("time", "s", 0.001),
    "millisecond": ("time", "s", 0.001),
    "s": ("time", "s", 1),
    "sec": ("time", "s", 1),
    "second": ("time", "s", 1),
    "min": ("time", "s", 60),
    "minute": ("time", "s", 60),
    "h": ("time", "s", 3600),
    "hr": ("time", "s", 3600),
    "hour": ("time", "s", 3600),
    "day": ("time", "s", 86_400),
    "week": ("time", "s", 604_800),
    "month": ("time", "s", 2_592_000),
    "year": ("time", "s", 31_536_000),
    "%": ("percent", "%", 1),
    "percent": ("percent", "%", 1),
    "kb": ("size", "B", 1e3),
    "mb": ("size", "B", 1e6),
    "gb": ("size", "B", 1e9),
    "tb": ("size", "B", 1e12),
    "character": ("length", "chars", 1),
    "char": ("length", "chars", 1),
}
_METRICS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (name, re.compile(pattern, re.IGNORECASE))
    for name, pattern in (
        (
            "timeout",
            r"\b(time ?out|expire|expiry|inactiv|idle|log(?:ged)? out|sign(?:ed)? out)",
        ),
        ("lockout", r"\b(lock|lockout|locked)\b|\bfailed (?:login |sign[- ]in )?attempts?"),
        ("password_length", r"\bpasswords?\b"),
        ("retention", r"\b(retain|retention|kept|keep|stored?|archiv|delet|purg|remov)"),
        ("availability", r"\b(availab|uptime)"),
        ("backup", r"\bback ?ups?\b"),
        ("upload_size", r"\b(upload|file size|attachment)"),
        ("response_time", r"\b(respon|latency|load|render|display|return)"),
        ("concurrency", r"\bconcurrent\b|\bsimultaneous\b"),
    )
)


@dataclass(frozen=True)
class Attributes:
    entity: str | None = None
    metric: str | None = None
    value: float | None = None
    unit: str | None = None
    comparison: Comparison | None = None
    actor: str | None = None
    action: str | None = None
    condition: str | None = None
    negated: bool = False
    modality: Modality | None = None
    extractor: Literal["rules", "llm"] = "rules"
    confidence: float = 0.0

    @property
    def parsed(self) -> bool:
        """Enough for a rule to work on: a modal verb with an action, or a number."""
        return (self.modality is not None and self.action is not None) or self.value is not None

    def as_json(self) -> dict[str, Any]:
        return asdict(self)


def stem(word: str) -> str:
    """A tiny suffix stripper, enough to match "deleted" with "delete" and "logs" with "logged"."""
    word = word.lower()
    for suffix in ("ing", "ied", "ed", "es", "s", "e"):
        if len(word) > len(suffix) + 2 and word.endswith(suffix):
            word = word[: -len(suffix)] + ("y" if suffix == "ied" else "")
            break
    if len(word) > 3 and word[-1] == word[-2] and word[-1] not in "aeiouls":
        word = word[:-1]
    return word


def _singular(word: str) -> str:
    if len(word) > 3 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _phrase(text: str, *, limit: int = 3) -> str | None:
    words = [w for w in re.findall(r"[a-z][a-z\-]*", text.lower()) if w not in _STOP]
    if not words:
        return None
    words = words[-limit:]
    words[-1] = _singular(words[-1])
    return " ".join(words)


def _number(text: str) -> tuple[float, str, Comparison, str] | None:
    """(value in base unit, base unit, comparison, dimension) of the first number with context."""
    for found in _NUMBER.finditer(text):
        raw_unit = (found.group("unit") or "").lower().rstrip(".")
        unit_key = raw_unit[:-1] if raw_unit.endswith("s") and raw_unit[:-1] in _UNITS else raw_unit
        number = float(found.group("num").replace(",", "."))
        cmp_word = (found.group("cmp") or "").lower()
        comparison: Comparison = (
            "<="
            if re.fullmatch(_LESS, cmp_word)
            else ">="
            if re.fullmatch(_MORE, cmp_word)
            else "="
        )
        if unit_key in _UNITS:
            dimension, base, factor = _UNITS[unit_key]
            return number * factor, base, comparison, dimension
        if raw_unit:  # a counted noun: "5 attempts", "100 users"
            return number, "count", comparison, f"count:{_singular(stem(raw_unit) or raw_unit)}"
        if cmp_word:  # "at most 3"
            return number, "count", comparison, "count"
    return None


class AttributeExtractor:
    """Pure: text in, :class:`Attributes` out. One per requirement (its main statement)."""

    def extract(self, text: str) -> Attributes:
        text = _ID_PREFIX.sub("", text.strip(), count=1)
        text = _WORD_NUMBER.sub(lambda m: f"{_NUMBER_WORDS[m.group(1).lower()]} ", text)
        sentence = text
        condition: str | None = None
        prefix = _CONDITION_PREFIX.match(sentence)
        if prefix:
            condition = _phrase(prefix.group("cond"), limit=4)
            sentence = sentence[prefix.end() :]
        modal = _MODAL.search(sentence)
        modality: Modality | None = None
        negated = False
        actor: str | None = None
        action: str | None = None
        obj: str | None = None
        rest = sentence
        if modal:
            word = " ".join(modal.group(1).lower().split())
            negated = word in {
                "shall not",
                "must not",
                "will not",
                "may not",
                "cannot",
                "can not",
                "shall never",
                "must never",
                "never",
            }
            modality = "shall_not" if negated else _MODALITY.get(word.split()[0], "shall")
            actor = _phrase(_QUALIFIER.split(sentence[: modal.start()], maxsplit=1)[0])
            rest = sentence[modal.end() :]
            if re.match(r"\s+(not|never)\b", rest, re.IGNORECASE):
                negated, modality = True, "shall_not"
                rest = re.sub(r"^\s+(not|never)\b", "", rest, flags=re.IGNORECASE)
            verb_object = re.split(
                r"\b(?:after|within|for|in|on|at|by|to|of|when|if|while|"
                r"every|before|during|with|from|than|\d)",
                rest,
                maxsplit=1,
            )[0]
            words = [w for w in re.findall(r"[a-z][a-z\-]*", verb_object.lower()) if w not in _STOP]
            verb = 2 if len(words) > 1 and words[1] in _PARTICLES else 1
            if words:
                action = " ".join(stem(w) for w in words[: verb + 2])
                obj = _phrase(" ".join(words[verb:]))
        if condition is None:
            scope = _TRAILING_SCOPE.search(rest)
            if scope and not re.search(r"\d", scope.group("scope")):
                condition = _phrase(scope.group("scope"), limit=4)

        value = unit = comparison = None
        dimension: str | None = None
        number = _number(sentence)
        if number:
            value, unit, comparison, dimension = number
        metric = next((name for name, pattern in _METRICS if pattern.search(text)), None)
        if metric is None:
            metric = dimension
        elif dimension and dimension.startswith("count:"):
            metric = f"{metric}:{dimension.split(':', 1)[1]}"

        entity = actor
        if actor is None or actor.split()[-1] in GENERIC_ACTORS:
            entity = obj or actor
        found = [modality, actor, action, value]
        confidence = round(0.5 + 0.1 * sum(1 for part in found if part is not None), 2)
        return Attributes(
            entity=entity,
            metric=metric,
            value=value,
            unit=unit,
            comparison=comparison,
            actor=actor,
            action=action,
            condition=condition,
            negated=negated,
            modality=modality,
            extractor="rules",
            confidence=min(confidence, 0.9),
        )


# ── the LLM fallback ────────────────────────────────────────────────────────────────────────
class AttributesOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    entity: str | None = Field(description="What the requirement is about, singular, lower case")
    metric: str | None = Field(description="The measured quantity, snake_case, or null")
    value: float | None = Field(description="The number it sets, in the unit given, or null")
    unit: str | None = Field(description="s, %, B, chars or count; null without a number")
    comparison: Comparison | None
    actor: str | None = Field(description="Who or what acts, singular, lower case")
    action: str | None = Field(description="The verb and its object, lower case, e.g. lock account")
    condition: str | None = Field(description="When or where it applies, or null")
    modality: Modality | None
    confidence: float = Field(ge=0, le=1)


def extract_with_llm(
    text: str, *, llm: LLMClient, project_id: uuid.UUID | None
) -> Attributes | None:
    """What the patterns could not parse, asked of the model (``extractor="llm"``). ``None`` when
    the model is unavailable or its reply does not validate; budget errors propagate."""
    system = load_prompt("attributes_system", "v1").substitute(
        schema=_schema_json(AttributesOutput)
    )
    user = load_prompt("attributes_user", "v1").substitute(text=_as_data(text))
    try:
        output = llm.complete_json(system, user, AttributesOutput, project_id=project_id)
    except LLMError:
        return None
    return Attributes(
        entity=output.entity,
        metric=output.metric,
        value=output.value,
        unit=output.unit,
        comparison=output.comparison,
        actor=output.actor,
        action=" ".join(stem(w) for w in output.action.split()) if output.action else None,
        condition=output.condition,
        negated=output.modality == "shall_not",
        modality=output.modality,
        extractor="llm",
        confidence=output.confidence,
    )
