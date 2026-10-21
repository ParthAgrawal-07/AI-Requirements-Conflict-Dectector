"""ProjectContextService (Bansil — US-60, FR-103 to FR-105, ADR-28).

The project context is a versioned brief (``project_contexts``). Rules:

* **Append-only.** Every change is a new version with its author and reason; nothing is updated
  in place, so findings that recorded ``context_version`` can always be traced to what the AI saw.
* **Setup → Active.** A project leaves Setup when the four required fields are filled *and*
  confirmed. Editing a field confirms it; an AI-drafted field is confirmed by naming it in
  ``confirm`` (interface design §8c). ``projects.context_version`` then points at that version.
* **After activation** every edit needs ``project.context`` (checked by the route) and a reason,
  required fields cannot be emptied, and the caller is told how many open findings could be
  re-run with the new context (FR-105). The context never changes a requirement (DR-24).
* **AI draft.** :func:`draft_from_sections` fills only fields nobody has confirmed, marks them
  ``ai_drafted``, and never activates the project (FR-104).

The ContextGate itself (``ensure_project_active``) is Parth's; :func:`ensure_analysis_allowed`
adds the names of the missing fields to its message.
"""

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.context.brief import (
    COLUMN_TO_FIELD,
    COLUMNS,
    SPECS,
    BriefField,
    BriefValues,
    FieldStatus,
    is_filled,
    labels,
    missing_required,
)
from app.context.drafter import BriefDrafter, SectionLike
from app.core.errors import BadRequestError, ConflictError, NotFoundError
from app.models import (
    AuditAction,
    AuditLog,
    Document,
    Finding,
    FindingStatus,
    Project,
    ProjectContext,
    ProjectStatus,
    User,
)
from app.services.projects import ensure_project_active

logger = logging.getLogger(__name__)

MAX_SUMMARY_WORDS = 300


@dataclass(frozen=True)
class SaveResult:
    context: ProjectContext
    created: bool  # False when the request changed nothing
    activated: bool  # this save moved the project from Setup to Active
    open_findings: int  # findings that could be re-run with the new context (0 in Setup)


# ── Reading ───────────────────────────────────────────────────────────────────


def latest_context(db: Session, project_id: uuid.UUID) -> ProjectContext | None:
    """The newest version, confirmed or not (what the setup wizard shows)."""
    return db.scalar(
        select(ProjectContext)
        .where(ProjectContext.project_id == project_id)
        .order_by(ProjectContext.version.desc())
        .limit(1)
    )


def confirmed_context(db: Session, project: Project) -> ProjectContext | None:
    """The version in force for analysis (``projects.context_version``), or None in Setup."""
    if project.context_version == 0:
        return None
    return db.scalar(
        select(ProjectContext).where(
            ProjectContext.project_id == project.id,
            ProjectContext.version == project.context_version,
        )
    )


