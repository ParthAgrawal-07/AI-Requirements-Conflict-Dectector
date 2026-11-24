"""The fidelity check of an updated SRS (Bansil — US-61, DR-25; design update §12.4).

Runs before publishing; any failure blocks it and is listed in words:

* **every baseline requirement exactly once, verbatim** — the text of each Approved and
  Implemented requirement frozen in the draft must appear as exactly one requirement quote in the
  requirement sections ("REQ-031 missing", "REQ-014 appears twice", "REQ-007 text differs");
* **no Proposed or rejected text** — no section may contain the text of a requirement of the
  project that is not in the baseline (Proposed, Under review, Rejected, Deprecated);
* **no stray "shall" or "must"** — a narrative or appendix sentence using either word must cite a
  baseline requirement ID; otherwise it reads like a requirement nobody approved.

Whitespace is normalised before comparing; nothing else is.
"""

import re
import uuid
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Requirement, RequirementState
from app.models.srs import SrsDocument, SrsSection

NOT_IN_BASELINE = (
    RequirementState.PROPOSED,
    RequirementState.UNDER_REVIEW,
    RequirementState.REJECTED,
    RequirementState.DEPRECATED,
)
MIN_FOREIGN_TEXT = 25  # shorter texts ("Log in.") would match by accident
_ID = re.compile(r"\b[A-Z][A-Z0-9]*-\d+(?:\.\d+)*\b")
_SENTENCE = re.compile(r"[^.!?\n]+[.!?]?")
_NORMATIVE = re.compile(r"\b(shall|must)\b", re.IGNORECASE)


@dataclass
class Failure:
    code: str  # missing, duplicated, not_baseline, normative
    message: str
    section_key: str | None = None
    label: str | None = None


@dataclass
class Report:
    passed: bool
    checked_at: str
    failures: list[Failure] = field(default_factory=list)
    requirements_checked: int = 0

    def as_json(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "checked_at": self.checked_at,
            "requirements_checked": self.requirements_checked,
            "failures": [asdict(f) for f in self.failures],
        }


def normalise(text: str) -> str:
    return " ".join(text.split())


def quotes(body: str) -> list[str]:
    """The block quotes of a Markdown body, each normalised (the requirement statements)."""
    found: list[str] = []
    current: list[str] = []
    for line in body.splitlines():
        if line.startswith(">"):
            current.append(line[2:] if line.startswith("> ") else line[1:])
        elif current:
            found.append(normalise("\n".join(current)))
            current = []
    if current:
        found.append(normalise("\n".join(current)))
    return found


def check(db: Session, document: SrsDocument, sections: list[SrsSection]) -> Report:
    failures: list[Failure] = []
    items = document.requirements or []
    in_requirements = Counter(
        q for s in sections if s.kind == "requirements" for q in quotes(s.body)
    )
    for item in items:
        label = item.get("label") or f"requirement {str(item['requirement_id'])[:8]}"
        text = normalise(str(item["body"]))
        seen = in_requirements.get(text, 0)
        if seen == 0:
            failures.append(Failure("missing", f"{label} missing", label=label))
        elif seen > 1:
            failures.append(Failure("duplicated", f"{label} appears {seen} times", label=label))

    baseline_ids = {i["label"] for i in items if i.get("label")}
    included = {uuid.UUID(i["requirement_id"]) for i in items}
    whole = {s.key: normalise(s.body) for s in sections}
    for requirement in db.scalars(
        select(Requirement).where(
            Requirement.project_id == document.project_id,
            Requirement.state.in_(NOT_IN_BASELINE),
        )
    ):
        if requirement.id in included:
            continue
        text = normalise(requirement.body)
        if len(text) < MIN_FOREIGN_TEXT:
            continue
        for key, body in whole.items():
            if text in body:
                label = requirement.source_req_id or f"requirement {str(requirement.id)[:8]}"
                state = requirement.state.value.replace("_", " ")
                failures.append(
                    Failure(
                        "not_baseline",
                        f"Section {key.split('_', 1)[0]} contains the text of {label}, "
                        f"which is {state} and not in the baseline",
                        section_key=key,
                        label=label,
                    )
                )

    for section in sections:
        if section.kind == "requirements":
            continue
        for sentence in _SENTENCE.findall(section.body):
            word = _NORMATIVE.search(sentence)
            if word and not set(_ID.findall(sentence)) & baseline_ids:
                failures.append(
                    Failure(
                        "normative",
                        f"Section {section.key.split('_', 1)[0]} contains a "
                        f"'{word.group(1).lower()}' sentence that is not "
                        f'a baseline requirement: "{sentence.strip()[:100]}"',
                        section_key=section.key,
                    )
                )
    return Report(
        passed=not failures,
        checked_at=datetime.now(UTC).isoformat(),
        failures=failures,
        requirements_checked=len(items),
    )
