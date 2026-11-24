"""Reviewing, checking, publishing and comparing an updated SRS (Bansil — US-61, FR-107,
DR-25; design update §12.4).

* **Review, section by section** (:func:`review`): *accept* the text as it is; *edit* it (the
  person's text replaces the AI's and counts as accepted); *regenerate* it with an instruction
  (a new LLM call, counted against the budget). AI text stays labelled until accepted.
  Requirement sections are system text and refuse every action (``409 locked``): their wording
  changes only through change requests.
* **Fidelity** (:func:`run_fidelity`, ``app.srs.fidelity``) — any change to a section clears an
  earlier result, so a publish always rests on a check of the text being published.
* **Publish** (:func:`publish`, ``srs.publish``) — every section accepted and a passing check
  of the current text; the next version label (v1.0, v1.1, …) is assigned and the document
  becomes immutable (a database trigger). The counts of what the export leaves out are frozen
  with it (US-59).
* **Compare** (:func:`compare`) two SRS versions of a project, section by section and
  requirement by requirement.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.classification.context_pack import ContextPackBuilder
from app.core.errors import AppError, BadRequestError, ConflictError
from app.export import open_items
from app.models import AuditAction, AuditLog, Project
from app.models.srs import SrsDocument, SrsSection
from app.realtime import bus
from app.realtime.events import SRS_PUBLISHED, srs_event
from app.services.access import AccessContext
from app.srs import fidelity, generator
from app.srs import inputs as section_inputs

MAX_BODY = 20_000
MAX_INSTRUCTION = 500


def sections_of(db: Session, srs_id: uuid.UUID) -> list[SrsSection]:
    return list(
        db.scalars(select(SrsSection).where(SrsSection.srs_id == srs_id).order_by(SrsSection.order))
    )


def versions(db: Session, project_id: uuid.UUID) -> list[SrsDocument]:
    """Drafts and published versions, newest first."""
    return list(
        db.scalars(
            select(SrsDocument)
            .where(SrsDocument.project_id == project_id, SrsDocument.status != "discarded")
            .order_by(SrsDocument.created_at.desc())
        )
    )


def next_label(db: Session, project_id: uuid.UUID) -> str:
    labels = db.scalars(
        select(SrsDocument.version_label).where(
            SrsDocument.project_id == project_id, SrsDocument.status == "published"
        )
    ).all()
    numbers: list[tuple[int, int]] = []
    for label in labels:
        try:
            left, right = (label or "v0.0")[1:].split(".")
            numbers.append((int(left), int(right)))
        except ValueError:
            continue
    if not numbers:
        return "v1.0"
    major, minor = max(numbers)
    return f"v{major}.{minor + 1}"


def _draft(document: SrsDocument) -> None:
    if document.status != "draft":
        raise ConflictError(
            "Only a finished draft can be changed"
            if document.status != "published"
            else "A published SRS is immutable",
            code="not_a_draft",
        )


def review(
    db: Session,
    ctx: AccessContext,
    document: SrsDocument,
    key: str,
    action: str,
    *,
    body: str | None = None,
    instruction: str | None = None,
) -> SrsSection:
    _draft(document)
    section = db.scalar(
        select(SrsSection).where(SrsSection.srs_id == document.id, SrsSection.key == key)
    )
    if section is None:
        raise BadRequestError(f"No section {key!r} in this draft", code="unknown_section")
    if section.kind == "requirements" or section.source == "system":
        raise ConflictError(
            "Requirement sections are inserted verbatim by the system; change a requirement "
            "through a change request",
            code="locked",
        )
    if section.status == "generating":
        raise ConflictError("The section is still being written", code="generating")
    now = datetime.now(UTC)
    if action == "accept":
        section.status, section.accepted_by, section.accepted_at = "accepted", ctx.user.id, now
    elif action == "edit":
        text = (body or "").strip()
        if not text:
            raise BadRequestError("The section text cannot be empty", code="empty_section")
        if len(text) > MAX_BODY:
            raise BadRequestError(f"A section is at most {MAX_BODY} characters", code="too_long")
        section.body, section.source, section.note = text, "edited", None
        section.status, section.accepted_by, section.accepted_at = "accepted", ctx.user.id, now
    elif action == "regenerate":
        if section.key not in generator.SPECS:
            raise ConflictError("Only AI-written sections can be regenerated", code="not_ai")
        asked = (instruction or "").strip()
        if len(asked) > MAX_INSTRUCTION:
            raise BadRequestError(
                f"An instruction is at most {MAX_INSTRUCTION} characters", code="too_long"
            )
        section.instruction = asked or None
        section.regenerations += 1
        section.status, section.accepted_by, section.accepted_at = "generating", None, None
    else:  # pragma: no cover — the API validates the action
        raise BadRequestError("Unknown action", code="invalid_action")
    document.fidelity_report = None  # a check covers the text it ran on, and only that
    db.add(
        AuditLog(
            workspace_id=ctx.workspace_id,
            actor_id=ctx.user.id,
            action=AuditAction.SRS_SECTION_REVIEWED,
            details={"srs_id": str(document.id), "section": key, "action": action},
        )
    )
    db.commit()
    if action == "regenerate":
        generator.enqueue(generator.REGENERATE, [str(document.id), key])
    return section


def regenerate(db: Session, srs_id: uuid.UUID, key: str, llm: Any) -> SrsSection | None:
    """Rewrite one section with its instruction (the ``srs.regenerate`` task)."""
    document = db.get(SrsDocument, srs_id)
    if document is None or document.status != "draft":
        return None
    section = db.scalar(
        select(SrsSection).where(SrsSection.srs_id == srs_id, SrsSection.key == key)
    )
    project = db.get(Project, document.project_id)
    if section is None or project is None or section.status != "generating":
        return None
    data = section_inputs.build(db, project, document)
    pack = ContextPackBuilder(db).build(project, query_text=project.name).text
    generator.write_one(db, project, document, section, llm, data, pack=pack)
    return section


def run_fidelity(db: Session, document: SrsDocument) -> fidelity.Report:
    if document.status not in ("draft", "published"):
        raise ConflictError("The draft is still being written", code="generating")
    report = fidelity.check(db, document, sections_of(db, document.id))
    if document.status == "draft":
        document.fidelity_report = report.as_json()
        db.commit()
    return report


def discard(db: Session, ctx: AccessContext, document: SrsDocument) -> SrsDocument:
    if document.status == "published":
        raise ConflictError("A published SRS is immutable", code="not_a_draft")
    document.status = "discarded"
    db.add(
        AuditLog(
            workspace_id=ctx.workspace_id,
            actor_id=ctx.user.id,
            action=AuditAction.SRS_DISCARDED,
            details={"srs_id": str(document.id)},
        )
    )
    db.commit()
    return document


def publish(db: Session, ctx: AccessContext, document: SrsDocument) -> SrsDocument:
    _draft(document)
    sections = sections_of(db, document.id)
    pending = [s.key for s in sections if s.status != "accepted"]
    if pending:
        raise AppError(
            f"{len(pending)} section{'s' * (len(pending) != 1)} still to accept",
            status_code=409,
            code="sections_pending",
            details=[{"code": "pending", "message": key} for key in pending],
        )
    if not (document.fidelity_report or {}).get("passed"):
        raise ConflictError(
            "Run the fidelity check on the current text first", code="fidelity_required"
        )
    report = fidelity.check(db, document, sections)  # the same text, re-checked at the gate
    if not report.passed:
        document.fidelity_report = report.as_json()
        db.commit()
        raise AppError(
            "The fidelity check fails",
            status_code=409,
            code="fidelity_failed",
            details=[{"code": f.code, "message": f.message} for f in report.failures],
        )
    project = db.get(Project, document.project_id)
    if project is None:  # pragma: no cover
        raise ConflictError("The project no longer exists", code="gone")
    excluded = open_items.excluded_counts(db, project.id)
    document.fidelity_report = {**report.as_json(), "excluded": excluded}
    document.version_label = next_label(db, project.id)
    document.status = "published"
    document.published_by, document.published_at = ctx.user.id, datetime.now(UTC)
    db.add(
        AuditLog(
            workspace_id=project.workspace_id,
            actor_id=ctx.user.id,
            action=AuditAction.SRS_PUBLISHED,
            details={
                "project_id": str(project.id),
                "srs_id": str(document.id),
                "version": document.version_label,
                "baseline_revision": document.baseline_revision,
            },
        )
    )
    try:
        db.commit()
    except IntegrityError:  # another version was published at the same moment
        db.rollback()
        raise ConflictError(
            "Another SRS version was just published; publish again", code="label_taken"
        ) from None
    bus.publish(
        srs_event(
            SRS_PUBLISHED,
            workspace_id=project.workspace_id,
            project_id=project.id,
            srs_id=document.id,
            version=document.version_label,
        )
    )
    return document


@dataclass
class Comparison:
    base: SrsDocument
    target: SrsDocument
    sections: list[dict[str, Any]] = field(
        default_factory=list
    )  # key, title, change, before, after
    requirements: dict[str, list[dict[str, Any]]] = field(default_factory=dict)


def compare(db: Session, base: SrsDocument, target: SrsDocument) -> Comparison:
    if base.project_id != target.project_id:  # the access layer already refuses this
        raise ConflictError("SRS versions of different projects", code="different_projects")
    result = Comparison(base, target)
    before = {s.key: s for s in sections_of(db, base.id)}
    after = {s.key: s for s in sections_of(db, target.id)}
    order = sorted(set(before) | set(after), key=lambda k: (after.get(k) or before[k]).order)
    for key in order:
        old, new = before.get(key), after.get(key)
        change = (
            "added" if old is None else "removed" if new is None
            else "changed" if old.body != new.body else "unchanged"
        )  # fmt: skip
        result.sections.append(
            {
                "key": key,
                "title": new.title if new is not None else old.title if old is not None else key,
                "change": change,
                "before": old.body if old and change != "unchanged" else None,
                "after": new.body if new and change != "unchanged" else None,
            }
        )
    old_items = {i["requirement_id"]: i for i in base.requirements or []}
    new_items = {i["requirement_id"]: i for i in target.requirements or []}
    result.requirements = {
        "added": [new_items[k] for k in new_items if k not in old_items],
        "removed": [old_items[k] for k in old_items if k not in new_items],
        "changed": [
            {
                "label": new_items[k].get("label"),
                "from_version": old_items[k]["version"],
                "to_version": new_items[k]["version"],
                "before": old_items[k]["body"],
                "after": new_items[k]["body"],
            }  # fmt: skip
            for k in new_items
            if k in old_items and old_items[k]["body"] != new_items[k]["body"]
        ],
    }
    return result
