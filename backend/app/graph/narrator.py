"""The written feed under the map (Dhavni — US-14, FR-84; interface design §9).

Every ``graph.delta`` carries one or more plain sentences saying what changed and who did it —
"Arjun added REQ-031.", "Analysis of REQ-031: 1 conflict with REQ-014 (high)." — so the map can
be followed without watching it, and a screen-reader user gets the same news.

Template sentences only: never an LLM (the AI summary of US-55 is separate and labelled).
Requirements are named by their printed ID and people by their name; requirement text never
appears (CR-04 — the feed travels over the event bus).
"""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from app.graph.schemas import EdgeKind

STATE_WORDS = {
    "Proposed": "Proposed",
    "Under_Review": "Under review",
    "Approved": "Approved",
    "Rejected": "Rejected",
    "Implemented": "Implemented",
    "Deprecated": "Deprecated",
}
# How a finding reads next to the requirement it was found for.
_RELATION: dict[EdgeKind, tuple[str, str]] = {  # (one, many)
    "conflict": ("1 conflict with", "conflicts with"),
    "duplicate": ("1 possible duplicate of", "possible duplicates of"),
    "depends_on": ("1 dependency on", "dependencies on"),
    "link": ("1 link to", "links to"),
}
_SINGLE: dict[EdgeKind, tuple[str, str]] = {
    "ambiguous": ("ambiguous wording", "ambiguous wording"),
    "incomplete": ("missing information", "missing information"),
}
_PLURAL = {
    "conflict": "conflicts",
    "duplicate": "duplicates",
    "depends_on": "dependencies",
    "ambiguous": "ambiguities",
    "incomplete": "incomplete requirements",
    "link": "links",
}
_REVIEW_VERBS = {
    "confirm": "confirmed",
    "dismiss": "dismissed",
    "merge": "merged",
    "reclassify": "reclassified",
    "reopen": "reopened",
    "escalate": "escalated",
}
_KIND_NOUN: dict[EdgeKind, str] = {
    "conflict": "conflict",
    "duplicate": "duplicate",
    "depends_on": "dependency",
    "ambiguous": "ambiguity",
    "incomplete": "missing-information finding",
    "link": "link",
}


@dataclass(frozen=True)
class Related:
    """One finding as the narrator needs it."""

    kind: EdgeKind
    other: str | None  # the other requirement's label; None for a single-requirement finding
    severity: str | None = None


def _who(actor: str | None) -> str:
    return actor or "Someone"


def _join(items: Sequence[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def added(actor: str | None, label: str, state: str = "Proposed") -> str:
    return f"{_who(actor)} added {label} ({STATE_WORDS.get(state, state)})."


def analysed(label: str, related: Sequence[Related]) -> str:
    """ "Analysis of REQ-031: 1 conflict with REQ-014 (high) and ambiguous wording."."""
    if not related:
        return f"Analysis of {label}: no issues detected (analysis can miss conflicts)."
    parts: list[str] = []
    for kind, (one, many) in _RELATION.items():
        others = [r for r in related if r.kind == kind and r.other]
        if not others:
            continue
        names = [r.other + (f" ({r.severity})" if r.severity else "") for r in others if r.other]
        parts.append(
            f"{one} {names[0]}" if len(names) == 1 else f"{len(names)} {many} {_join(names)}"
        )
    for kind, (one, _many) in _SINGLE.items():
        if any(r.kind == kind for r in related):
            parts.append(one)
    return f"Analysis of {label}: {_join(parts)}."


def document_analysed(document: str, kinds: Sequence[EdgeKind]) -> str:
    if not kinds:
        return f"Analysis of {document} finished: no issues detected (analysis can miss conflicts)."
    counts = Counter(kinds)
    parts = [f"{n} {_KIND_NOUN[k] if n == 1 else _PLURAL[k]}" for k, n in sorted(counts.items())]
    return f"Analysis of {document} finished: {_join(parts)}."


def reviewed(
    actor: str | None,
    action: str,
    kind: EdgeKind,
    labels: Sequence[str],
    *,
    new_kind: EdgeKind | None = None,
) -> str:
    verb = _REVIEW_VERBS.get(action, action)
    noun = _KIND_NOUN[kind]
    subject = (
        f"the {noun} between {_join(list(labels))}"
        if len(labels) > 1
        else (f"the {noun} on {labels[0]}" if labels else f"a {noun}")
    )
    tail = f" as {_KIND_NOUN[new_kind]}" if action == "reclassify" and new_kind else ""
    return f"{_who(actor)} {verb} {subject}{tail}."


def moved(actor: str | None, label: str, state: str) -> str:
    if state == "Approved":
        return f"{_who(actor)} approved {label}."
    if state == "Rejected":
        return f"{_who(actor)} rejected {label}."
    if state == "Implemented":
        return f"{_who(actor)} marked {label} implemented."
    return f"{_who(actor)} moved {label} to {STATE_WORDS.get(state, state)}."


def owner_changed(actor: str | None, label: str, owner: str | None) -> str:
    if owner is None:
        return f"{_who(actor)} removed the owner of {label}."
    return f"{_who(actor)} made {owner} the owner of {label}."


def issue_opened(actor: str | None, number: int, labels: Sequence[str]) -> str:
    """A member opened ISS-n about requirements (US-52)."""
    return f"{_who(actor)} opened ISS-{number} on {_join(list(labels))}."


def auto_issue_opened(number: int, labels: Sequence[str], owners: Sequence[str]) -> str:
    """A conflict between owners became ISS-n by itself (FR-87). Owners by name."""
    return f"ISS-{number} opened for the conflict between {_join(list(labels))}: assigned to {_join(list(owners))}."


def issue_closed(actor: str | None, number: int, reason: str) -> str:
    why = {
        "resolved_by_merge": " by a merged change request",
        "finding_resolved": ": its finding was resolved",
    }.get(reason, "")
    if reason == "manual":
        return f"{_who(actor)} closed ISS-{number}."
    return f"ISS-{number} closed{why}."


def issue_reopened(actor: str | None, number: int, *, reflagged: bool = False) -> str:
    if reflagged:
        return f"ISS-{number} reopened: its conflict was found again."
    return f"{_who(actor)} reopened ISS-{number}."


def change_requested(actor: str | None, number: int, label: str, kind: str) -> str:
    """RCR-n opened (US-33). Never the proposed text."""
    what = "deprecating" if kind == "deprecate" else "a change to"
    return f"{_who(actor)} proposed {what} {label} (RCR-{number})."


def concern_raised(actor: str | None, kind: EdgeKind, labels: Sequence[str]) -> str:
    """A person raised a concern (US-56): the map shows it with a Person badge."""
    return f"{_who(actor)} raised a concern: {_KIND_NOUN.get(kind, kind)} on {_join(list(labels))}."


def linked(actor: str | None, source: str, words: str, target: str) -> str:
    """A person asserted a link (US-53): "Riya linked REQ-031 to REQ-014 (depends on)."."""
    return f"{_who(actor)} linked {source} to {target} ({words})."


def unlinked(actor: str | None, source: str, words: str, target: str) -> str:
    return f"{_who(actor)} removed the link: {source} {words} {target}."


def merged(actor: str | None, number: int, label: str, version: int) -> str:
    """RCR-n merged (US-35): the requirement has a new version."""
    return f"{_who(actor)} merged RCR-{number}: {label} is now v{version}."
