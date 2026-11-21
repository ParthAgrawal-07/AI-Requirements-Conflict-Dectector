"""The ISO/IEC/IEEE 29148 outline of the updated SRS and its system-written parts (Bansil —
US-61, US-41, FR-74, FR-106, DR-22, DR-25).

==============================  ==============  ================================================
Section                         Written by      Content
==============================  ==============  ================================================
1.1–1.3, 2.1–2.5, 4, Appendix A  the LLM          narrative (``app.classification.srs_sections``)
1.4 References                   the system       the brief's references
3.1 Functional, 3.2 Non-         the system       every Approved and Implemented requirement,
functional, 3.3 Constraints,                      **verbatim**, with ID, priority, owner and
3.4 Other                                         version, grouped by stakeholder group
Appendix B Open items            the system       only when a PM overrode the readiness check
==============================  ==============  ================================================

A requirement is written as a heading line naming it and a block quote holding its text exactly
as approved — the fidelity check (``app.srs.fidelity``) finds each one there, and the exporters
render quotes verbatim. :func:`template_text` is the no-LLM fallback for a narrative section: the
confirmed brief's own words, or a placeholder (FR-74).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from app.classification.srs_sections import NARRATIVE_SECTIONS, SPECS
from app.context.brief import BriefValues
from app.export.markdown import quote_lines


@dataclass(frozen=True)
class OutlineSection:
    key: str
    order: int
    title: str
    kind: str  # narrative, requirements, appendix
    group: str  # the chapter heading it sits under ("1 Introduction"), "" for a chapter itself


REQUIREMENT_GROUPS = (
    ("3.1_functional", "3.1 Functional requirements", "functional"),
    ("3.2_non_functional", "3.2 Non-functional requirements", "non_functional"),
    ("3.3_constraints", "3.3 Constraints", "constraint"),
    ("3.4_other", "3.4 Other requirements", None),
)
CHAPTERS = {
    "1": "1 Introduction",
    "2": "2 Overall description",
    "3": "3 Specific requirements",
}


def chapter(key: str) -> str:
    return CHAPTERS.get(key.split(".", 1)[0] if "." in key else "", "")


def outline(*, with_open_items: bool) -> list[OutlineSection]:
    """Every section of a new draft, in reading order."""
    narrative = {s.key: s for s in NARRATIVE_SECTIONS}
    keys: list[tuple[str, str, str]] = [
        (k, narrative[k].title, "narrative")
        for k in ("1.1_purpose", "1.2_scope", "1.3_definitions")
    ]
    keys.append(("1.4_references", "1.4 References", "narrative_system"))
    keys += [
        (k, narrative[k].title, "narrative")
        for k in (
            "2.1_product_perspective",
            "2.2_user_classes",
            "2.3_operating_environment",
            "2.4_constraints",
            "2.5_assumptions",
        )
    ]
    keys += [(key, title, "requirements") for key, title, _ in REQUIREMENT_GROUPS]
    keys.append(("4_changes", narrative["4_changes"].title, "narrative"))
    keys.append(("A_decisions", narrative["A_decisions"].title, "appendix"))
    if with_open_items:
        keys.append(("B_open_items", "Appendix B — Open items", "appendix_system"))
    return [
        OutlineSection(
            key=key,
            order=index,
            title=title,
            kind={"narrative_system": "narrative", "appendix_system": "appendix"}.get(kind, kind),
            group=chapter(key),
        )
        for index, (key, title, kind) in enumerate(keys, start=1)
    ]


def is_llm_section(key: str) -> bool:
    return key in SPECS


# ── requirement sections (verbatim) ─────────────────────────────────────────────────────────
def requirement_block(item: dict[str, Any]) -> str:
    meta = [f"**{item.get('label') or 'Unnumbered requirement'}**"]
    if item.get("priority"):
        meta.append(f"Priority: {str(item['priority']).capitalize()}")
    meta.append(f"Owner: {item.get('owner_name') or 'unassigned'}")
    meta.append(f"Version {item.get('version', 1)}")
    if item.get("state") == "Implemented":
        meta.append("Implemented")
    return " · ".join(meta) + "\n\n" + quote_lines(str(item["body"]))


def requirements_body(items: Sequence[dict[str, Any]], req_type: str | None) -> str:
    """The requirements of one type, grouped by stakeholder group (FR-74), verbatim."""
    known = {t for _, _, t in REQUIREMENT_GROUPS if t}
    chosen = [
        i
        for i in items
        if (i.get("req_type") == req_type if req_type else i.get("req_type") not in known)
    ]
    if not chosen:
        return "_No requirements of this type in the baseline._"
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in chosen:
        groups.setdefault(item.get("group") or "General", []).append(item)
    parts: list[str] = []
    for group in sorted(groups, key=lambda g: (g == "General", g.lower())):
        parts.append(f"#### {group}")
        parts += [requirement_block(i) for i in groups[group]]
    return "\n\n".join(parts)


# ── template text: the no-LLM fallback ──────────────────────────────────────────────────────
def _or_placeholder(text: str | None, what: str) -> str:
    return text.strip() if text and text.strip() else f"[To be written: {what}.]"


def template_text(key: str, brief: BriefValues, inputs: dict[str, Any]) -> str:
    """A narrative section from the confirmed brief and the computed inputs, without an LLM."""
    if key == "1.1_purpose":
        return _or_placeholder(brief.purpose, "the purpose of this specification")
    if key == "1.2_scope":
        scope_in = _or_placeholder(brief.scope_in, "what the product covers")
        scope_out = brief.scope_out.strip() if brief.scope_out else None
        return scope_in + (f"\n\nOut of scope: {scope_out}" if scope_out else "")
    if key == "1.3_definitions":
        terms = brief.glossary or []
        if not terms:
            return "[To be written: the project's terms and their meanings.]"
        return "\n".join(f"- **{t.term}**: {t.meaning}" for t in terms)
    if key == "1.4_references":
        refs = brief.references or []
        if not refs:
            return "_No references were listed in the project brief._"
        return "\n".join(f"- {r.title}" + (f" — {r.url}" if r.url else "") for r in refs)
    if key == "2.1_product_perspective":
        return _or_placeholder(brief.environment, "where the product sits among other systems")
    if key == "2.2_user_classes":
        actors = brief.actors or []
        groups = inputs.get("stakeholder_groups") or []
        lines = [f"- {a}" for a in actors] + [f"- {g} (stakeholder group)" for g in groups]
        return "\n".join(lines) or "[To be written: the user classes.]"
    if key == "2.3_operating_environment":
        return _or_placeholder(brief.environment, "the operating environment")
    if key == "2.4_constraints":
        text = "\n\n".join(t for t in (brief.constraints, brief.regulations) if t and t.strip())
        return _or_placeholder(text, "design and implementation constraints")
    if key == "2.5_assumptions":
        return _or_placeholder(brief.quality_goals, "assumptions and dependencies")
    if key == "4_changes":
        sentences = inputs.get("change_log") or []
        if not sentences:
            return "_No changes were logged since the previous version._"
        return "\n".join(f"- {s}" for s in sentences)
    if key == "A_decisions":
        decisions = inputs.get("decisions") or []
        if not decisions:
            return "_No decisions were recorded on closed issues._"
        return "\n".join(
            f"- {d['key']}: {d['title']} — decided by {d.get('decided_by') or 'the decision owner'}"
            + (f" ({d['reason']})" if d.get("reason") else "")
            for d in decisions
        )
    return "[To be written.]"