def list_versions(
    db: Session, project_id: uuid.UUID, *, limit: int, offset: int
) -> tuple[list[ProjectContext], int]:
    total = (
        db.scalar(
            select(func.count(ProjectContext.id)).where(ProjectContext.project_id == project_id)
        )
        or 0
    )
    rows = db.scalars(
        select(ProjectContext)
        .where(ProjectContext.project_id == project_id)
        .order_by(ProjectContext.version.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return list(rows), total


def values_of(context: ProjectContext | None) -> BriefValues:
    if context is None:
        return BriefValues()
    return BriefValues.model_validate({column: getattr(context, column) for column in COLUMNS})


def status_of(context: ProjectContext | None) -> dict[str, str]:
    return dict(context.field_status) if context is not None else {}


def missing_fields(context: ProjectContext | None) -> list[BriefField]:
    return missing_required(values_of(context), status_of(context))


def ensure_analysis_allowed(db: Session, project: Project) -> None:
    """The ContextGate with the missing fields named (FR-103). 409 unless the project is active."""
    if project.status is ProjectStatus.ACTIVE:
        return
    ensure_project_active(
        project, missing_fields=labels(missing_fields(latest_context(db, project.id)))
    )


def count_open_findings(db: Session, project_id: uuid.UUID) -> int:
    return (
        db.scalar(
            select(func.count(Finding.id))
            .join(Document, Document.id == Finding.document_id)
            .where(Document.project_id == project_id, Finding.status == FindingStatus.FLAGGED)
        )
        or 0
    )


def build_summary(values: BriefValues) -> str:
    """A plain summary of the brief, at most 300 words, for the context pack (FR-105).

    Built from the confirmed fields only, so it never says more than the Project Manager did.
    """
    parts = [values.purpose or ""]
    if values.scope_in:
        parts.append(f"In scope: {values.scope_in}")
    if values.scope_out:
        parts.append(f"Out of scope: {values.scope_out}")
    if values.actors:
        parts.append("Actors: " + ", ".join(values.actors) + ".")
    if values.environment:
        parts.append(f"Environment: {values.environment}")
    if values.quality_goals:
        parts.append(f"Quality goals: {values.quality_goals}")
    if values.constraints:
        parts.append(f"Constraints: {values.constraints}")
    if values.regulations:
        parts.append(f"Regulations: {values.regulations}")
    words = " ".join(part.strip() for part in parts if part.strip()).split()
    if len(words) <= MAX_SUMMARY_WORDS:
        return " ".join(words)
    return " ".join(words[:MAX_SUMMARY_WORDS]) + " …"


# ── Writing ───────────────────────────────────────────────────────────────────


def _lock_project(db: Session, project_id: uuid.UUID) -> Project:
    """Serialise writers of one project's context, so two saves can't take the same version."""
    project = db.scalar(select(Project).where(Project.id == project_id).with_for_update())
    if project is None:
        raise NotFoundError("Project not found")
    if project.status is ProjectStatus.ARCHIVED:
        raise ConflictError("This project is archived; its context can no longer be changed")
    return project


def _changed_fields(before: BriefValues, after: BriefValues) -> set[BriefField]:
    return {COLUMN_TO_FIELD[c] for c in COLUMNS if getattr(before, c) != getattr(after, c)}


def save_context(
    db: Session,
    *,
    project_id: uuid.UUID,
    actor: User,
    changes: BriefValues,
    confirm: Sequence[BriefField] = (),
    reason: str | None = None,
) -> SaveResult:
    """Apply a ``PUT /projects/{p}/context`` and store the result as a new version.

    ``changes`` carries only the columns the caller sent (``model_fields_set``); sending a column
    as null clears it. Fields in ``confirm`` keep their value and become ``confirmed``.
    """
    project = _lock_project(db, project_id)
    previous = latest_context(db, project.id)
    before = values_of(previous)
    status = status_of(previous)
    reason = (reason or "").strip() or None
    was_active = project.status is ProjectStatus.ACTIVE

    after = before.model_copy(update={c: getattr(changes, c) for c in changes.model_fields_set})
    edited = _changed_fields(before, after)
    for field in edited:
        if is_filled(field, after):
            status[field.value] = FieldStatus.CONFIRMED  # editing a field confirms it
        else:
            status.pop(field.value, None)
    for field in confirm:
        if not is_filled(field, after):
            raise BadRequestError(
                f"'{SPECS[field].label}' is empty, so it cannot be confirmed",
                code="context_field_empty",
            )
        status[field.value] = FieldStatus.CONFIRMED

    if status == status_of(previous) and not edited:
        if previous is None:
            raise BadRequestError("Nothing to save: the brief is empty", code="context_empty")
        db.rollback()  # releases the row lock
        return SaveResult(previous, created=False, activated=False, open_findings=0)

    missing = missing_required(after, status)
    if was_active:
        if missing:
            raise BadRequestError(
                "Required fields cannot be emptied once the project is active: "
                + ", ".join(labels(missing)),
                code="context_required_field_empty",
            )
        if reason is None:
            raise BadRequestError(
                "Give a reason for changing the context of an active project",
                code="context_reason_required",
            )

    context = _append_version(
        db,
        project=project,
        previous=previous,
        values=after,
        status=status,
        created_by=actor.id,
        reason=reason,
        source_document_id=previous.source_document_id if previous else None,
    )
    activated = False
    if not missing:
        context.summary = build_summary(_confirmed_only(after, status))
        project.context_version = context.version
        if not was_active:
            project.status = ProjectStatus.ACTIVE
            activated = True
    _audit(
        db,
        project,
        actor.id,
        AuditAction.PROJECT_ACTIVATED if activated else AuditAction.CONTEXT_UPDATED,
        context,
        fields=sorted(f.value for f in edited | set(confirm)),
    )
    db.commit()
    open_findings = count_open_findings(db, project.id) if was_active else 0
    return SaveResult(context, created=True, activated=activated, open_findings=open_findings)


def draft_from_sections(
    db: Session,
    *,
    project_id: uuid.UUID,
    sections: Sequence[SectionLike],
    drafter: BriefDrafter,
    document: Document | None = None,
    actor: User | None = None,
) -> ProjectContext | None:
    """Draft the brief from a document (FR-104). Confirmed fields are never overwritten.

    Returns the new version, or None if the draft added nothing. The project's status and
    ``context_version`` are untouched: a draft must be confirmed before it is used.
    """
    drafted = drafter.draft(sections)
    project = _lock_project(db, project_id)
    previous = latest_context(db, project.id)
    before = values_of(previous)
    status = status_of(previous)

    # Only columns the draft has text for, and only in fields nobody has confirmed. A draft may
    # fill half of a field (scope in, but nothing said about scope out); it is still a draft.
    updates = {
        column: getattr(drafted, column)
        for column, field in COLUMN_TO_FIELD.items()
        if getattr(drafted, column) and status.get(field.value) != FieldStatus.CONFIRMED
    }
    after = before.model_copy(update=updates)
    edited = _changed_fields(before, after)
    if not edited:
        db.rollback()
        return None
    for field in edited:
        status[field.value] = FieldStatus.AI_DRAFTED

    name = document.filename if document is not None else "a document"
    context = _append_version(
        db,
        project=project,
        previous=previous,
        values=after,
        status=status,
        created_by=actor.id if actor else None,
        reason=f"AI draft from {name}",
        source_document_id=document.id if document is not None else None,
    )
    # The worker drafts on behalf of whoever uploaded the document, so the audit names them.
    audit_actor = actor.id if actor else (document.uploaded_by if document else None)
    if audit_actor is not None:
        _audit(
            db,
            project,
            audit_actor,
            AuditAction.CONTEXT_DRAFTED,
            context,
            fields=sorted(f.value for f in edited),
        )
    db.commit()
    return context


def _confirmed_only(values: BriefValues, status: dict[str, str]) -> BriefValues:
    return values.model_copy(
        update={
            column: None
            for column, field in COLUMN_TO_FIELD.items()
            if status.get(field.value) != FieldStatus.CONFIRMED
        }
    )


def _append_version(
    db: Session,
    *,
    project: Project,
    previous: ProjectContext | None,
    values: BriefValues,
    status: dict[str, str],
    created_by: uuid.UUID | None,
    reason: str | None,
    source_document_id: uuid.UUID | None,
) -> ProjectContext:
    context = ProjectContext(
        project_id=project.id,
        version=(previous.version if previous else 0) + 1,
        field_status=status,
        created_by=created_by,
        reason=reason,
        source_document_id=source_document_id,
        **values.to_columns(),
    )
    db.add(context)
    db.flush()
    return context


def _audit(
    db: Session,
    project: Project,
    actor_id: uuid.UUID,
    action: AuditAction,
    context: ProjectContext,
    *,
    fields: list[str],
) -> None:
    # Identifiers and field names only — the brief text stays out of the audit log (CR-04).
    db.add(
        AuditLog(
            workspace_id=project.workspace_id,
            actor_id=actor_id,
            action=action,
            details={
                "project_id": str(project.id),
                "context_version": context.version,
                "fields": fields,
            },
        )
    )
