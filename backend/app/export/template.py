"""Markdown for SRS exports (Bansil — US-41, US-61, FR-74, FR-107, DR-22).

* :func:`srs_markdown` — a published (or draft) updated SRS: title page, the excluded-items note,
  then its sections in outline order. AI text that has not been accepted is marked in a draft.
* :func:`template_markdown` — the **template export**, the fallback when there is no published
  SRS or no LLM budget: the IEEE 830 / 29148 outline with the confirmed brief (or placeholders) for
  the introduction and every Approved and Implemented requirement, verbatim, grouped by type and
  stakeholder group.

Both name the baseline revision and contain only Approved and Implemented requirements (DR-22);
the open-items report for the same revision lists the rest (US-59).
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from app.context.brief import BriefValues
from app.export.open_items import exclusion_note
from app.models.srs import SrsDocument, SrsSection
from app.srs import outline


def _revision(baseline_revision: int, baseline_label: str | None) -> str:
    text = f"Baseline revision {baseline_revision}"
    return text + (f" (snapshot “{baseline_label}”)" if baseline_label else "")


def srs_markdown(
    document: SrsDocument,
    sections: Sequence[SrsSection],
    *,
    project_name: str,
    baseline_label: str | None,
    published_by: str | None,
    excluded: dict[str, int],
) -> str:
    label = document.version_label or "draft"
    when = document.published_at.strftime("%d %b %Y") if document.published_at else None
    head = [
        f"# Software Requirements Specification — {project_name}",
        "",
        f"**SRS {label}** · {_revision(document.baseline_revision, baseline_label)}"
        + (
            f" · Published {when}" + (f" by {published_by}" if published_by else "") if when else ""
        ),
        "",
        f"_{exclusion_note(excluded)}_",
        "",
    ]
    if document.override_reason:
        head += [
            f"_Generated with open items (readiness overridden: {document.override_reason}); "
            "see Appendix B._",
            "",
        ]
    body: list[str] = []
    current_group = ""
    for section in sorted(sections, key=lambda s: s.order):
        spec_group = outline.chapter(section.key)
        if spec_group and spec_group != current_group:
            body += [f"## {spec_group}", ""]
            current_group = spec_group
        level = "###" if spec_group else "##"
        if not spec_group:
            current_group = ""
        title = section.title
        if (
            document.status != "published"
            and section.source == "llm"
            and section.status != "accepted"
        ):
            title += " (AI draft — not yet accepted)"
        body += [f"{level} {title}", "", section.body.strip() or "_Empty._", ""]
    return "\n".join(head + body).rstrip() + "\n"


def template_markdown(
    *,
    project_name: str,
    items: Sequence[dict[str, Any]],
    brief: BriefValues,
    baseline_revision: int,
    baseline_label: str | None,
    generated_at: datetime,
    excluded: dict[str, int],
) -> str:
    inputs: dict[str, Any] = {
        "stakeholder_groups": sorted({i["group"] for i in items if i.get("group")}),
    }
    lines = [
        f"# Software Requirements Specification — {project_name}",
        "",
        f"**Template export** · {_revision(baseline_revision, baseline_label)} · "
        f"generated {generated_at.strftime('%d %b %Y')}",
        "",
        f"_{exclusion_note(excluded)}_",
        "",
        "_This is the template export (IEEE 830 / ISO/IEC/IEEE 29148 outline): the introduction "
        "comes from the confirmed project brief, and the requirements are inserted verbatim._",
        "",
    ]
    for spec in outline.outline(with_open_items=False):
        if spec.key in ("4_changes", "A_decisions"):
            continue  # need a previous version and decisions: the updated SRS writes them
        if spec.group and (not lines or f"## {spec.group}" not in lines):
            lines += [f"## {spec.group}", ""]
        if spec.kind == "requirements":
            req_type = next(t for k, _, t in outline.REQUIREMENT_GROUPS if k == spec.key)
            text = outline.requirements_body(items, req_type)
        else:
            text = outline.template_text(spec.key, brief, inputs)
        lines += [f"### {spec.title}", "", text, ""]
    return "\n".join(lines).rstrip() + "\n"
