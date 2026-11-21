"""Creating and writing an updated SRS draft (Bansil — US-61, FR-106, NFR-38; design update
§12.4, ``SrsDraftGenerator``).

:func:`create_draft` (``POST /projects/{p}/srs``):

1. freezes the requirements the SRS is built from — the chosen labelled baseline's items, or the
   project's current Approved and Implemented requirements — with their printed ID, version,
   text, priority, owner, type and stakeholder group;
2. runs the readiness checklist (``app.srs.readiness``). Blocking items refuse the draft
   (``409 not_ready``) unless a Project Manager (``srs.publish``) overrides with a reason; the
   open-items report (US-59) is then attached and becomes Appendix B;
3. writes the outline: requirement sections are rendered from the frozen list right away
   (system text, accepted, never editable); narrative sections wait for the worker.

:func:`generate` (the ``srs.generate`` task) writes each narrative section with one LLM call
(``app.classification.srs_sections``), about ten in all. A section the model cannot write — no
model, budget used up, or text that keeps breaking DR-25 — gets the template text from the
confirmed brief instead, marked so the reviewer knows. Each finished section is announced
(``srs.section_ready``), then the whole draft (``srs.draft_ready``).
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.classification.context_pack import ContextPackBuilder
from app.classification.llm_client import LLMClient
from app.classification.srs_sections import SPECS, SectionUnavailable, write_section
from app.core.errors import AppError, ConflictError, ForbiddenError, NotFoundError
from app.export import open_items
from app.models import (
    AuditAction,
    AuditLog,
    Baseline,
    BaselineItem,
    Project,
    Requirement,
    RequirementState,
    User,
)
from app.models.srs import SrsDocument, SrsSection
from app.realtime import bus
from app.realtime.events import SRS_DRAFT_READY, SRS_SECTION_READY, srs_event
from app.services.access import AccessContext
from app.srs import inputs as section_inputs
from app.srs import outline, readiness

logger = logging.getLogger(__name__)

IN_BASELINE = (RequirementState.APPROVED, RequirementState.IMPLEMENTED)
OPEN_STATUSES = ("generating", "draft")
GENERATE = "suggestions.srs_generate"  # runs on the suggestions queue: never delays analysis
REGENERATE = "suggestions.srs_regenerate"


def freeze(db: Session, project: Project, baseline: Baseline | None) -> list[dict[str, Any]]:
    """The requirements an SRS is built from, frozen with everything the document prints."""
    if baseline is not None:
        rows = list(
            db.execute(
                select(BaselineItem, Requirement)
                .join(Requirement, Requirement.id == BaselineItem.requirement_id)
                .where(BaselineItem.baseline_id == baseline.id)
                .order_by(Requirement.order_index, BaselineItem.label, Requirement.id)
            )
        )
        pairs = [(r, item.version_no, item.state, item.body, item.label) for item, r in rows]
    else:
        current = db.scalars(
            select(Requirement)
            .where(Requirement.project_id == project.id, Requirement.state.in_(IN_BASELINE))
            .order_by(Requirement.order_index, Requirement.source_req_id, Requirement.id)
        )
        pairs = [(r, r.current_version, r.state.value, r.body, r.source_req_id) for r in current]
    owners = {
        u.id: u.full_name
        for u in db.scalars(
            select(User).where(User.id.in_({r.owner_id for r, *_ in pairs if r.owner_id}))
        )
    }
    return [
        {
            "requirement_id": str(r.id),
            "label": label,
            "version": version,
            "state": state,
            "body": body,
            "priority": r.priority,
            "owner_id": str(r.owner_id) if r.owner_id else None,
            "owner_name": owners.get(r.owner_id) if r.owner_id else None,
            "req_type": r.req_type,
            "group": r.stakeholder_group,
        }
        for r, version, state, body, label in pairs
    ]


def open_draft(db: Session, project_id: uuid.UUID) -> SrsDocument | None:
    return db.scalar(
        select(SrsDocument).where(
            SrsDocument.project_id == project_id, SrsDocument.status.in_(OPEN_STATUSES)
        )
    )


def readiness_for(
    db: Session, project: Project, baseline: Baseline | None
) -> tuple[list[dict[str, Any]], list[readiness.Check]]:
    items = freeze(db, project, baseline)
    return items, readiness.check(db, [uuid.UUID(i["requirement_id"]) for i in items])


def create_draft(
    db: Session,
    ctx: AccessContext,
    project: Project,
    *,
    baseline_id: uuid.UUID | None = None,
    override_reason: str | None = None,
) -> SrsDocument:
    baseline = None
    if baseline_id is not None:
        baseline = db.get(Baseline, baseline_id)
        if baseline is None or baseline.project_id != project.id:
            raise NotFoundError("Baseline not found")
    existing = open_draft(db, project.id)
    if existing is not None:
        raise ConflictError(
            "This project already has an SRS draft: finish or discard it first",
            code="draft_open",
        )
    items, checks = readiness_for(db, project, baseline)
    if not items:
        raise ConflictError(
            "No Approved or Implemented requirements to put in an SRS", code="empty_baseline"
        )
    blocking = readiness.blocking(checks)
    reason = (override_reason or "").strip() or None
    report = None
    if blocking:
        if reason is None:
            raise AppError(
                "Resolve the readiness checklist first, or a Project Manager overrides it",
                status_code=409,
                code="not_ready",
                details=[
                    {"code": c.key, "message": f"{c.count} {c.label.lower()}"} for c in blocking
                ],
            )
        if not ctx.can("srs.publish"):
            raise ForbiddenError("Only a Project Manager may override the readiness checklist")
        report = open_items.build(
            db,
            project,
            baseline_revision=baseline.baseline_revision if baseline else project.baseline_revision,
            baseline_label=baseline.label if baseline else None,
            generated_at=datetime.now(UTC),
        )
    document = SrsDocument(
        project_id=project.id,
        baseline_id=baseline.id if baseline else None,
        baseline_revision=baseline.baseline_revision if baseline else project.baseline_revision,
        status="generating",
        context_version=project.context_version,
        requirements=items,
        readiness=[c.as_json() for c in checks],
        override_reason=reason if blocking else None,
        open_items=report.as_json() if report else None,
        created_by=ctx.user.id,
    )
    db.add(document)
    db.flush()
    for spec in outline.outline(with_open_items=report is not None):
        db.add(_section(document, spec, report))
    db.add(
        AuditLog(
            workspace_id=project.workspace_id,
            actor_id=ctx.user.id,
            action=AuditAction.SRS_DRAFT_CREATED,
            details={
                "project_id": str(project.id),
                "srs_id": str(document.id),
                "baseline_revision": document.baseline_revision,
                "override": bool(document.override_reason),
                "requirements": len(items),
            },
        )
    )
    db.commit()
    return document


def _section(
    document: SrsDocument, spec: outline.OutlineSection, report: open_items.OpenItems | None
) -> SrsSection:
    common: dict[str, Any] = {
        "srs_id": document.id,
        "key": spec.key,
        "order": spec.order,
        "title": spec.title,
        "kind": spec.kind,
    }
    if spec.kind == "requirements":
        req_type = next(t for k, _, t in outline.REQUIREMENT_GROUPS if k == spec.key)
        body = outline.requirements_body(document.requirements, req_type)
        return SrsSection(**common, body=body, source="system", status="accepted")
    if spec.key == "B_open_items" and report is not None:
        body = open_items.to_markdown(report).split("\n", 2)[2]  # without its own title
        return SrsSection(**common, body=body, source="system", status="accepted")
    if spec.key == "1.4_references":  # the brief's list: filled from it when generated
        return SrsSection(**common, source="template", status="generating")
    return SrsSection(**common, source="llm", status="generating")


def _publish_section(project: Project, document: SrsDocument, section: SrsSection) -> None:
    bus.publish(
        srs_event(
            SRS_SECTION_READY,
            workspace_id=project.workspace_id,
            project_id=project.id,
            srs_id=document.id,
            key=section.key,
            source=section.source,
        )
    )


def write_one(
    db: Session,
    project: Project,
    document: SrsDocument,
    section: SrsSection,
    llm: LLMClient | None,
    data: section_inputs.SectionInputs,
    *,
    pack: str,
) -> None:
    """Write (or rewrite) one narrative section; template text when the model cannot."""
    spec = SPECS.get(section.key)
    if spec is not None and llm is not None:
        try:
            draft = write_section(
                llm,
                spec,
                data.values,
                project_name=project.name,
                project_id=project.id,
                context_pack=pack,
                known_ids=data.known_ids,
                baseline_ids=data.baseline_ids,
                instruction=section.instruction,
            )
        except SectionUnavailable as error:
            section.llm_calls += error.llm_calls
            document.llm_calls += error.llm_calls
            section.body = outline.template_text(section.key, data.brief, data.values)
            section.source, section.llm_model = "template", None
            section.note = f"Template text: the AI could not write this section ({error.reason})."
        else:
            section.body, section.source, section.llm_model = draft.body, "llm", draft.model
            section.llm_calls += draft.llm_calls
            document.llm_calls += draft.llm_calls
            section.note = None
    else:
        section.body = outline.template_text(section.key, data.brief, data.values)
        section.source = "template"
        section.note = None if spec is None else "Template text: no AI model is configured."
    section.status = "pending"
    db.commit()
    _publish_section(project, document, section)


def generate(db: Session, srs_id: uuid.UUID, llm: LLMClient | None) -> SrsDocument | None:
    """Write every narrative section still waiting (the ``srs.generate`` task)."""
    document = db.get(SrsDocument, srs_id)
    if document is None or document.status not in OPEN_STATUSES:
        return None
    project = db.get(Project, document.project_id)
    if project is None:  # pragma: no cover
        return None
    data = section_inputs.build(db, project, document)
    pack = ContextPackBuilder(db).build(project, query_text=project.name).text
    waiting = db.scalars(
        select(SrsSection)
        .where(SrsSection.srs_id == document.id, SrsSection.status == "generating")
        .order_by(SrsSection.order)
    ).all()
    for section in waiting:
        try:
            write_one(db, project, document, section, llm, data, pack=pack)
        except Exception:
            db.rollback()
            logger.exception("SRS %s section %s failed", srs_id, section.key)
    document.status = "draft"
    db.commit()
    bus.publish(
        srs_event(
            SRS_DRAFT_READY,
            workspace_id=project.workspace_id,
            project_id=project.id,
            srs_id=document.id,
            llm_calls=document.llm_calls,
        )
    )
    return document


def enqueue(name: str, args: list[str]) -> None:
    from app.services import analysis_orchestrator

    # Looked up at call time so tests record it instead of needing a broker.
    analysis_orchestrator.send(name, args)
