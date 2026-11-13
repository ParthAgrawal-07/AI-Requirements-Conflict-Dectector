"""Finding explanations (Keval — US-07, FR-13, FR-14, NFR-17).

Turns a validated classifier output into what the finding card shows:

* ``explanation`` — the model's rationale, plus, in plain words, *what* is wrong where the output
  says so: the vague terms of an Ambiguous requirement, the missing facts of an Incomplete one,
  the direction of a dependency;
* ``evidence_spans`` — every quoted clause (``evidence`` / ``vague_terms``) **located in the
  requirement text** with character offsets, so the UI can highlight the problem clause in the
  side-by-side view. A quote that does not occur in either requirement is dropped from the spans:
  the UI never highlights words the requirement does not contain. The model's output is kept
  verbatim in ``findings.original_ai_output`` regardless (FR-20).

Pure: no database, no LLM. Confidence and the low-confidence marker are not decided here — the
threshold is the project's and can change, so the API applies it when reading.
"""

import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.classification.schemas import PairClassificationOutput, SingleClassificationOutput


@dataclass(frozen=True)
class Subject:
    """A requirement as the explanation refers to it."""

    id: uuid.UUID
    label: str  # printed ID, or the stand-in the model saw
    text: str


@dataclass(frozen=True)
class Explanation:
    text: str
    evidence_spans: list[dict[str, Any]] = field(default_factory=list)


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().strip("\"'“”‘’").strip())


def locate(quote: str, subjects: list[Subject]) -> dict[str, Any] | None:
    """Find ``quote`` in one of the requirements: exact first, then ignoring case and runs of
    whitespace. Returns the span with offsets into the stored text, or ``None``."""
    needle = _normalise(quote)
    if len(needle) < 2:
        return None
    for subject in subjects:
        start = subject.text.find(needle)
        if start < 0:
            pattern = r"\s+".join(re.escape(part) for part in needle.split(" "))
            match = re.search(pattern, subject.text, re.IGNORECASE)
            if match is None:
                continue
            start, end = match.span()
        else:
            end = start + len(needle)
        return {
            "requirement_id": str(subject.id),
            "label": subject.label,
            "quote": subject.text[start:end],
            "start": start,
            "end": end,
        }
    return None


def _spans(quotes: list[str], subjects: list[Subject]) -> list[dict[str, Any]]:
    spans: list[dict[str, Any]] = []
    for quote in quotes:
        span = locate(quote, subjects)
        if span is not None and span not in spans:
            spans.append(span)
    return spans


def _join(items: list[str]) -> str:
    return "; ".join(item.strip().rstrip(".") for item in items if item.strip())


def explain_pair(output: PairClassificationOutput, a: Subject, b: Subject) -> Explanation:
    parts = [output.rationale.strip()]
    if output.dependency_direction == "A_depends_on_B":
        parts.append(f"{a.label} depends on {b.label}.")
    elif output.dependency_direction == "B_depends_on_A":
        parts.append(f"{b.label} depends on {a.label}.")
    return Explanation(text=" ".join(parts), evidence_spans=_spans(output.evidence, [a, b]))


def explain_single(output: SingleClassificationOutput, subject: Subject) -> Explanation:
    parts = [output.rationale.strip()]
    if output.vague_terms:
        terms = ", ".join(f"“{_normalise(term)}”" for term in output.vague_terms)
        parts.append(f"Vague wording: {terms}.")
    if output.missing_information:
        parts.append(f"Missing: {_join(output.missing_information)}.")
    return Explanation(text=" ".join(parts), evidence_spans=_spans(output.vague_terms, [subject]))
